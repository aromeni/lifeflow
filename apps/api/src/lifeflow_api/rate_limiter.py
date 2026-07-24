"""Stage 9 Delivery Phase 4 — the atomic Redis token-bucket limiter (ADR 0005
D64, D81).

One Lua script performs the entire read-refill-consume-write cycle inside a
single Redis command, so concurrent requests against the same bucket can
never race (no read-then-write window). Redis's own `TIME` command is the
clock, so all API instances agree regardless of local clock skew.

A bucket key never contains a raw subject: `hash_subject` HMACs the
authenticated user id or resolved client IP with a server-side secret before
it ever reaches Redis, so Redis holds only a namespace, a policy code, and an
opaque digest.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass

import redis.asyncio as aioredis

from lifeflow_api.rate_limit_policy import RateLimitPolicy, RateLimitSubjectType

logger = logging.getLogger(__name__)

# KEYS[1] = bucket key
# ARGV[1] = capacity (tokens)
# ARGV[2] = refill_rate (tokens per second)
# ARGV[3] = ttl_seconds
#
# Returns {allowed (0/1), remaining_tokens (string), retry_after_seconds (int)}.
_BUCKET_SCRIPT_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])

local time_parts = redis.call('TIME')
local now = tonumber(time_parts[1]) + tonumber(time_parts[2]) / 1000000

local bucket = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(bucket[1])
local ts = tonumber(bucket[2])
if tokens == nil or ts == nil then
  tokens = capacity
  ts = now
end

local elapsed = now - ts
if elapsed < 0 then
  elapsed = 0
end
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
end

redis.call('HMSET', key, 'tokens', tostring(tokens), 'ts', tostring(now))
redis.call('EXPIRE', key, ttl)

local retry_after = 0
if allowed == 0 then
  local deficit = 1 - tokens
  retry_after = math.ceil(deficit / refill_rate)
end

return {allowed, tostring(tokens), retry_after}
"""


def hash_subject(secret: str, subject_type: RateLimitSubjectType, normalised_subject: str) -> str:
    """A keyed digest of the rate-limit subject. `secret` is
    `RATE_LIMIT_KEY_SECRET` — independent of any user data and never logged —
    so the digest cannot be reversed or correlated without it."""
    message = f"{subject_type.value}:{normalised_subject}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def bucket_key(redis_prefix: str, policy_code: str, digest: str) -> str:
    return f"{redis_prefix}:{policy_code}:{digest}"


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int
    policy_code: str
    # True only when a Redis error made the decision fail open — allowed is
    # always True in that case, but callers/tests may want to distinguish
    # "genuinely under budget" from "we could not check".
    degraded: bool = False


class RateLimiter:
    """Thin wrapper around one shared Redis client and its registered script.
    Constructed once per app (see `main.py`) and stored on `app.state`."""

    def __init__(self, redis_client: aioredis.Redis, *, socket_timeout_seconds: float) -> None:
        self._redis = redis_client
        self._timeout = socket_timeout_seconds
        self._script = redis_client.register_script(_BUCKET_SCRIPT_LUA)

    async def check(self, key: str, policy: RateLimitPolicy) -> RateLimitDecision:
        """Evaluate one request against a bucket. Never raises: any Redis
        failure (connection error, timeout, unexpected reply) fails open —
        the ratified pilot posture (ADR 0005 D64) is availability over
        strictness, since a rate limiter is a defence-in-depth layer, not the
        source of truth for correctness (that remains the database)."""
        try:
            import asyncio

            result = await asyncio.wait_for(
                self._script(
                    keys=[key],
                    args=[
                        policy.capacity,
                        policy.refill_rate_per_second,
                        policy.bucket_ttl_seconds,
                    ],
                ),
                timeout=self._timeout,
            )
            allowed_flag, _remaining, retry_after = result
            return RateLimitDecision(
                allowed=bool(int(allowed_flag)),
                retry_after_seconds=min(int(retry_after), policy.refill_window_seconds),
                policy_code=policy.code,
            )
        except Exception:
            logger.warning("rate_limit.redis_check_failed policy=%s", policy.code)
            return RateLimitDecision(
                allowed=True, retry_after_seconds=0, policy_code=policy.code, degraded=True
            )

    async def aclose(self) -> None:
        await self._redis.aclose()


__all__ = ["RateLimitDecision", "RateLimiter", "bucket_key", "hash_subject"]
