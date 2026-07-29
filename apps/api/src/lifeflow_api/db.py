"""Database engine and metadata.

Domain models arrive in Stage 2; this module owns the async engine and the
declarative base they will attach to. Alembic reads the same metadata for
autogeneration.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def create_engine(database_url: str, *, statement_timeout_ms: str | None = None) -> AsyncEngine:
    """Stage 9 Delivery Phase 5: `statement_timeout_ms` bounds every query
    (asyncpg's `server_settings`, applied once per connection) so a stuck
    query can never hold a pool connection — and therefore a request or
    worker job — indefinitely. `None` (the default, used by every existing
    test that doesn't pass it) leaves Postgres's own default unset, exactly
    the prior behaviour."""
    connect_args = {"server_settings": {"statement_timeout": statement_timeout_ms}}
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        connect_args=connect_args if statement_timeout_ms is not None else {},
    )


async def check_database(engine: AsyncEngine) -> None:
    """Raise if the database is unreachable. Used by the readiness endpoint."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
