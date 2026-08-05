"""Stage 7: HTTP-level Google sign-in (auth.py) and connector-consent
(connected_accounts.py) flows. `verify_id_token` is monkeypatched at the
point of use in `auth.py` so no real network/JWKS call is ever attempted;
Google's token/API endpoints are replaced with `httpx.MockTransport` on the
app instance. Never real network.
"""

from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL, _test_settings

import lifeflow_api.auth as auth_module
from lifeflow_api.google.oauth import GoogleIdentity, GoogleOAuthClient
from lifeflow_api.main import create_app
from lifeflow_api.models import AccountStatus, User
from lifeflow_api.repositories import ConnectedAccountRepository

pytestmark = pytest.mark.integration

GOOGLE_SETTINGS_OVERRIDES = {
    "google_oauth_enabled": True,
    "google_oidc_signin_enabled": True,
    "google_connector_oauth_enabled": True,
    "google_oidc_client_id": "oidc-id",
    "google_oidc_client_secret": "oidc-secret",
    "google_oidc_redirect_uri": "http://localhost:8010/auth/google/callback",
    "google_connector_client_id": "conn-id",
    "google_connector_client_secret": "conn-secret",
    "google_connector_redirect_uri": "http://localhost:8010/connected-accounts/google/callback",
}


def _token_handler(id_token: str = "id-token-stub") -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/gmail.readonly "
                "https://www.googleapis.com/auth/gmail.compose",
                "id_token": id_token,
            },
        )

    return httpx.MockTransport(handle)


def _token_handler_with_unreachable_revoke(id_token: str = "id-token-stub") -> httpx.MockTransport:
    """Same token/exchange behaviour as `_token_handler`, but Google's
    `/revoke` endpoint is genuinely unreachable — a connection error, not a
    mocked-success shortcut — so the disconnect test below actually proves
    D20 (local disconnect never depends on Google being reachable)."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/revoke":
            raise httpx.ConnectError("network down", request=request)
        return httpx.Response(
            200,
            json={
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/gmail.readonly "
                "https://www.googleapis.com/auth/gmail.compose",
                "id_token": id_token,
            },
        )

    return httpx.MockTransport(handle)


async def _google_client(mock_transport: httpx.MockTransport) -> AsyncIterator[AsyncClient]:
    settings = _test_settings("development").model_copy(update=GOOGLE_SETTINGS_OVERRIDES)
    app = create_app(settings)
    mock_http = httpx.AsyncClient(transport=mock_transport)
    app.state.google_oauth_client = GoogleOAuthClient(mock_http)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
async def google_client() -> AsyncIterator[AsyncClient]:
    async for c in _google_client(_token_handler()):
        yield c


def _extract_state(location: str) -> str:
    return parse_qs(urlparse(location).query)["state"][0]


async def test_google_signin_route_is_404_when_disabled(client: AsyncClient) -> None:
    assert (await client.get("/auth/google/login", follow_redirects=False)).status_code == 404


async def test_google_connect_route_is_404_when_disabled_for_a_signed_in_user(
    dev_client: AsyncClient,
) -> None:
    login = await dev_client.post(
        "/auth/dev-login",
        json={"email": "disabled-check@example.com", "display_name": "D"},
        headers=CSRF_HEADERS,
    )
    assert login.status_code == 200
    response = await dev_client.get("/connected-accounts/google/connect", follow_redirects=False)
    assert response.status_code == 404


async def test_login_redirect_requests_openid_scope_only(google_client: AsyncClient) -> None:
    response = await google_client.get("/auth/google/login", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    params = parse_qs(urlparse(location).query)
    assert params["scope"][0] == "openid email profile"
    assert params["code_challenge_method"][0] == "S256"


async def test_login_redirect_carries_a_nonce(google_client: AsyncClient) -> None:
    response = await google_client.get("/auth/google/login", follow_redirects=False)
    params = parse_qs(urlparse(response.headers["location"]).query)
    assert len(params["nonce"][0]) > 0


async def test_connect_redirect_never_carries_a_nonce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The connector-consent flow never exchanges an ID token, so it has
    nothing to bind a nonce to."""

    async def fake_verify(
        token: str, *, client_id: str, expected_nonce: str | None = None
    ) -> GoogleIdentity:
        return GoogleIdentity(
            subject="sub-nonce", email="nonce-check@example.com", email_verified=True
        )

    monkeypatch.setattr(auth_module, "verify_id_token", fake_verify)

    async for gclient in _google_client(_token_handler()):
        login = await gclient.get("/auth/google/login", follow_redirects=False)
        state = _extract_state(login.headers["location"])
        await gclient.get(
            "/auth/google/callback", params={"code": "c", "state": state}, follow_redirects=False
        )

        connect = await gclient.get("/connected-accounts/google/connect", follow_redirects=False)
        assert "nonce" not in parse_qs(urlparse(connect.headers["location"]).query)


