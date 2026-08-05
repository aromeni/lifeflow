from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from tests.conftest import _test_settings
from tests.test_google_route_integration import GOOGLE_SETTINGS_OVERRIDES

from lifeflow_api.main import create_app


async def test_health_returns_ok_without_dependencies(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_config_reports_google_disabled_by_default(client: AsyncClient) -> None:
    """The `client` fixture never sets GOOGLE_OAUTH_ENABLED — the landing
    page must never be told to show a "Sign in with Google" button, nor the
    Connections page a "Connect Google" control, that would 404."""
    response = await client.get("/config")
    assert response.status_code == 200
    assert response.json() == {
        "google_provider_configured": False,
        "google_oidc_signin_enabled": False,
        "google_connector_oauth_enabled": False,
    }


async def test_config_reports_google_enabled_when_wired_and_both_flows_on() -> None:
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
    assert response.json() == {
        "google_provider_configured": True,
        "google_oidc_signin_enabled": True,
        "google_connector_oauth_enabled": True,
    }


async def test_config_reports_each_flow_independently_the_exact_phase_6_incident_configuration() -> (
    None
):
    """Stage 11A Phase 6A.1: reproduces the exact Phase 6 incident's flag
    configuration (connector consent authorised, OIDC sign-in not) and
    proves `/config` reports the two flows independently rather than
    collapsing them onto one boolean — the frontend discrepancy this phase
    fixes."""
    settings = _test_settings("development").model_copy(
        update={
            **GOOGLE_SETTINGS_OVERRIDES,
            "google_oidc_signin_enabled": False,
            "google_connector_oauth_enabled": True,
        }
    )
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as test_client:
            response = await test_client.get("/config")
    assert response.status_code == 200
    assert response.json() == {
        "google_provider_configured": True,
        "google_oidc_signin_enabled": False,
        "google_connector_oauth_enabled": True,
    }


async def test_config_never_reports_a_flow_enabled_when_provider_is_unconfigured() -> None:
    """A per-flow flag being `true` in `Settings` must never surface as
    `true` in `/config` if the provider itself isn't actually wired —
    matching `main.py`'s own startup guard, which refuses to even start in
    that combination. `/config` must not have an independent, weaker path
    to the same claim."""
    settings = _test_settings("development").model_copy(
        update={"google_oidc_signin_enabled": False, "google_connector_oauth_enabled": False}
    )
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as test_client:
            response = await test_client.get("/config")
    assert response.status_code == 200
    body = response.json()
    assert body["google_provider_configured"] is False
    assert body["google_oidc_signin_enabled"] is False
    assert body["google_connector_oauth_enabled"] is False
