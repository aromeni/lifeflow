"""Stage 11A Phase 6A — independent Google OAuth flow gating.

A real Phase 6 incident: `google_oauth_initiation_enabled` was one flag
shared by both the OIDC sign-in flow and the connector-consent flow.
Enabling it to authorise a connector reconnection necessarily also armed
sign-in, and the owner completed a real (contained, Account-A-only) OIDC
sign-in as a result. This file proves the replacement — two independent
flags, `google_oidc_signin_enabled` and `google_connector_oauth_enabled` —
actually closes that gap, across every relevant configuration combination,
and reproduces the exact incident as a named regression test.

All transports are local mocks; no real Google network call is ever made.
"""

from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from tests.conftest import CSRF_HEADERS, _test_settings
from tests.test_google_auth_and_connections_api import GOOGLE_SETTINGS_OVERRIDES, _token_handler

from lifeflow_api.google.oauth import GoogleOAuthClient
from lifeflow_api.main import create_app
from lifeflow_api.oauth_initiation import (
    GOOGLE_CONNECTOR_OAUTH_BLOCKED_DETAIL,
    GOOGLE_OIDC_SIGNIN_BLOCKED_DETAIL,
)

pytestmark = pytest.mark.integration


async def _client_with(
    *, mock_transport: httpx.MockTransport, **overrides: object
) -> AsyncIterator[AsyncClient]:
    settings = _test_settings("development").model_copy(
        update={**GOOGLE_SETTINGS_OVERRIDES, **overrides}
    )
    app = create_app(settings)
    mock_http = httpx.AsyncClient(transport=mock_transport)
    app.state.google_oauth_client = GoogleOAuthClient(mock_http)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    await mock_http.aclose()


def _extract_state(location: str) -> str:
    return parse_qs(urlparse(location).query)["state"][0]


def _assert_signin_available(response: httpx.Response) -> None:
    assert response.status_code == 302
    assert "accounts.google.com" in response.headers["location"]


def _assert_signin_blocked(response: httpx.Response) -> None:
    assert response.status_code == 409
    assert response.json()["error"]["message"] == GOOGLE_OIDC_SIGNIN_BLOCKED_DETAIL
    assert "location" not in response.headers


def _assert_connector_available(response: httpx.Response) -> None:
    assert response.status_code == 302
    assert "accounts.google.com" in response.headers["location"]


def _assert_connector_blocked(response: httpx.Response) -> None:
    assert response.status_code == 409
    assert response.json()["error"]["message"] == GOOGLE_CONNECTOR_OAUTH_BLOCKED_DETAIL
    assert "location" not in response.headers


# --- Configuration truth table -----------------------------------------


async def test_both_flows_disabled_blocks_both() -> None:
    async for client in _client_with(
        mock_transport=_token_handler(),
        google_oidc_signin_enabled=False,
        google_connector_oauth_enabled=False,
    ):
        _assert_signin_blocked(await client.get("/auth/google/login", follow_redirects=False))
        login = await client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
        assert login.status_code == 200
        _assert_connector_blocked(
            await client.get("/connected-accounts/google/connect", follow_redirects=False)
        )


async def test_signin_enabled_connector_disabled() -> None:
    async for client in _client_with(
        mock_transport=_token_handler(),
        google_oidc_signin_enabled=True,
        google_connector_oauth_enabled=False,
    ):
        _assert_signin_available(await client.get("/auth/google/login", follow_redirects=False))
        login = await client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
        assert login.status_code == 200
        _assert_connector_blocked(
            await client.get("/connected-accounts/google/connect", follow_redirects=False)
        )


async def test_signin_disabled_connector_enabled_the_exact_phase_6_incident_now_fixed() -> None:
    """Reproduces the exact Phase 6 incident: connector consent enabled,
    OIDC sign-in deliberately left disabled, then a sign-in attempt.
    Before Phase 6A this succeeded (the shared flag armed both flows); it
    must now be blocked before any redirect or state creation."""
    async for client in _client_with(
        mock_transport=_token_handler(),
        google_oidc_signin_enabled=False,
        google_connector_oauth_enabled=True,
    ):
        _assert_signin_blocked(await client.get("/auth/google/login", follow_redirects=False))

        login = await client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
        assert login.status_code == 200
        _assert_connector_available(
            await client.get("/connected-accounts/google/connect", follow_redirects=False)
        )


