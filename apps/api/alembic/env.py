"""Alembic environment (async engine).

The database URL comes from the DATABASE_URL environment variable when set,
falling back to the development default in alembic.ini.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import lifeflow_api.models  # noqa: F401  — register all tables on Base.metadata
from lifeflow_api.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


_DEV_DEFAULT_URL = (
    "postgresql+asyncpg://lifeflow:lifeflow@localhost:5433/lifeflow"  # pragma: allowlist secret
)


def _database_url() -> str:
    return os.environ.get("DATABASE_URL") or _DEV_DEFAULT_URL


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_database_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
