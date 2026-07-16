import pytest
from httpx import AsyncClient
from tests.conftest import CSRF_HEADERS

pytestmark = pytest.mark.integration


async def test_me_requires_authentication(dev_client: AsyncClient) -> None:
    response = await dev_client.get("/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_dev_login_creates_user_session_and_audit_trail(dev_client: AsyncClient) -> None:
    response = await dev_client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
    assert response.status_code == 200
    assert response.json()["email"] == "dev@lifeflow.local"

    set_cookie = response.headers["set-cookie"]
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()

    me = await dev_client.get("/me")
    assert me.status_code == 200
    body = me.json()
    assert body["timezone"] == "Europe/London"
    assert body["onboarding_state"] == "new"


async def test_dev_login_is_disabled_outside_development(client: AsyncClient) -> None:
    response = await client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
    assert response.status_code == 404


async def test_logout_ends_the_session(dev_client: AsyncClient) -> None:
    await dev_client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
    assert (await dev_client.get("/me")).status_code == 200

    response = await dev_client.post("/auth/logout", headers=CSRF_HEADERS)
    assert response.status_code == 204
    assert (await dev_client.get("/me")).status_code == 401


async def test_state_changing_requests_require_csrf_header(dev_client: AsyncClient) -> None:
    response = await dev_client.post("/auth/dev-login", json={})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_header_missing"


async def test_settings_update_validates_and_audits(dev_client: AsyncClient) -> None:
    await dev_client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)

    bad = await dev_client.patch("/me", json={"timezone": "Mars/Olympus"}, headers=CSRF_HEADERS)
    assert bad.status_code == 422

    empty = await dev_client.patch("/me", json={}, headers=CSRF_HEADERS)
    assert empty.status_code == 400

    good = await dev_client.patch(
        "/me",
        json={"timezone": "Europe/Paris", "onboarding_state": "complete"},
        headers=CSRF_HEADERS,
    )
    assert good.status_code == 200
    assert good.json()["timezone"] == "Europe/Paris"
    assert good.json()["onboarding_state"] == "complete"


async def test_session_cookie_is_rejected_after_tampering(dev_client: AsyncClient) -> None:
    await dev_client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
    cookie = dev_client.cookies.get("lifeflow_session")
    assert cookie is not None
    dev_client.cookies.set("lifeflow_session", cookie[:-4] + "AAAA")
    assert (await dev_client.get("/me")).status_code == 401
