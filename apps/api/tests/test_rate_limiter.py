"""Stage 9 Delivery Phase 4: the atomic Redis token-bucket limiter, against a
real Redis instance (ADR 0005 D64/D81). Uses a dedicated logical database
(index 5) on the dev-compose Redis so these tests never collide with the
worker's queue (db 0) or another suite; flushed before and after each test.
"""

import asyncio
import uuid

import pytest
import redis.asyncio as aioredis

from lifeflow_api.rate_limit_policy import RateLimitPolicy, RateLimitSubjectType
from lifeflow_api.rate_limiter import RateLimiter, bucket_key, hash_subject

pytestmark = pytest.mark.integration

TEST_REDIS_URL = "redis://localhost:6380/5"
SECRET = "test-rate-limit-hmac-secret-not-a-real-secret"  # pragma: allowlist secret


def _policy(**overrides: object) -> RateLimitPolicy:
    defaults: dict[str, object] = {
        "code": "test_policy",
        "subject_type": RateLimitSubjectType.authenticated_user,
        "capacity": 3,
        "refill_amount": 3,
        "refill_window_seconds": 60,
    }
    defaults.update(overrides)
    return RateLimitPolicy(**defaults)  # type: ignore[arg-type]


@pytest.fixture
async def redis_client() -> aioredis.Redis:  # type: ignore[misc]
    client: aioredis.Redis = aioredis.from_url(TEST_REDIS_URL)  # type: ignore[no-untyped-call]
    try:
        await client.flushdb()
    except Exception:
        pytest.skip("Redis is not running (docker compose up -d redis)")
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
def limiter(redis_client: aioredis.Redis) -> RateLimiter:
    return RateLimiter(redis_client, socket_timeout_seconds=2.0)


def _key(policy: RateLimitPolicy, subject: str = "user-1") -> str:
    digest = hash_subject(SECRET, policy.subject_type, subject)
    return bucket_key("ratelimit:v1", policy.code, digest)


async def test_first_request_is_allowed(limiter: RateLimiter) -> None:
    policy = _policy()
    decision = await limiter.check(_key(policy), policy)
    assert decision.allowed is True
    assert decision.degraded is False


async def test_capacity_is_enforced(limiter: RateLimiter) -> None:
    policy = _policy(capacity=2, refill_amount=2, refill_window_seconds=3600)
    key = _key(policy)
    first = await limiter.check(key, policy)
    second = await limiter.check(key, policy)
    third = await limiter.check(key, policy)
    assert first.allowed and second.allowed
    assert third.allowed is False


async def test_retry_after_is_positive_and_bounded(limiter: RateLimiter) -> None:
    policy = _policy(capacity=1, refill_amount=1, refill_window_seconds=30)
    key = _key(policy)
    await limiter.check(key, policy)
    blocked = await limiter.check(key, policy)
    assert blocked.allowed is False
    assert 0 < blocked.retry_after_seconds <= policy.refill_window_seconds


async def test_refill_permits_a_later_request(limiter: RateLimiter) -> None:
    # A one-second window refills fast enough to observe within a test.
    policy = _policy(capacity=1, refill_amount=1, refill_window_seconds=1)
    key = _key(policy)
    first = await limiter.check(key, policy)
    immediately_after = await limiter.check(key, policy)
    await asyncio.sleep(1.2)
    after_refill = await limiter.check(key, policy)
    assert first.allowed is True
    assert immediately_after.allowed is False
    assert after_refill.allowed is True


async def test_concurrent_requests_cannot_overshoot_capacity(limiter: RateLimiter) -> None:
    policy = _policy(capacity=5, refill_amount=5, refill_window_seconds=3600)
    key = _key(policy)
    results = await asyncio.gather(*(limiter.check(key, policy) for _ in range(20)))
    allowed_count = sum(1 for r in results if r.allowed)
    assert allowed_count == 5


async def test_separate_users_have_separate_buckets(limiter: RateLimiter) -> None:
    policy = _policy(capacity=1, refill_amount=1, refill_window_seconds=3600)
    key_a = _key(policy, subject=str(uuid.uuid4()))
    key_b = _key(policy, subject=str(uuid.uuid4()))
    assert key_a != key_b
    first_a = await limiter.check(key_a, policy)
    first_b = await limiter.check(key_b, policy)
    assert first_a.allowed and first_b.allowed