async def test_both_flows_enabled_both_available_and_still_isolated() -> None:
    async for client in _client_with(
        mock_transport=_token_handler(),
        google_oidc_signin_enabled=True,
        google_connector_oauth_enabled=True,
    ):
        _assert_signin_available(await client.get("/auth/google/login", follow_redirects=False))
        login = await client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
        assert login.status_code == 200
        _assert_connector_available(
            await client.get("/connected-accounts/google/connect", follow_redirects=False)
        )


async def test_provider_not_configured_blocks_both_regardless_of_per_flow_flags() -> None:
    """The master flag is a real prerequisite, not a formality: the startup
    guard (proven separately in `test_malformed_configuration_fails_startup_
    for_each_flag`) already refuses to even start with a per-flow flag
    enabled and the provider unconfigured. With the provider unconfigured
    and both per-flow flags left at their only reachable state here (their
    safe default, `false`), both routes are still blocked — never inferring
    availability from anything other than their own flag."""
    settings = _test_settings("development").model_copy(update={"google_oauth_enabled": False})
    app = create_app(settings)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (
                await client.get("/auth/google/login", follow_redirects=False)
            ).status_code == 404
            login = await client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
            assert login.status_code == 200
            assert (
                await client.get("/connected-accounts/google/connect", follow_redirects=False)
            ).status_code == 404


# --- Independence: enabling one flag must never enable the other -------


async def test_connector_enablement_never_enables_signin() -> None:
    async for client in _client_with(
        mock_transport=_token_handler(),
        google_oidc_signin_enabled=False,
        google_connector_oauth_enabled=True,
    ):
        _assert_signin_blocked(await client.get("/auth/google/login", follow_redirects=False))
        _assert_signin_blocked(
            await client.get(
                "/auth/google/callback",
                params={"code": "c", "state": "s"},
                follow_redirects=False,
            )
        )


async def test_signin_enablement_never_enables_connector() -> None:
    async for client in _client_with(
        mock_transport=_token_handler(),
        google_oidc_signin_enabled=True,
        google_connector_oauth_enabled=False,
    ):
        login = await client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
        assert login.status_code == 200
        _assert_connector_blocked(
            await client.get("/connected-accounts/google/connect", follow_redirects=False)
        )
        _assert_connector_blocked(
            await client.get(
                "/connected-accounts/google/callback",
                params={"code": "c", "state": "s"},
                follow_redirects=False,
            )
        )


# --- Cross-flow OAuth-state isolation (pre-existing `purpose` binding, ---
# --- reconfirmed fresh against the newly-split gates) --------------------


async def test_signin_state_cannot_be_consumed_by_the_connector_callback() -> None:
    async for client in _client_with(
        mock_transport=_token_handler(),
        google_oidc_signin_enabled=True,
        google_connector_oauth_enabled=True,
    ):
        login = await client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
        assert login.status_code == 200
        signin_redirect = await client.get("/auth/google/login", follow_redirects=False)
        signin_state = _extract_state(signin_redirect.headers["location"])

        cross_flow = await client.get(
            "/connected-accounts/google/callback",
            params={"code": "attacker-supplied-code", "state": signin_state},
            follow_redirects=False,
        )
        assert cross_flow.status_code == 302
        assert "invalid_state" in cross_flow.headers["location"]


async def test_connector_state_cannot_be_consumed_by_the_signin_callback() -> None:
    async for client in _client_with(
        mock_transport=_token_handler(),
        google_oidc_signin_enabled=True,
        google_connector_oauth_enabled=True,
    ):
        login = await client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
        assert login.status_code == 200
        connect_redirect = await client.get(
            "/connected-accounts/google/connect", follow_redirects=False
        )
        connector_state = _extract_state(connect_redirect.headers["location"])

        cross_flow = await client.get(
            "/auth/google/callback",
            params={"code": "attacker-supplied-code", "state": connector_state},
            follow_redirects=False,
        )
        assert cross_flow.status_code == 302
        assert "invalid_state" in cross_flow.headers["location"]


# --- Startup validation for the new flags --------------------------------


def test_malformed_configuration_fails_startup_for_each_flag() -> None:
    for flag in ("google_oidc_signin_enabled", "google_connector_oauth_enabled"):
        settings = _test_settings("development").model_copy(
            update={"google_oauth_enabled": False, flag: True}
        )
        with pytest.raises(RuntimeError, match="requires GOOGLE_OAUTH_ENABLED=true"):
            create_app(settings)


def test_defaults_are_disabled() -> None:
    settings = _test_settings("development")
    assert settings.google_oidc_signin_enabled is False
    assert settings.google_connector_oauth_enabled is False
