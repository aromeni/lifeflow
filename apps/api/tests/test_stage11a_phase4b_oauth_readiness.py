"""Stage 11A Phase 4B — OAuth callback readiness gaps found while inspecting
the implementation before designing the test-account connection plan
(governing task §8/§23), plus structural proofs that the Gmail/Calendar
clients cannot exceed LifeFlow's closed action model (governing task §6).

None of these tests connect a real Google account or call a real Google API
— they exercise only the existing fake/mock transport already used by
`test_google_auth_and_connections_api.py`.
"""

import inspect

import pytest
from tests.conftest import CSRF_HEADERS, _test_settings
from tests.test_google_auth_and_connections_api import (
    GOOGLE_SETTINGS_OVERRIDES,
    _extract_state,
    _google_client,
    _token_handler,
)

import lifeflow_api.auth as auth_module
from lifeflow_api.google.calendar_client import CalendarEventClient
from lifeflow_api.google.gmail_client import GmailDraftClient
from lifeflow_api.google.oauth import GoogleIdentity
from lifeflow_api.main import create_app

pytestmark = pytest.mark.integration


# --- denied/cancelled consent -----------------------------------------------


async def test_signin_denied_consent_redirects_safely_and_clears_pending_flow() -> None:
    async for gclient in _google_client(_token_handler()):
        login = await gclient.get("/auth/google/login", follow_redirects=False)
        state = _extract_state(login.headers["location"])

        denied = await gclient.get(
            "/auth/google/callback", params={"error": "access_denied"}, follow_redirects=False
        )
        assert denied.status_code == 302
        assert "auth_error=access_denied" in denied.headers["location"]

        # The pending flow must have been cleared by the denial, not left
        # for this now-stale state to be consumed later.
        replay = await gclient.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        assert "invalid_state" in replay.headers["location"]


