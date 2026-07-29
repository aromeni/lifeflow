"""Stage 9 Delivery Phase 5: the closed failure taxonomy classifies every
known exception type into exactly one safe code, never leaks a raw
exception message, and falls back safely for anything unrecognised."""

import redis.exceptions as redis_exceptions
from sqlalchemy.exc import OperationalError

from lifeflow_api.failure_taxonomy import FailureCode, Severity, classify_exception, safe_message
from lifeflow_api.google.errors import GoogleAuthError, GoogleClientError, GoogleTransientError


def test_google_auth_error_is_authentication_expired_and_retryable() -> None:
    result = classify_exception(GoogleAuthError("token rejected"))
    assert result.code == FailureCode.authentication_expired
    assert result.retryable is True
    assert result.severity == Severity.warning


def test_google_transient_error_is_provider_transient_and_retryable() -> None:
    result = classify_exception(GoogleTransientError("HTTP 503"))
    assert result.code == FailureCode.provider_transient_error
    assert result.retryable is True


def test_google_client_error_is_provider_permanent_and_not_retryable() -> None:
    result = classify_exception(GoogleClientError("HTTP 400", status_code=400))
    assert result.code == FailureCode.provider_permanent_error
    assert result.retryable is False
    assert result.severity == Severity.error


def test_redis_error_is_redis_unavailable_and_retryable() -> None:
    result = classify_exception(redis_exceptions.ConnectionError("refused"))
    assert result.code == FailureCode.redis_unavailable
    assert result.retryable is True


def test_operational_error_is_database_unavailable() -> None:
    result = classify_exception(OperationalError("stmt", {}, Exception("down")))
    assert result.code == FailureCode.database_unavailable
    assert result.retryable is True


def test_timeout_error_is_dependency_timeout() -> None:
    result = classify_exception(TimeoutError())
    assert result.code == FailureCode.dependency_timeout
    assert result.retryable is True


def test_unknown_exception_maps_to_the_closed_unknown_code_never_raw_text() -> None:
    result = classify_exception(ValueError("contains a secret token abc123"))
    assert result.code == FailureCode.unknown_error
    assert result.retryable is False
    assert "abc123" not in result.safe_message
    assert "secret" not in result.safe_message


def test_every_failure_code_has_a_registered_safe_message() -> None:
    for code in FailureCode:
        message = safe_message(code)
        assert isinstance(message, str)
        assert len(message) > 0
