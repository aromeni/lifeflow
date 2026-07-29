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
    """Requires PostgreSQL from docker compose up -d db. The default test
    settings also point at a real Redis (docker compose up -d redis), so
    the healthy case reports no degraded dependencies."""
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "degraded_dependencies": []}


@pytest.mark.integration
async def test_ready_reports_redis_degraded_without_failing_readiness() -> None:
    """Stage 9 Delivery Phase 5 (§12): Redis is a fail-open, optional
    dependency (ADR 0005 D64) — its absence must be reported honestly but
    must never flip readiness to unavailable, since the API's core
    functions (backed by PostgreSQL) remain fully usable without it."""
    settings = Settings(
        environment="test",
        log_level="WARNING",
        redis_url="redis://127.0.0.1:1/0",  # a port nothing listens on
    )
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "degraded_dependencies": ["redis"]}
