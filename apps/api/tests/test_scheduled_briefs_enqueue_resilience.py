"""Stage 9 Delivery Phase 5 (§11): a Redis blip during
`dispatch_tick`/`recover_stale_running` must never abort the whole cron
tick — before this fix, an uncaught `redis.enqueue_job` exception aborted
the entire function, rolling back every other user's state change made
earlier in the same loop. Uses the same fake-Redis, DB-focused style as
`test_scheduled_briefs.py` (real queue semantics live in
`test_scheduled_briefs_queue.py`); this file only needs precise, injectable
failure control, not a live Redis.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import redis.exceptions as redis_exceptions
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL
from tests.test_scheduled_briefs import FakeRedis, _enable_scheduling, _make_user

from lifeflow_api.models import ScheduledBriefRun, ScheduledRunStatus
from lifeflow_api.scheduled_briefs import dispatch_tick, job_id_for, recover_stale_running

pytestmark = pytest.mark.integration


class _FlakyRedis(FakeRedis):
    """Raises for every job id in `fail_job_ids`, otherwise behaves exactly
    like `FakeRedis`. `persistent=False` (the default) clears an id from
    the failure set the first time it's raised on — modelling a blip that
    resolves itself in time for the immediate same-tick drain retry
    (`dispatch_tick` calls `_recover_never_enqueued` right after its main
    loop). `persistent=True` keeps failing that id across every call in
    this instance's lifetime — modelling a Redis outage still ongoing when
    the drain retry runs a moment later."""

    def __init__(self, fail_job_ids: set[str], *, persistent: bool = False) -> None:
        super().__init__()
        self._fail_job_ids = set(fail_job_ids)
        self._persistent = persistent

    async def enqueue_job(
        self, function: str, *args: object, _job_id: str | None = None, **kwargs: object
    ) -> object | None:
        if _job_id in self._fail_job_ids:
            if not self._persistent:
                self._fail_job_ids.discard(_job_id)
            raise redis_exceptions.ConnectionError("simulated Redis outage")
        return await super().enqueue_job(function, *args, _job_id=_job_id, **kwargs)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


async def test_one_users_redis_failure_does_not_abort_another_users_enqueue(
    session: AsyncSession,
) -> None:
    healthy_user = await _make_user(session)
    flaky_user = await _make_user(session)
    await _enable_scheduling(session, healthy_user.id, briefing_time="07:30")
    await _enable_scheduling(session, flaky_user.id, briefing_time="07:30")
    await session.commit()
    now = datetime(2026, 7, 21, 6, 30, tzinfo=UTC)

    flaky_job_id = job_id_for(flaky_user.id, now.date(), 0)
    redis = _FlakyRedis(fail_job_ids={flaky_job_id}, persistent=True)

    result = await dispatch_tick(redis, session, now=now)

    assert result.enqueued == 1  # the healthy user, despite the other's failure
    runs = (await session.execute(select(ScheduledBriefRun))).scalars().all()
    healthy_run = next(r for r in runs if r.user_id == healthy_user.id)
    flaky_run = next(r for r in runs if r.user_id == flaky_user.id)
    assert healthy_run.enqueued_at is not None
    # The failed run is left `pending`/`enqueued_at=None` for a later tick
    # to drain — never silently lost, never crashing the tick.
    assert flaky_run.status == ScheduledRunStatus.pending
    assert flaky_run.enqueued_at is None


async def test_a_failed_enqueue_is_drained_by_the_same_ticks_drain_pass_once_healthy(
    session: AsyncSession,
) -> None:
    """A blip that resolves itself before `dispatch_tick`'s own
    `_recover_never_enqueued` drain pass runs a moment later self-heals
    within the very same tick — no second cron tick required."""
    user = await _make_user(session)
    await _enable_scheduling(session, user.id, briefing_time="07:30")
    await session.commit()
    now = datetime(2026, 7, 21, 6, 30, tzinfo=UTC)

    job_id = job_id_for(user.id, now.date(), 0)
    redis = _FlakyRedis(fail_job_ids={job_id}, persistent=False)

    result = await dispatch_tick(redis, session, now=now)

    assert result.enqueued == 0  # failed on the main loop's own attempt
    assert result.drained == 1  # recovered moments later by the drain pass
    run = (
        await session.execute(select(ScheduledBriefRun).where(ScheduledBriefRun.user_id == user.id))
    ).scalar_one()
    assert run.enqueued_at is not None


async def test_a_persistent_failure_is_drained_on_a_later_healthy_tick(
    session: AsyncSession,
) -> None:
    """An outage still ongoing through the whole first tick (main loop and
    its own drain pass both fail) is picked up by a later tick once Redis
    recovers."""
    user = await _make_user(session)
    await _enable_scheduling(session, user.id, briefing_time="07:30")
    await session.commit()
    now = datetime(2026, 7, 21, 6, 30, tzinfo=UTC)

    job_id = job_id_for(user.id, now.date(), 0)
    flaky_redis = _FlakyRedis(fail_job_ids={job_id}, persistent=True)
    first = await dispatch_tick(flaky_redis, session, now=now)
    assert first.enqueued == 0
    assert first.drained == 0

    healthy_redis = FakeRedis()
    second = await dispatch_tick(healthy_redis, session, now=now + timedelta(minutes=1))
    assert second.drained == 1

    run = (
        await session.execute(select(ScheduledBriefRun).where(ScheduledBriefRun.user_id == user.id))
    ).scalar_one()
    assert run.enqueued_at is not None


async def test_recover_stale_running_survives_a_redis_failure_mid_recovery(
    session: AsyncSession,
) -> None:
    stuck_user = await _make_user(session)
    other_user = await _make_user(session)
    now = datetime(2026, 7, 21, 8, 0, tzinfo=UTC)
    started_at = now - timedelta(minutes=30)  # well past STALE_RUNNING_THRESHOLD

    stuck_run = ScheduledBriefRun(
        user_id=stuck_user.id,
        local_brief_date=now.date(),
        scheduled_for_utc=now,
        timezone_snapshot="Europe/London",
        briefing_time_snapshot="07:30",
        status=ScheduledRunStatus.running,
        started_at=started_at,
        queue_job_id="stale-original",
    )
    other_run = ScheduledBriefRun(
        user_id=other_user.id,
        local_brief_date=now.date(),
        scheduled_for_utc=now,
        timezone_snapshot="Europe/London",
        briefing_time_snapshot="07:30",
        status=ScheduledRunStatus.running,
        started_at=started_at,
        queue_job_id="stale-original",
    )
    session.add_all([stuck_run, other_run])
    await session.flush()

    # `recover_stale_running` regenerates `queue_job_id` from
    # (user_id, local_brief_date, attempt_count=0) before enqueuing — the
    # fake must fail on that regenerated id, not the placeholder above.
    stuck_job_id = job_id_for(stuck_user.id, now.date(), 0)
    redis = _FlakyRedis(fail_job_ids={stuck_job_id})
    outcome = await recover_stale_running(session, redis, now=now)

    assert outcome.requeued == 1  # only the healthy one actually got a working enqueue
    await session.refresh(stuck_run)
    await session.refresh(other_run)
    assert stuck_run.status == ScheduledRunStatus.pending
    assert stuck_run.enqueued_at is None  # available for a later drain pass
    assert other_run.enqueued_at is not None
