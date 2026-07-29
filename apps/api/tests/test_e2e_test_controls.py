"""Stage 9 Delivery Phase 5 (§20): the test-only provider-control boundary.

`e2e_test_controls_enabled` and `google_api_origin_override` exist purely so
a local/CI Playwright run can point the real Google clients at an in-process
fake server instead of the real Google hosts — never reachable in
production, and inert unless explicitly turned on.
"""

import pytest
from tests.conftest import _test_settings
from tests.test_google_auth_and_connections_api import GOOGLE_SETTINGS_OVERRIDES

from lifeflow_api.google.calendar_client import CalendarEventClient
from lifeflow_api.google.gmail_client import GmailDraftClient
from lifeflow_api.main import create_app


def test_e2e_test_controls_enabled_refuses_to_start_in_production() -> None:
    settings = _test_settings("production").model_copy(
        update={**GOOGLE_SETTINGS_OVERRIDES, "e2e_test_controls_enabled": True}
    )
    with pytest.raises(RuntimeError, match="E2E_TEST_CONTROLS_ENABLED"):
        create_app(settings)


def test_e2e_test_controls_enabled_alone_is_safe_in_production() -> None:
    """The guard is specifically about the test-controls flag, not about
    Google being configured at all — production with real Google settings
    and the flag left off (the only combination a real deployment ever
    uses) must keep starting normally."""
    settings = _test_settings("production").model_copy(
        update={
            **GOOGLE_SETTINGS_OVERRIDES,
            "session_secret": "a-production-session-secret-value",  # pragma: allowlist secret
            "token_key_id": "prod-1",
        }
    )
    create_app(settings)  # must not raise


def test_origin_override_is_ignored_unless_test_controls_are_enabled() -> None:
    """Setting the override alone (the accidental-leftover-env-var case)
    must never redirect real Google traffic — the flag is the single gate."""
    settings = _test_settings("development").model_copy(
        update={
            **GOOGLE_SETTINGS_OVERRIDES,
            "e2e_test_controls_enabled": False,
            "google_api_origin_override": "http://127.0.0.1:8098",
        }
    )
    app = create_app(settings)
    gmail_client: GmailDraftClient = app.state.gmail_client
    calendar_client: CalendarEventClient = app.state.calendar_client
    assert gmail_client._base_url == "https://gmail.googleapis.com/gmail/v1/users/me"
    assert (
        calendar_client._base_url
        == "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    )


def test_origin_override_redirects_both_clients_when_test_controls_are_enabled() -> None:
    settings = _test_settings("development").model_copy(
        update={
            **GOOGLE_SETTINGS_OVERRIDES,
            "e2e_test_controls_enabled": True,
            "google_api_origin_override": "http://127.0.0.1:8098/",
        }
    )
    app = create_app(settings)
    gmail_client: GmailDraftClient = app.state.gmail_client
    calendar_client: CalendarEventClient = app.state.calendar_client
    assert gmail_client._base_url == "http://127.0.0.1:8098/gmail/v1/users/me"
    assert calendar_client._base_url == "http://127.0.0.1:8098/calendar/v3/calendars/primary/events"


def test_test_controls_enabled_without_an_origin_override_keeps_real_google() -> None:
    """Enabling the flag alone (no override configured) must not change
    behaviour — both must be set for anything to redirect."""
    settings = _test_settings("development").model_copy(
        update={**GOOGLE_SETTINGS_OVERRIDES, "e2e_test_controls_enabled": True}
    )
    app = create_app(settings)
    gmail_client: GmailDraftClient = app.state.gmail_client
    assert gmail_client._base_url == "https://gmail.googleapis.com/gmail/v1/users/me"