async def test_connector_denied_consent_redirects_safely_and_clears_pending_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_verify(
        token: str, *, client_id: str, expected_nonce: str | None = None
    ) -> GoogleIdentity:
        return GoogleIdentity(subject="sub-denied", email="denied@example.com", email_verified=True)

    monkeypatch.setattr(auth_module, "verify_id_token", fake_verify)

    async for gclient in _google_client(_token_handler()):
        login = await gclient.get("/auth/google/login", follow_redirects=False)
        state0 = _extract_state(login.headers["location"])
        await gclient.get(
            "/auth/google/callback", params={"code": "c", "state": state0}, follow_redirects=False
        )

        connect = await gclient.get("/connected-accounts/google/connect", follow_redirects=False)
        state = _extract_state(connect.headers["location"])

        denied = await gclient.get(
            "/connected-accounts/google/callback",
            params={"error": "access_denied"},
            follow_redirects=False,
        )
        assert denied.status_code == 302
        assert "connect_error=access_denied" in denied.headers["location"]

        replay = await gclient.get(
            "/connected-accounts/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        assert "invalid_state" in replay.headers["location"]


# --- replay of an already-consumed callback ---------------------------------


async def test_replaying_a_consumed_signin_callback_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_verify(
        token: str, *, client_id: str, expected_nonce: str | None = None
    ) -> GoogleIdentity:
        return GoogleIdentity(subject="sub-replay", email="replay@example.com", email_verified=True)

    monkeypatch.setattr(auth_module, "verify_id_token", fake_verify)

    async for gclient in _google_client(_token_handler()):
        login = await gclient.get("/auth/google/login", follow_redirects=False)
        state = _extract_state(login.headers["location"])

        first = await gclient.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        assert first.status_code == 302
        assert "connections" in first.headers["location"]

        second = await gclient.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        assert "invalid_state" in second.headers["location"]


async def test_replaying_a_consumed_connector_callback_is_rejected() -> None:
    """Stage 11A Phase 4D §21: "callback replay" is a named emergency-stop
    trigger for the connector-consent flow specifically — the sign-in
    equivalent above proves the shared `consume_oauth_flow` mechanism, but
    the connector flow (the one this phase actually uses) had no direct
    end-to-end proof of its own."""
    async for gclient in _google_client(_token_handler()):
        login = await gclient.post(
            "/auth/dev-login",
            json={"email": "connector-replay@example.com", "display_name": "R"},
            headers=CSRF_HEADERS,
        )
        assert login.status_code == 200

        connect = await gclient.get("/connected-accounts/google/connect", follow_redirects=False)
        state = _extract_state(connect.headers["location"])

        first = await gclient.get(
            "/connected-accounts/google/callback",
            params={"code": "connector-code", "state": state},
            follow_redirects=False,
        )
        assert first.status_code == 302
        assert "connected=google" in first.headers["location"]

        second = await gclient.get(
            "/connected-accounts/google/callback",
            params={"code": "connector-code", "state": state},
            follow_redirects=False,
        )
        assert "invalid_state" in second.headers["location"]


# --- callback after logout --------------------------------------------------


async def test_connector_callback_after_logout_is_unauthorised() -> None:
    async for gclient in _google_client(_token_handler()):
        login = await gclient.post(
            "/auth/dev-login",
            json={"email": "logout-check@example.com", "display_name": "L"},
            headers=CSRF_HEADERS,
        )
        assert login.status_code == 200

        connect = await gclient.get("/connected-accounts/google/connect", follow_redirects=False)
        state = _extract_state(connect.headers["location"])

        await gclient.post("/auth/logout", headers=CSRF_HEADERS)

        callback = await gclient.get(
            "/connected-accounts/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        assert callback.status_code == 401


# --- malformed callback parameters ------------------------------------------


async def test_signin_callback_with_empty_state_is_rejected_not_crashed() -> None:
    async for gclient in _google_client(_token_handler()):
        await gclient.get("/auth/google/login", follow_redirects=False)
        callback = await gclient.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": ""},
            follow_redirects=False,
        )
        assert callback.status_code == 302
        assert "invalid_state" in callback.headers["location"]


async def test_signin_callback_with_repeated_state_param_is_rejected_not_crashed() -> None:
    async for gclient in _google_client(_token_handler()):
        await gclient.get("/auth/google/login", follow_redirects=False)
        callback = await gclient.get(
            "/auth/google/callback?state=first&state=second&code=c", follow_redirects=False
        )
        assert callback.status_code == 302
        location = callback.headers["location"]
        assert "invalid_state" in location or "missing_code" in location


# --- production guards, previously exercised only as a side effect --------
# (governing task §23: review production guards, add regression tests for
# any uncovered ones). Each guard below already existed and already worked
# — confirmed by inspection before writing these tests — but had no test
# asserting its specific error message, the same class of coverage gap as
# the `dev-1` key-id guard found during the Phase 4A merge-integrity check.


def test_missing_session_secret_refuses_to_start_in_production() -> None:
    settings = _test_settings("production")
    with pytest.raises(RuntimeError, match="SESSION_SECRET must be set in production"):
        create_app(settings)


def test_google_oauth_enabled_without_client_config_refuses_to_start() -> None:
    settings = _test_settings("development").model_copy(
        update={"google_oauth_enabled": True, "session_secret": "s" * 32}
    )
    with pytest.raises(RuntimeError, match="GOOGLE_OAUTH_ENABLED=true requires"):
        create_app(settings)


def test_google_oauth_enabled_without_token_key_refuses_to_start() -> None:
    settings = _test_settings("development").model_copy(
        update={
            **GOOGLE_SETTINGS_OVERRIDES,
            "google_oauth_enabled": True,
            "session_secret": "s" * 32,
            "token_key": "",
        }
    )
    with pytest.raises(RuntimeError, match="GOOGLE_OAUTH_ENABLED=true requires TOKEN_KEY"):
        create_app(settings)


# --- structural proofs: closed action model (governing task §6) ------------


def test_gmail_client_has_no_send_capable_method() -> None:
    """S11A-P4B-021/023: `gmail.compose` technically permits sending email;
    LifeFlow's own client surface must never expose that capability."""
    public_methods = {
        name
        for name, _ in inspect.getmembers(GmailDraftClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_methods == {
        "list_messages",
        "get_message",
        "list_history",
        "get_current_history_id",
        "get_profile_email",
        "create_draft",
        "get_draft",
    }
    for name in public_methods:
        assert "send" not in name.lower()
    # Check only the actual URL-construction call sites, not prose in
    # docstrings/comments that may legitimately mention "send" while
    # explaining why it is absent.
    call_sites = [
        line
        for line in inspect.getsource(GmailDraftClient).splitlines()
        if "_get(" in line or "_post(" in line or line.strip().startswith(('f"{self._base_url}',))
    ]
    assert call_sites, "expected at least one URL-construction call site"
    for line in call_sites:
        assert "send" not in line.lower()


def test_calendar_client_has_no_update_or_delete_method() -> None:
    """S11A-P4B-022/024: `calendar.events` technically permits updating or
    deleting any event on the calendar; LifeFlow's own client surface must
    never expose that capability — insert-only, by construction."""
    public_methods = {
        name
        for name, _ in inspect.getmembers(CalendarEventClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_methods == {
        "list_events",
        "insert_event",
        "get_event",
        "get_primary_calendar_metadata",
    }
    for forbidden in ("update", "patch", "delete"):
        assert forbidden not in public_methods
    source = inspect.getsource(CalendarEventClient)
    for verb in ("PATCH", "PUT", "DELETE"):
        assert verb not in source
