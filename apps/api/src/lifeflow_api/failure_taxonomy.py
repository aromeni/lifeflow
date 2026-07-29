"""Stage 9 Delivery Phase 5 — the closed operational failure taxonomy.

Every failure that could reach a log line, a metric label, or an API error
response must first be classified into exactly one of these codes, with a
fixed safe message. Never a raw exception message, provider response body,
or stack trace — those may contain source content or internals (threat
model T6) and would blow the bounded-cardinality requirement on metric
labels (a raw exception string is effectively unbounded cardinality).

Several codes below (`worker_stale_timeout`, `max_attempts_exhausted`,
`database_unavailable`, `redis_unavailable`, `generation_error`,
`worker_timeout`) already existed as untyped string literals duplicated
across `scheduled_briefs.py` and `deletion_ops.py` (Stage 8/9 Delivery
Phases 1-4). Their string *values* are kept byte-identical here — they are
already persisted in `ActionExecution.error_code`,
`ScheduledBriefRun.error_code`, and `DataDeletionOperation.safe_error_code`
columns and asserted in existing tests — so folding them into this enum is
a pure type-safety improvement, not a behaviour change.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from lifeflow_api.google.errors import GoogleAuthError, GoogleClientError, GoogleTransientError


class FailureCode(StrEnum):
    """Closed vocabulary. Add a new member here (with a safe message and a
    classification rule in `classify_exception`) rather than ever returning
    an ad hoc string from a new call site."""

    dependency_timeout = "dependency_timeout"
    dependency_unavailable = "dependency_unavailable"
    dependency_rate_limited = "dependency_rate_limited"
    # The pre-existing, already-persisted Redis-specific value (see module
    # docstring) — `classify_exception` returns this (not the more generic
    # `dependency_unavailable`) for a `redis.exceptions.RedisError`.
    redis_unavailable = "redis_unavailable"
    authentication_expired = "authentication_expired"
    authorisation_revoked = "authorisation_revoked"
    provider_transient_error = "provider_transient_error"
    provider_permanent_error = "provider_permanent_error"
    worker_unavailable = "worker_unavailable"
    worker_delayed = "worker_delayed"
    database_unavailable = "database_unavailable"
    redis_degraded = "redis_degraded"
    uncertain_external_outcome = "uncertain_external_outcome"
    configuration_error = "configuration_error"
    # Pre-existing values (see module docstring) — kept for byte-identical
    # backward compatibility with already-persisted rows.
    worker_stale_timeout = "worker_stale_timeout"
    max_attempts_exhausted = "max_attempts_exhausted"
    generation_error = "generation_error"
    worker_timeout = "worker_timeout"
    # The mandatory closed fallback for anything not explicitly classified
    # below — never a raw exception type or message.
    unknown_error = "unknown_error"


class Severity(StrEnum):
    info = "info"
    warning = "warning"
    error = "error"


@dataclass(frozen=True)
class FailureClassification:
    code: FailureCode
    safe_message: str
    retryable: bool
    severity: Severity


_SAFE_MESSAGES: dict[FailureCode, str] = {
    FailureCode.dependency_timeout: "The operation timed out.",
    FailureCode.dependency_unavailable: "A required service was temporarily unavailable.",
    FailureCode.dependency_rate_limited: "The external service is rate-limiting requests.",
    FailureCode.redis_unavailable: "The job queue was temporarily unavailable.",
    FailureCode.authentication_expired: "Your Google connection needs to be refreshed.",
    FailureCode.authorisation_revoked: "Your Google connection needs to be reconnected.",
    FailureCode.provider_transient_error: "Google was temporarily unavailable.",
    FailureCode.provider_permanent_error: "Google rejected the request.",
    FailureCode.worker_unavailable: "Background processing is temporarily unavailable.",
    FailureCode.worker_delayed: "This is taking longer than usual.",
    FailureCode.database_unavailable: "The database was temporarily unavailable.",
    FailureCode.redis_degraded: "A supporting service is running in a degraded mode.",
    FailureCode.uncertain_external_outcome: (
        "We could not confirm whether this action completed. It has not been retried."
    ),
    FailureCode.configuration_error: "This feature is not currently configured.",
    FailureCode.worker_stale_timeout: "The worker did not finish after repeated attempts.",
    FailureCode.max_attempts_exhausted: "This did not complete after repeated attempts.",
    FailureCode.generation_error: "Generation failed and was not completed.",
    FailureCode.worker_timeout: "The operation timed out.",
    FailureCode.unknown_error: "An unexpected error occurred.",
}


def safe_message(code: FailureCode) -> str:
    return _SAFE_MESSAGES[code]


def classify_exception(exc: BaseException) -> FailureClassification:
    """Map an exception to exactly one closed failure code. Import-lazy for
    optional dependencies (redis, sqlalchemy) so this module has no hard
    dependency on either being installed at import time in contexts that
    don't need them (kept simple here since both are always installed in
    this repo, but avoids a circular-import risk with `db.py`/`rate_limiter.py`).
    """
    import redis.exceptions as redis_exceptions
    from sqlalchemy.exc import OperationalError

    if isinstance(exc, GoogleAuthError):
        return FailureClassification(
            FailureCode.authentication_expired,
            safe_message(FailureCode.authentication_expired),
            retryable=True,
            severity=Severity.warning,
        )
    if isinstance(exc, GoogleTransientError):
        return FailureClassification(
            FailureCode.provider_transient_error,
            safe_message(FailureCode.provider_transient_error),
            retryable=True,
            severity=Severity.warning,
        )
    if isinstance(exc, GoogleClientError):
        return FailureClassification(
            FailureCode.provider_permanent_error,
            safe_message(FailureCode.provider_permanent_error),
            retryable=False,
            severity=Severity.error,
        )
    if isinstance(exc, redis_exceptions.RedisError):
        return FailureClassification(
            FailureCode.redis_unavailable,
            safe_message(FailureCode.redis_unavailable),
            retryable=True,
            severity=Severity.warning,
        )
    if isinstance(exc, OperationalError):
        return FailureClassification(
            FailureCode.database_unavailable,
            safe_message(FailureCode.database_unavailable),
            retryable=True,
            severity=Severity.error,
        )
    if isinstance(exc, TimeoutError):
        return FailureClassification(
            FailureCode.dependency_timeout,
            safe_message(FailureCode.dependency_timeout),
            retryable=True,
            severity=Severity.warning,
        )
    return FailureClassification(
        FailureCode.unknown_error,
        safe_message(FailureCode.unknown_error),
        retryable=False,
        severity=Severity.error,
    )


__all__ = [
    "FailureClassification",
    "FailureCode",
    "Severity",
    "classify_exception",
    "safe_message",
]
