"""Demo mode through the API: start, list, re-run (Stage 3)."""

import pytest
from httpx import AsyncClient
from tests.conftest import CSRF_HEADERS

pytestmark = pytest.mark.integration


async def _login(client: AsyncClient) -> None:
    response = await client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
    assert response.status_code == 200


async def test_demo_start_requires_authentication(dev_client: AsyncClient) -> None:
    response = await dev_client.post("/demo/start", headers=CSRF_HEADERS)
    assert response.status_code == 401


async def test_demo_start_imports_the_dataset(dev_client: AsyncClient) -> None:
    await _login(dev_client)
    response = await dev_client.post("/demo/start", headers=CSRF_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] > 0
    assert body["imported"] + body["skipped"] + body["updated"] <= 36


async def test_demo_start_twice_does_not_duplicate(dev_client: AsyncClient) -> None:
    await _login(dev_client)
    first = (await dev_client.post("/demo/start", headers=CSRF_HEADERS)).json()
    second = (await dev_client.post("/demo/start", headers=CSRF_HEADERS)).json()
    assert second["imported"] == 0
    assert second["skipped"] == first["imported"]


async def test_source_items_listing_and_filtering(dev_client: AsyncClient) -> None:
    await _login(dev_client)
    await dev_client.post("/demo/start", headers=CSRF_HEADERS)

    everything = (await dev_client.get("/source-items", params={"limit": 500})).json()
    emails = (
        await dev_client.get("/source-items", params={"source_type": "email", "limit": 500})
    ).json()
    events = (
        await dev_client.get(
            "/source-items", params={"source_type": "calendar_event", "limit": 500}
        )
    ).json()

    assert everything["count"] == emails["count"] + events["count"]
    assert all(item["source_type"] == "email" for item in emails["items"])
    assert all(item["source_type"] == "calendar_event" for item in events["items"])
    # Normalised items carry evidence-ready metadata.
    sample = emails["items"][0]
    assert {"id", "title", "sender_or_organiser", "occurred_at", "metadata"} <= set(sample)


async def test_source_items_require_authentication(dev_client: AsyncClient) -> None:
    response = await dev_client.get("/source-items")
    assert response.status_code == 401
