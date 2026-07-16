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


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


async def check_database(engine: AsyncEngine) -> None:
    """Raise if the database is unreachable. Used by the readiness endpoint."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
