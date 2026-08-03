"""Stage 11A Phase 4C — configured Google clients stay disconnected.

All transports are local mocks. These tests prove that installing client
configuration does not itself permit a redirect, callback exchange, token
storage, or account binding, while the ordinary synthetic/demo path remains
available.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from tests.conftest import CSRF_HEADERS, _test_settings
from tests.test_google_auth_and_connections_api import GOOGLE_SETTINGS_OVERRIDES

from lifeflow_api.google.oauth import GoogleOAuthClient
from lifeflow_api.main import create_app
from lifeflow_api.models import ConnectedAccount
from lifeflow_api.oauth_initiation import OAUTH_INITIATION_BLOCKED_DETAIL

pytestmark = pytest.mark.integration


async def _blocked_client(
    handler: httpx.MockTransport,
) -> AsyncIterator[tuple[AsyncClient, FastAPI]]:
    settings = _test_settings("development").model_copy(
        update={
            **GOOGLE_SETTINGS_OVERRIDES,
            "google_oauth_initiation_enabled": False,
        }
    )
    app = create_app(settings)
    mock_http = httpx.AsyncClient(transport=handler)
    app.state.google_oauth_client = GoogleOAuthClient(mock_http)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, app
    await mock_http.aclose()


def _assert_blocked(response: httpx.Response) -> None:
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "conflict"
    assert error["message"] == OAUTH_INITIATION_BLOCKED_DETAIL
    assert error["dependency"] is None
    assert error["retryable"] is None
    assert "location" not in response.headers


async def test_configured_clients_cannot_start_either_oauth_flow() -> None:
    transport_calls = 0

    def should_not_run(request: httpx.Request) -> httpx.Response:
        nonlocal transport_calls
        transport_calls += 1
        raise AssertionError("OAuth transport must not run while initiation is blocked")

    async for client, _app in _blocked_client(httpx.MockTransport(should_not_run)):
        _assert_blocked(await client.get("/auth/google/login", follow_redirects=False))

        login = await client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
        assert login.status_code == 200
        _assert_blocked(
            await client.get("/connected-accounts/google/connect", follow_redirects=False)
        )

    assert transport_calls == 0


async def test_callbacks_are_blocked_before_code_exchange_or_token_storage() -> None:
    transport_calls = 0

    def should_not_run(request: httpx.Request) -> httpx.Response:
        nonlocal transport_calls
        transport_calls += 1
        raise AssertionError("callback must not exchange a code while initiation is blocked")

    async for client, app in _blocked_client(httpx.MockTransport(should_not_run)):
        login = await client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
        assert login.status_code == 200

        _assert_blocked(
            await client.get(
                "/auth/google/callback",
                params={"code": "synthetic-code", "state": "synthetic-state"},
                follow_redirects=False,
            )
        )
        _assert_blocked(
            await client.get(
                "/connected-accounts/google/callback",
                params={"code": "synthetic-code", "state": "synthetic-state"},
                follow_redirects=False,
            )
        )

        async with app.state.sessionmaker() as session:
            stored_accounts = await session.scalar(
                select(func.count()).select_from(ConnectedAccount)
            )
        assert stored_accounts == 0

    assert transport_calls == 0


async def test_demo_mode_remains_available_while_oauth_is_blocked() -> None:
    def should_not_run(request: httpx.Request) -> httpx.Response:
        raise AssertionError("demo mode must not touch the OAuth transport")

    async for client, _app in _blocked_client(httpx.MockTransport(should_not_run)):
        login = await client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
        assert login.status_code == 200
        demo = await client.post("/demo/start", headers=CSRF_HEADERS)
        assert demo.status_code == 200
        assert demo.json()["imported"] > 0


def test_initiation_flag_cannot_enable_an_unconfigured_integration() -> None:
    settings = _test_settings("development").model_copy(
        update={
            "google_oauth_enabled": False,
            "google_oauth_initiation_enabled": True,
        }
    )
    with pytest.raises(
        RuntimeError,
        match="GOOGLE_OAUTH_INITIATION_ENABLED=true requires GOOGLE_OAUTH_ENABLED=true",
    ):
        create_app(settings)
