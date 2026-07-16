from httpx import AsyncClient


async def test_not_found_uses_shared_error_shape(client: AsyncClient) -> None:
    response = await client.get("/no-such-route")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["correlation_id"] == response.headers["X-Correlation-ID"]


async def test_error_correlation_id_matches_supplied_header(client: AsyncClient) -> None:
    response = await client.get("/no-such-route", headers={"X-Correlation-ID": "trace-42"})
    assert response.json()["error"]["correlation_id"] == "trace-42"