async def test_separate_anonymous_ips_have_separate_buckets(limiter: RateLimiter) -> None:
    policy = _policy(capacity=1, refill_amount=1, subject_type=RateLimitSubjectType.client_ip)
    key_a = _key(policy, subject="203.0.113.1")
    key_b = _key(policy, subject="203.0.113.2")
    assert key_a != key_b


async def test_route_parameter_does_not_create_a_separate_bucket(limiter: RateLimiter) -> None:
    """A proposal/account/operation id must never enter the subject — the
    caller always hashes only the stable user id, so two different
    proposal ids for the same user necessarily share one bucket key."""
    policy = _policy(capacity=1, refill_amount=1, refill_window_seconds=3600)
    user_id = str(uuid.uuid4())
    key_for_proposal_one = _key(policy, subject=user_id)
    key_for_proposal_two = _key(policy, subject=user_id)  # subject never includes a proposal id
    assert key_for_proposal_one == key_for_proposal_two
    first = await limiter.check(key_for_proposal_one, policy)
    second = await limiter.check(key_for_proposal_two, policy)
    assert first.allowed is True
    assert second.allowed is False


async def test_policies_remain_isolated_for_the_same_subject(limiter: RateLimiter) -> None:
    policy_a = _policy(code="policy_a", capacity=1, refill_amount=1)
    policy_b = _policy(code="policy_b", capacity=1, refill_amount=1)
    key_a = _key(policy_a)
    key_b = _key(policy_b)
    assert key_a != key_b
    first_a = await limiter.check(key_a, policy_a)
    first_b = await limiter.check(key_b, policy_b)
    assert first_a.allowed and first_b.allowed


async def test_redis_keys_expire(limiter: RateLimiter, redis_client: aioredis.Redis) -> None:
    policy = _policy(capacity=1, refill_amount=1, refill_window_seconds=60)
    key = _key(policy)
    await limiter.check(key, policy)
    ttl = await redis_client.ttl(key)
    assert 0 < ttl <= policy.bucket_ttl_seconds


async def test_redis_stores_no_raw_subject_or_payload(
    limiter: RateLimiter, redis_client: aioredis.Redis
) -> None:
    subject = "user-with-a-very-recognisable-id-999"
    policy = _policy()
    key = _key(policy, subject=subject)
    assert subject not in key
    await limiter.check(key, policy)
    stored = await redis_client.hgetall(key)
    stored_text = str(stored)
    assert subject not in stored_text
    assert set(stored.keys()) <= {b"tokens", b"ts"}


async def test_multiple_limiter_instances_share_the_same_bucket() -> None:
    """Two RateLimiter objects (standing in for two API instances) pointed at
    the same Redis must observe one shared bucket, not per-instance state."""
    client_a: aioredis.Redis = aioredis.from_url(TEST_REDIS_URL)  # type: ignore[no-untyped-call]
    client_b: aioredis.Redis = aioredis.from_url(TEST_REDIS_URL)  # type: ignore[no-untyped-call]
    try:
        await client_a.flushdb()
    except Exception:
        pytest.skip("Redis is not running (docker compose up -d redis)")
    try:
        limiter_a = RateLimiter(client_a, socket_timeout_seconds=2.0)
        limiter_b = RateLimiter(client_b, socket_timeout_seconds=2.0)
        policy = _policy(capacity=2, refill_amount=2, refill_window_seconds=3600)
        key = _key(policy)
        first = await limiter_a.check(key, policy)
        second = await limiter_b.check(key, policy)
        third = await limiter_a.check(key, policy)
        assert first.allowed and second.allowed
        assert third.allowed is False
    finally:
        await client_a.flushdb()
        await client_a.aclose()
        await client_b.aclose()


async def test_redis_unavailable_fails_open() -> None:
    unreachable: aioredis.Redis = aioredis.from_url(  # type: ignore[no-untyped-call]
        "redis://localhost:1/0", socket_connect_timeout=0.2, socket_timeout=0.2
    )
    limiter = RateLimiter(unreachable, socket_timeout_seconds=0.3)
    policy = _policy(capacity=1, refill_amount=1)
    decision = await limiter.check(_key(policy), policy)
    assert decision.allowed is True
    assert decision.degraded is True
    await unreachable.aclose()
