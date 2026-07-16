import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from lifeflow_api.config import Settings
from lifeflow_api.main import create_app


async def test_ready_returns_503_when_database_is_unreachable() -> None:
    settings = Settings(
        environment="test",
        log_level="WARNING",
        # A port nothing listens on — connection must fail fast, not hang.
        database_url="postgresql+asyncpg://lifeflow:lifeflow@127.0.0.1:59999/lifeflow",  # pragma: allowlist secret
    )
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


@pytest.mark.integration
async def test_ready_returns_ok_with_running_database(client: AsyncClient) -> None:
    """Requires PostgreSQL from docker compose up -d db."""
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