async def test_signin_callback_creates_user_by_google_subject(
    google_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_verify(
        token: str, *, client_id: str, expected_nonce: str | None = None
    ) -> GoogleIdentity:
        return GoogleIdentity(subject="sub-1", email="new-user@example.com", email_verified=True)

    monkeypatch.setattr(auth_module, "verify_id_token", fake_verify)

    login = await google_client.get("/auth/google/login", follow_redirects=False)
    state = _extract_state(login.headers["location"])

    callback = await google_client.get(
        "/auth/google/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    # Sign-in only establishes identity; the next step is connecting Gmail/
    # Calendar, so success lands on Connections, not an empty Today.
    assert callback.headers["location"] == "http://localhost:3000/connections"

    me = await google_client.get("/me")
    assert me.status_code == 200
    assert me.json()["email"] == "new-user@example.com"


async def test_signin_reuses_existing_user_by_subject_on_second_login(
    google_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_verify(
        token: str, *, client_id: str, expected_nonce: str | None = None
    ) -> GoogleIdentity:
        return GoogleIdentity(subject="sub-2", email="returning@example.com", email_verified=True)

    monkeypatch.setattr(auth_module, "verify_id_token", fake_verify)

    for _ in range(2):
        login = await google_client.get("/auth/google/login", follow_redirects=False)
        state = _extract_state(login.headers["location"])
        await google_client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

    engine = create_async_engine(TEST_DB_URL)
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as reader:
            result = await reader.execute(select(User).where(User.google_subject == "sub-2"))
            users = result.scalars().all()
            assert len(users) == 1
    finally:
        await engine.dispose()


async def test_signin_rejects_unverified_email(
    google_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_verify(
        token: str, *, client_id: str, expected_nonce: str | None = None
    ) -> GoogleIdentity:
        raise Exception("simulated: email_verified is false")

    monkeypatch.setattr(auth_module, "verify_id_token", fake_verify)

    login = await google_client.get("/auth/google/login", follow_redirects=False)
    state = _extract_state(login.headers["location"])
    callback = await google_client.get(
        "/auth/google/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert "auth_error" in callback.headers["location"]


async def test_signin_conflicting_email_gets_safe_error_not_a_crash(
    google_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D15 correction: users.email is globally unique; a colliding email
    with no matching google_subject must fail safely, never merge or 500."""
    login1 = await google_client.get("/auth/google/login", follow_redirects=False)
    state1 = _extract_state(login1.headers["location"])

    async def fake_verify_a(
        token: str, *, client_id: str, expected_nonce: str | None = None
    ) -> GoogleIdentity:
        return GoogleIdentity(subject="sub-a", email="shared@example.com", email_verified=True)

    monkeypatch.setattr(auth_module, "verify_id_token", fake_verify_a)
    await google_client.get(
        "/auth/google/callback", params={"code": "code-a", "state": state1}, follow_redirects=False
    )

    login2 = await google_client.get("/auth/google/login", follow_redirects=False)
    state2 = _extract_state(login2.headers["location"])

    async def fake_verify_b(
        token: str, *, client_id: str, expected_nonce: str | None = None
    ) -> GoogleIdentity:
        return GoogleIdentity(subject="sub-b", email="shared@example.com", email_verified=True)

    monkeypatch.setattr(auth_module, "verify_id_token", fake_verify_b)
    callback2 = await google_client.get(
        "/auth/google/callback", params={"code": "code-b", "state": state2}, follow_redirects=False
    )
    assert callback2.status_code == 302
    assert "email_already_registered" in callback2.headers["location"]


async def test_callback_with_invalid_state_redirects_safely(google_client: AsyncClient) -> None:
    await google_client.get("/auth/google/login", follow_redirects=False)
    callback = await google_client.get(
        "/auth/google/callback",
        params={"code": "auth-code", "state": "not-the-real-state"},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert "invalid_state" in callback.headers["location"]


async def test_connector_connect_requires_signed_in_user(client: AsyncClient) -> None:
    response = await client.get("/connected-accounts/google/connect", follow_redirects=False)
    assert response.status_code == 401


async def test_connector_connect_requests_exact_four_data_scopes(
    google_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_verify(
        token: str, *, client_id: str, expected_nonce: str | None = None
    ) -> GoogleIdentity:
        return GoogleIdentity(subject="sub-3", email="connector@example.com", email_verified=True)

    monkeypatch.setattr(auth_module, "verify_id_token", fake_verify)
    login = await google_client.get("/auth/google/login", follow_redirects=False)
    state = _extract_state(login.headers["location"])
    await google_client.get(
        "/auth/google/callback", params={"code": "c", "state": state}, follow_redirects=False
    )

    connect = await google_client.get("/connected-accounts/google/connect", follow_redirects=False)
    assert connect.status_code == 302
    params = parse_qs(urlparse(connect.headers["location"]).query)
    assert params["scope"][0] == (
        "https://www.googleapis.com/auth/gmail.readonly "
        "https://www.googleapis.com/auth/gmail.compose "
        "https://www.googleapis.com/auth/calendar.readonly "
        "https://www.googleapis.com/auth/calendar.events"
    )
    assert params["access_type"][0] == "offline"
    assert params["prompt"][0] == "consent"


async def test_connector_connect_redirect_also_carries_pkce(
    google_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The connector-consent flow shares `begin_oauth_flow`/
    `build_authorization_url` with OIDC sign-in and therefore always sends
    PKCE too — closing a documentation gap (Stage 11A Phase 4B recorded this
    flow as lacking PKCE, which was never true of the code; corrected during
    the Phase 4C integrity check)."""

    async def fake_verify(
        token: str, *, client_id: str, expected_nonce: str | None = None
    ) -> GoogleIdentity:
        return GoogleIdentity(subject="sub-pkce", email="pkce@example.com", email_verified=True)

    monkeypatch.setattr(auth_module, "verify_id_token", fake_verify)
    login = await google_client.get("/auth/google/login", follow_redirects=False)
    state = _extract_state(login.headers["location"])
    await google_client.get(
        "/auth/google/callback", params={"code": "c", "state": state}, follow_redirects=False
    )

    connect = await google_client.get("/connected-accounts/google/connect", follow_redirects=False)
    assert connect.status_code == 302
    params = parse_qs(urlparse(connect.headers["location"]).query)
    assert params["code_challenge_method"][0] == "S256"
    assert len(params["code_challenge"][0]) > 0


async def test_connector_callback_stores_only_actually_granted_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T20: a partial grant (user deselects a scope) must be recorded
    honestly — never the requested set."""

    async def fake_verify(
        token: str, *, client_id: str, expected_nonce: str | None = None
    ) -> GoogleIdentity:
        return GoogleIdentity(subject="sub-4", email="partial@example.com", email_verified=True)

    monkeypatch.setattr(auth_module, "verify_id_token", fake_verify)

    async for gclient in _google_client(_token_handler()):
        login = await gclient.get("/auth/google/login", follow_redirects=False)
        state = _extract_state(login.headers["location"])
        await gclient.get(
            "/auth/google/callback", params={"code": "c", "state": state}, follow_redirects=False
        )

        connect = await gclient.get("/connected-accounts/google/connect", follow_redirects=False)
        connector_state = _extract_state(connect.headers["location"])
        callback = await gclient.get(
            "/connected-accounts/google/callback",
            params={"code": "c2", "state": connector_state},
            follow_redirects=False,
        )
        assert callback.status_code == 302

        accounts = await gclient.get("/connected-accounts")
        body = accounts.json()["accounts"]
        assert len(body) == 1
        assert set(body[0]["granted_scopes"]) == {
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.compose",
        }
        break


async def test_disconnect_google_never_requires_google_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D20: a genuinely unreachable `/revoke` (connection error, not a mocked
    200) must never block the local disconnect — and the account must
    actually be connected first, so there is a real refresh token this test
    proves gets cleared locally despite Google being unreachable."""

    async def fake_verify(
        token: str, *, client_id: str, expected_nonce: str | None = None
    ) -> GoogleIdentity:
        return GoogleIdentity(subject="sub-5", email="disconnect@example.com", email_verified=True)

    monkeypatch.setattr(auth_module, "verify_id_token", fake_verify)

    async for gclient in _google_client(_token_handler_with_unreachable_revoke()):
        login = await gclient.get("/auth/google/login", follow_redirects=False)
        state = _extract_state(login.headers["location"])
        await gclient.get(
            "/auth/google/callback", params={"code": "c", "state": state}, follow_redirects=False
        )

        connect = await gclient.get("/connected-accounts/google/connect", follow_redirects=False)
        connector_state = _extract_state(connect.headers["location"])
        connected = await gclient.get(
            "/connected-accounts/google/callback",
            params={"code": "c2", "state": connector_state},
            follow_redirects=False,
        )
        assert connected.status_code == 302

        before = await gclient.get("/connected-accounts")
        assert before.json()["accounts"][0]["status"] == "active"

        response = await gclient.post("/connected-accounts/google/disconnect", headers=CSRF_HEADERS)
        assert response.status_code == 204

        engine = create_async_engine(TEST_DB_URL)
        try:
            from sqlalchemy.ext.asyncio import async_sessionmaker

            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as reader:
                result = await reader.execute(select(User).where(User.google_subject == "sub-5"))
                user = result.scalar_one()
                account = await ConnectedAccountRepository(reader, user.id).get_by_provider(
                    "google"
                )
                assert account is not None
                assert account.status == AccountStatus.disconnected
                assert account.encrypted_access_token is None
                assert account.encrypted_refresh_token is None
        finally:
            await engine.dispose()

        # Disconnecting again (nothing left connected) must not error either.
        response2 = await gclient.post(
            "/connected-accounts/google/disconnect", headers=CSRF_HEADERS
        )
        assert response2.status_code == 204
        break
