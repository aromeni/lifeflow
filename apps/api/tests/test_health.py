from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from tests.conftest import _test_settings
from tests.test_google_route_integration import GOOGLE_SETTINGS_OVERRIDES

from lifeflow_api.main import create_app


async def test_health_returns_ok_without_dependencies(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_config_reports_google_oauth_disabled_by_default(client: AsyncClient) -> None:
    """The `client` fixture never sets GOOGLE_OAUTH_ENABLED — the landing
    page must never be told to show a "Sign in with Google" button that
    would 404."""
    response = await client.get("/config")
    assert response.status_code == 200
    assert response.json() == {"google_oauth_enabled": False}


async def test_config_reports_google_oauth_enabled_when_wired() -> None:
    """When GOOGLE_OAUTH_ENABLED=true and both OAuth client configs are
    present, `create_app` (ADR 0003 D23) constructs real client objects on
    `app.state` before this route ever runs — `/config` reuses the exact
    same `google_integration_ready` check the sync/execute routes gate on,
    so it can never drift from what those routes would actually do."""
    settings = _test_settings("development").model_copy(update=GOOGLE_SETTINGS_OVERRIDES)
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as test_client:
            response = await test_client.get("/config")
    assert response.status_code == 200
    assert response.json() == {"google_oauth_enabled": True}
