"""Stage 9 Delivery Phase 2: real-Redis queue behaviour for the deletion
engine (ADR 0005 §9/§10).

Covers only what genuinely needs a live queue: that a `pending` operation is
drained onto Redis with a payload that is JSON and contains nothing but the
operation id (never scope, counts, confirmation text, or personal data), and
that the drained job runs the operation to completion. The database-owned
behaviour (planner, lifecycle, recovery) is covered with no Redis in
`test_deletion_engine.py`.

Requires: `docker compose up -d redis --wait`.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import redis.exceptions as redis_exceptions
from arq.connections import ArqRedis, RedisSettings, create_pool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL

from lifeflow_api.deletion import (
    confirm_operation,
    create_imported_data_preview,
    recover_stale_operations,
    run_operation,
)
from lifeflow_api.deletion_ops import (
    CONFIRM_IMPORTED_DATA,
    JOB_FUNCTION_NAME,
    job_deserializer,
    job_serializer,
)
from lifeflow_api.models import (
    ConnectedAccount,
    DeletionOperationState,
    SourceItem,
    User,
)
from lifeflow_api.retention import RetentionHorizons

pytestmark = pytest.mark.integration

REDIS_SETTINGS = RedisSettings(host="localhost", port=6380)
NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
HORIZONS = RetentionHorizons(
    source_items_days=30,
    brief_versions_days=90,
    unapproved_proposals_days=90,
    scheduled_runs_days=90,
    memory_evidence_days=90,
)


@pytest.fixture
async def redis() -> AsyncIterator[ArqRedis]:
    try:
        pool = await create_pool(
            REDIS_SETTINGS, job_serializer=job_serializer, job_deserializer=job_deserializer
        )
    except (OSError, redis_exceptions.RedisError):
        pytest.skip("Redis is not running (docker compose up -d redis --wait)")
    await pool.flushdb()
    try:
        yield pool
    finally:
        await pool.flushdb()
        await pool.aclose()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _seed(session: AsyncSession) -> tuple[User, ConnectedAccount]:
    user = User(email=f"q-{uuid.uuid4()}@example.com", display_name="Q")
    session.add(user)
    await session.flush()
    account = ConnectedAccount(user_id=user.id, provider="google", granted_scopes=[])
    session.add(account)
    await session.flush()
    for i in range(3):
        session.add(
            SourceItem(
                user_id=user.id,
                source_type="email",
                external_id=f"em-{i}",
                source_account_id=account.id,
                title="t",
                sender_or_organiser="x@example.com",
                occurred_at=NOW,
                content_fingerprint=f"fp-{i}",
                created_at=NOW,
            )
        )
    await session.flush()
    return user, account


async def _confirm(session: AsyncSession, user: User, account: ConnectedAccount) -> uuid.UUID:
    op = await create_imported_data_preview(
        session, user, source_account_id=account.id, now=NOW, ttl_minutes=30
    )
    confirmed = await confirm_operation(
        session,
        user,
        op.id,
        expected_version=op.version,
        phrase=CONFIRM_IMPORTED_DATA,
        now=NOW,
        preview_ttl_minutes=30,
    )
    await session.commit()
    return confirmed.id


async def test_pending_operation_drains_with_id_only_payload(
    session: AsyncSession, redis: ArqRedis
) -> None:
    user, account = await _seed(session)
    operation_id = await _confirm(session, user, account)

    result = await recover_stale_operations(
        session, redis, now=NOW, heartbeat_timeout=timedelta(minutes=10), max_attempts=3
    )
    assert result.drained == 1

    jobs = await redis.queued_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.function == JOB_FUNCTION_NAME
    # The payload is exactly the operation id and nothing else (JSON decodes
    # the args tuple as a list).
    assert list(job.args) == [str(operation_id)]
    assert user.email not in str(job.args)


async def test_drained_operation_runs_to_completion(session: AsyncSession, redis: ArqRedis) -> None:
    user, account = await _seed(session)
    operation_id = await _confirm(session, user, account)
    await recover_stale_operations(
        session, redis, now=NOW, heartbeat_timeout=timedelta(minutes=10), max_attempts=3
    )
    # Run the job body (what the worker invokes for the drained job).
    await run_operation(
        session, operation_id, now=NOW, horizons=HORIZONS, batch_size=2, max_attempts=3
    )
    remaining = int(
        (
            await session.execute(
                select(func.count()).select_from(SourceItem).where(SourceItem.user_id == user.id)
            )
        ).scalar_one()
    )
    assert remaining == 0
    from lifeflow_api.models import DataDeletionOperation

    final = await session.get(DataDeletionOperation, operation_id, populate_existing=True)
    assert final is not None and final.state == DeletionOperationState.succeeded
