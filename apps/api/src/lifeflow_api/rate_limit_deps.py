"""Stage 9 Delivery Phase 4 — the one reusable FastAPI rate-limit dependency
(ADR 0005 D64, D81).

`rate_limit_dependency(policy_code)` is the sole way a route declares a
policy — never a bare limiter call inside a service. It is evaluated once,
at route-declaration time, against the closed registry (`rate_limit_policy`),
so an unregistered code fails at import time rather than at request time.

`enforce_rate_limit` is also exported directly for the one route (deletion
confirm) whose correct policy depends on data only known after a read inside
the handler body — see `privacy_deletion.py`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, Request
from fastapi.params import Depends as DependsMarker

from lifeflow_api.deps import CurrentUser
from lifeflow_api.errors import RateLimitExceededError
from lifeflow_api.metrics import rate_limited_requests_total
from lifeflow_api.rate_limit_ip import resolve_client_ip
from lifeflow_api.rate_limit_policy import RateLimitSubjectType, effective_policy, get_policy
from lifeflow_api.rate_limiter import RateLimiter, bucket_key, hash_subject


async def enforce_rate_limit(request: Request, policy_code: str, *, subject: str) -> None:
    """Charge one token against `policy_code`'s bucket for `subject` (an
    already-resolved user id or client IP — never a path parameter). Raises
    `RateLimitExceededError` when the bucket is exhausted; returns silently
    when rate limiting is disabled, misconfigured, or Redis is unavailable
    (fail open, ADR 0005 D64)."""
    settings = request.app.state.settings
    if not settings.rate_limiting_enabled:
        return
    limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return

    policy = effective_policy(policy_code, request.app.state.rate_limit_policy_overrides)
    digest = hash_subject(request.app.state.rate_limit_key_secret, policy.subject_type, subject)
    key = bucket_key(settings.rate_limit_redis_prefix, policy.code, digest)
    decision = await limiter.check(key, policy)
    if not decision.allowed:
        rate_limited_requests_total.labels(policy_code=decision.policy_code).inc()
        raise RateLimitExceededError(decision.policy_code, decision.retry_after_seconds)


def _anonymous_subject(request: Request) -> str:
    settings = request.app.state.settings
    resolution = resolve_client_ip(
        request,
        trusted_proxy_cidrs=settings.trusted_proxy_cidrs,
        max_forwarded_hops=settings.rate_limit_max_forwarded_hops,
    )
    return resolution.ip


def rate_limit_dependency(policy_code: str) -> Callable[..., Awaitable[None]]:
    """Build a FastAPI dependency enforcing `policy_code`. Validated eagerly
    against the closed registry so a typo'd or retired code fails at import
    time, not at request time."""
    policy = get_policy(policy_code)

    if policy.subject_type is RateLimitSubjectType.authenticated_user:

        async def _authenticated_dependency(request: Request, user: CurrentUser) -> None:
            await enforce_rate_limit(request, policy_code, subject=str(user.id))

        return _authenticated_dependency

    async def _anonymous_dependency(request: Request) -> None:
        await enforce_rate_limit(request, policy_code, subject=_anonymous_subject(request))

    return _anonymous_dependency


def RateLimited(policy_code: str) -> DependsMarker:  # noqa: N802 - reads like Depends()
    """`dependencies=[RateLimited("policy_code")]` — the standard way every
    route in this codebase declares its rate-limit policy."""
    marker: DependsMarker = Depends(rate_limit_dependency(policy_code))
    return marker


__all__ = [
    "RateLimited",
    "enforce_rate_limit",
    "rate_limit_dependency",
]
