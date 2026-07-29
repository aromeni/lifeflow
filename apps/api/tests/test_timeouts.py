"""Stage 9 Delivery Phase 5: the central timeout policy — every network
operation gets a finite, validated timeout, never a scattered magic number,
and a misconfigured non-positive override fails startup rather than
silently disabling the timeout."""

import pytest
from pydantic import ValidationError

from lifeflow_api.config import Settings
from lifeflow_api.timeouts import (
    database_statement_timeout_ms,
    google_httpx_timeout,
    google_httpx_write_timeout,
)


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg, arg-type]


def test_google_read_timeout_uses_configured_connect_and_read_values() -> None:
    settings = _settings(google_connect_timeout_seconds=3.0, google_read_timeout_seconds=7.0)
    timeout = google_httpx_timeout(settings)
    assert timeout.connect == 3.0
    assert timeout.read == 7.0


def test_google_write_timeout_uses_the_longer_write_budget() -> None:
    settings = _settings(google_connect_timeout_seconds=3.0, google_write_timeout_seconds=25.0)
    timeout = google_httpx_write_timeout(settings)
    assert timeout.connect == 3.0
    assert timeout.read == 25.0


def test_write_timeout_is_never_shorter_than_read_timeout_by_default() -> None:
    settings = _settings()
    read_timeout = google_httpx_timeout(settings)
    write_timeout = google_httpx_write_timeout(settings)
    assert write_timeout.read >= read_timeout.read


def test_database_statement_timeout_converts_seconds_to_milliseconds() -> None:
    settings = _settings(database_statement_timeout_seconds=2.5)
    assert database_statement_timeout_ms(settings) == "2500"


@pytest.mark.parametrize(
    "field",
    [
        "google_connect_timeout_seconds",
        "google_read_timeout_seconds",
        "google_write_timeout_seconds",
        "database_statement_timeout_seconds",
        "worker_health_check_timeout_seconds",
    ],
)
def test_non_positive_timeout_overrides_fail_startup_validation(field: str) -> None:
    with pytest.raises(ValidationError):
        _settings(**{field: 0})
    with pytest.raises(ValidationError):
        _settings(**{field: -1})
