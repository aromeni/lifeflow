import uuid

from httpx import AsyncClient


async def test_correlation_id_is_generated_when_absent(client: AsyncClient) -> None:
    response = await client.get("/health")
    correlation_id = response.headers["X-Correlation-ID"]
    uuid.UUID(correlation_id)  # generated IDs are UUIDs


async def test_supplied_correlation_id_is_echoed(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Correlation-ID": "req-12345"})
    assert response.headers["X-Correlation-ID"] == "req-12345"


async def test_invalid_correlation_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Correlation-ID": "a" * 300})
    replaced = response.headers["X-Correlation-ID"]
    assert replaced != "a" * 300
    uuid.UUID(replaced)
