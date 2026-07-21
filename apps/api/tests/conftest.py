import asyncio
import base64
import os
from collections.abc import AsyncIterator

import asyncpg
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from lifeflow_api.config import Settings
from lifeflow_api.db import Base
from lifeflow_api.main import create_app
from lifeflow_api.security.csrf import CSRF_HEADER

# Tests run against a dedicated database (lifeflow_test) on the dev Postgres
# container so they never touch development data.
DB_HOST, DB_PORT = "localhost", 5433
TEST_DB_URL = f"postgresql+asyncpg://lifeflow:lifeflow@{DB_HOST}:{DB_PORT}/lifeflow_test"  # pragma: allowlist secret

CSRF_HEADERS = {CSRF_HEADER: "1"}


def _test_settings(environment: str = "test") -> Settings:
    # `_env_file=None` deliberately skips the developer's local `.env` (now
    # that `config.py` resolves it correctly regardless of CWD, tests must
    # not become hermetic-by-accident any more — every field the test suite
    # cares about is set explicitly here, or must stay at its documented
    # off-by-default value, exactly as CI sees it).
    return Settings(
        _env_file=None,
        environment=environment,  # type: ignore[arg-type]
        log_level="WARNING",
        database_url=TEST_DB_URL,
        token_key=base64.b64encode(os.urandom(32)).decode(),
        token_key_id="test-1",
    )


TEST_SETTINGS = _test_settings()


@pytest.fixture(scope="session", autouse=True)
def test_database() -> None:
    """Create the lifeflow_test database and its schema once per session."""

    async def prepare() -> None:
        conn = await asyncpg.connect(
            user="lifeflow",
            password="lifeflow",  # pragma: allowlist secret
            database="lifeflow",
            host=DB_HOST,
            port=DB_PORT,
        )
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = 'lifeflow_test'")
        if not exists:
            await conn.execute("CREATE DATABASE lifeflow_test")
        await conn.close()

        engine = create_async_engine(TEST_DB_URL)
        async with engine.begin() as tx:
            await tx.run_sync(Base.metadata.drop_all)
            await tx.run_sync(Base.metadata.create_all)
        await engine.dispose()

    try:
        asyncio.run(prepare())
    except OSError:
        pytest.skip("PostgreSQL is not running (docker compose up -d db)")


@pytest.fixture(autouse=True)
async def clean_tables(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    """Empty all tables after each database-marked test."""
    yield
    if "integration" not in {mark.name for mark in request.node.iter_markers()}:
        return
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as tx:
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        await tx.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))
    await engine.dispose()


async def _make_client(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """App in the 'test' environment (dev-login disabled)."""
    async for c in _make_client(TEST_SETTINGS):
        yield c


@pytest.fixture
async def dev_client() -> AsyncIterator[AsyncClient]:
    """App in the 'development' environment (dev-login enabled)."""
    async for c in _make_client(_test_settings("development")):
        yield c
