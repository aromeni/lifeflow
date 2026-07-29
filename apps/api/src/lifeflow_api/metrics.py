"""Stage 9 Delivery Phase 5 — bounded-cardinality operational metrics.

Every metric label comes from a closed, small registry: a provider name
(`"gmail"`/`"calendar"`), a fixed operation name, a `FailureCode` value, a
registered rate-limit policy code (`rate_limit_policy.py`, already closed),
or a fixed job/dependency name — never a user id, email, proposal id,
provider object id, URL, exception message, correlation id, or IP address,
any of which would be unbounded cardinality and could leak identifying
information into a metrics backend (threat model T6).

A single process-local `CollectorRegistry` (not the global default) so
tests can construct an isolated instance instead of accumulating state
across the whole test session."""

from __future__ import annotations

import functools
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram
from prometheus_client import generate_latest as _generate_latest

from lifeflow_api.google.errors import (
    GoogleAuthError,
    GoogleClientError,
    GoogleHistoryExpiredError,
    GoogleSyncTokenExpiredError,
    GoogleTransientError,
    InvalidGrantError,
)

REGISTRY = CollectorRegistry()

provider_requests_total = Counter(
    "lifeflow_provider_requests_total",
    "Google API requests by provider, operation, and outcome.",
    ["provider", "operation", "outcome"],
    registry=REGISTRY,
)
provider_request_duration_seconds = Histogram(
    "lifeflow_provider_request_duration_seconds",
    "Google API request latency by provider and operation.",
    ["provider", "operation"],
    registry=REGISTRY,
)
provider_timeouts_total = Counter(
    "lifeflow_provider_timeouts_total",
    "Google API requests that timed out, by provider and operation.",
    ["provider", "operation"],
    registry=REGISTRY,
)
retry_attempts_total = Counter(
    "lifeflow_retry_attempts_total",
    "Bounded read retries attempted, by dependency.",
    ["dependency"],
    registry=REGISTRY,
)
uncertain_outcomes_total = Counter(
    "lifeflow_uncertain_outcomes_total",
    "Executions that resolved as uncertain, by action type.",
    ["action_type"],
    registry=REGISTRY,
)
worker_job_events_total = Counter(
    "lifeflow_worker_job_events_total",
    "Worker job/cron invocations, by job name and outcome.",
    ["job", "outcome"],
    registry=REGISTRY,
)
stale_pending_recovered_total = Counter(
    "lifeflow_stale_pending_recovered_total",
    "Rows recovered from a stale pending/never-enqueued state, by kind.",
    ["kind"],
    registry=REGISTRY,
)
database_readiness_failures_total = Counter(
    "lifeflow_database_readiness_failures_total",
    "GET /ready calls where PostgreSQL was unreachable.",
    registry=REGISTRY,
)
redis_degraded_total = Counter(
    "lifeflow_redis_degraded_total",
    "GET /ready calls where Redis was unreachable (never blocking, fail-open).",
    registry=REGISTRY,
)
rate_limit_fail_open_total = Counter(
    "lifeflow_rate_limit_fail_open_total",
    "Rate-limit checks that failed open because Redis was unavailable, by policy.",
    ["policy_code"],
    registry=REGISTRY,
)
rate_limited_requests_total = Counter(
    "lifeflow_rate_limited_requests_total",
    "Requests rejected with 429, by registered rate-limit policy.",
    ["policy_code"],
    registry=REGISTRY,
)
http_responses_total = Counter(
    "lifeflow_http_responses_total",
    "HTTP responses by status class (2xx/3xx/4xx/5xx).",
    ["status_class"],
    registry=REGISTRY,
)


def status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"


@asynccontextmanager
async def observe_provider_call(provider: str, operation: str) -> AsyncIterator[None]:
    """Wraps one Google client method body: records a request count (by
    provider, operation, and a closed outcome vocabulary derived from
    `google.errors`) and a latency observation, then re-raises whatever the
    call raised unchanged — this never changes control flow, only observes
    it. `provider`/`operation` must always be literal, fixed strings at the
    call site (e.g. `"gmail"`/`"list_messages"`), never derived from a URL,
    account, or user value.

    A `GoogleTransientError` whose `__cause__` is an `httpx.TimeoutException`
    (set by the `raise ... from exc` in every client's `_get`/`_post`
    helper) is classified as the dedicated `"timeout"` outcome rather than
    the generic `"transient_error"` one, and *additionally* increments
    `provider_timeouts_total` — a deliberate, documented double count (one
    counter for "what kind of request outcome was this", one for "did this
    specific dependency time out", answering a different operational
    question each) rather than an accidental one. A `GoogleTransientError`
    raised directly from an HTTP 429/5xx response (no `__cause__`) is a real
    response, not a timeout, and keeps the `"transient_error"` outcome."""
    start = time.monotonic()
    outcome = "success"
    try:
        yield
    except InvalidGrantError:
        outcome = "grant_invalid"
        raise
    except GoogleAuthError:
        outcome = "auth_error"
        raise
    except GoogleHistoryExpiredError:
        outcome = "history_expired"
        raise
    except GoogleSyncTokenExpiredError:
        outcome = "sync_token_expired"
        raise
    except GoogleTransientError as exc:
        if isinstance(exc.__cause__, httpx.TimeoutException):
            outcome = "timeout"
            provider_timeouts_total.labels(provider=provider, operation=operation).inc()
        else:
            outcome = "transient_error"
        raise
    except GoogleClientError:
        outcome = "client_error"
        raise
    except Exception:
        outcome = "unknown_error"
        raise
    finally:
        provider_requests_total.labels(
            provider=provider, operation=operation, outcome=outcome
        ).inc()
        provider_request_duration_seconds.labels(provider=provider, operation=operation).observe(
            time.monotonic() - start
        )


def with_worker_metrics[T](
    job_name: str,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Records `worker_job_events_total{job=job_name, outcome=...}` around
    one ARQ job/cron invocation — `job_name` must always be a literal, fixed
    string at the decoration site (matching the function's own name is the
    convention every call site in `worker_app.py` follows), never derived
    from queue payload content. Typed like `with_worker_correlation`
    (`Callable[..., Awaitable[T]]`, not a `ParamSpec`) for the same reason:
    arq's `WorkerCoroutine` protocol does not structurally accept a
    `ParamSpec`-generic wrapper under mypy strict."""

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                result = await fn(*args, **kwargs)
            except Exception:
                worker_job_events_total.labels(job=job_name, outcome="failed").inc()
                raise
            worker_job_events_total.labels(job=job_name, outcome="succeeded").inc()
            return result

        return wrapper

    return decorator


def render_latest() -> tuple[bytes, str]:
    return _generate_latest(REGISTRY), CONTENT_TYPE_LATEST


__all__ = [
    "REGISTRY",
    "database_readiness_failures_total",
    "http_responses_total",
    "observe_provider_call",
    "provider_request_duration_seconds",
    "provider_requests_total",
    "provider_timeouts_total",
    "rate_limit_fail_open_total",
    "rate_limited_requests_total",
    "redis_degraded_total",
    "render_latest",
    "retry_attempts_total",
    "stale_pending_recovered_total",
    "status_class",
    "uncertain_outcomes_total",
    "worker_job_events_total",
]
