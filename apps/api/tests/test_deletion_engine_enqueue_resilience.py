"""Stage 9 Delivery Phase 5 (§11): a Redis blip during
`recover_stale_operations` must never abort the whole cron tick, and must
never lose an operation — before this fix, an uncaught
`redis.enqueue_job` exception propagated out of the function, rolling back
every operation's state change made earlier in the same loop (nothing had
committed yet)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import redis.exceptions as redis_exceptions
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL
from tests.test_deletion_engine import _seed_imported_dataset

from lifeflow_api.deletion import (
    confirm_operation,
    create_imported_data_preview,
    recover_stale_operations,
)
from lifeflow_api.deletion_ops import CONFIRM_IMPORTED_DATA
from lifeflow_api.models import (
    ConnectedAccount,
    DataDeletionOperation,
    DeletionOperationState,
    User,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


class _FlakyRedis:
    """A minimal `ArqRedis` stand-in whose `enqueue_job` always raises —
    modelling a Redis outage for exactly the operations this test cares
    about, distinct from `redis=None` (which the existing test suite
    already uses for the unrelated "no worker configured" case)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def enqueue_job(self, function: str, *args: object, **_: object) -> object:
        self.calls.append(str(args[0]) if args else "")
        raise redis_exceptions.ConnectionError("simulated Redis outage")


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


async def test_stale_recovery_survives_a_redis_failure_during_requeue(
    session: AsyncSession,
) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
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
    confirmed.state = DeletionOperationState.running
    confirmed.heartbeat_at = NOW - timedelta(minutes=30)
    confirmed.attempt_count = 1
    await session.commit()

    redis = _FlakyRedis()

    result = await recover_stale_operations(
        session, redis, now=NOW, heartbeat_timeout=timedelta(minutes=10), max_attempts=3
    )

    # The state transition itself (running -> pending) still happens even
    # though the enqueue failed — it's the whole point of `requeued`
    # reflecting the DB decision, not enqueue success.
    assert result.requeued == 1
    reloaded = await session.get(DataDeletionOperation, confirmed.id, populate_existing=True)
    assert reloaded is not None
    assert reloaded.state == DeletionOperationState.pending
    # Left enqueued_at unset so the pending-drain pass below picks it up —
    # never silently lost, and the failed enqueue was actually attempted.
    assert reloaded.enqueued_at is None
    # Two attempts in this one call: the stale-recovery requeue, then the
    # same function's own pending-drain pass retrying the now-pending row
    # again immediately — both fail with this persistently-flaky fake.
    assert redis.calls == [str(confirmed.id), str(confirmed.id)]


async def test_pending_drain_survives_a_redis_failure_and_recovers_next_tick(
    session: AsyncSession,
) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
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
    assert confirmed.state == DeletionOperationState.pending
    assert confirmed.enqueued_at is None  # never enqueued (no worker was running at confirm time)

    flaky = _FlakyRedis()
    first = await recover_stale_operations(
        session, flaky, now=NOW, heartbeat_timeout=timedelta(minutes=10), max_attempts=3
    )
    assert first.drained == 0  # the attempt happened and failed, not skipped
    reloaded = await session.get(DataDeletionOperation, confirmed.id, populate_existing=True)
    assert reloaded is not None
    assert reloaded.enqueued_at is None

    class _HealthyRedis:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def enqueue_job(self, function: str, *args: object, **_: object) -> object:
            self.calls.append(str(args[0]) if args else "")
            return object()

    healthy = _HealthyRedis()
    second = await recover_stale_operations(
        session, healthy, now=NOW, heartbeat_timeout=timedelta(minutes=10), max_attempts=3
    )
    assert second.drained == 1
    reloaded_again = await session.get(DataDeletionOperation, confirmed.id, populate_existing=True)
    assert reloaded_again is not None
    assert reloaded_again.enqueued_at is not None
