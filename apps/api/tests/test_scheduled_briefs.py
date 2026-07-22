"""Stage 8 Phase 2: the scheduled daily brief (ADR 0004 D47-D50).

Pure database logic, plus real-Postgres concurrency races following the
same pattern as `test_action_concurrency.py` (each racing task uses its own
engine/session so row locks and unique constraints are exercised for
real). Queue-level (real Redis) behaviour lives in
`test_scheduled_briefs_queue.py`; this file uses a small in-process fake
Redis wherever only the database-side logic is under test, and is explicit
about that boundary in each test's docstring.

All tests use a controllable, explicit `now` — never wall-clock time — so
the schedule/DST/catch-up matrix is deterministic regardless of when the
suite runs.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL
from tests.helpers import REFERENCE, TIMEZONE, demo_source_items

from lifeflow_api.brief_composition import BriefService
from lifeflow_api.models import (
    ActionExecution,
    ActionProposal,
    Brief,
    Preference,
    ProposalStatus,
    Provenance,
    ScheduledBriefRun,
    ScheduledRunStatus,
    User,
)
from lifeflow_api.preferences import (
    BRIEF_SECTIONS_KEY,
    BRIEFING_TIME_KEY,
    SCHEDULED_BRIEFS_ENABLED_KEY,
)
from lifeflow_api.repositories import ScheduledBriefRunRepository
from lifeflow_api.scheduled_briefs import (
    ERROR_GENERATION_FAILED,
    ERROR_MISSED_GRACE_WINDOW,
    ERROR_REDIS_UNAVAILABLE,
    ERROR_SCHEDULE_DISABLED,
    ERROR_WORKER_STALE_TIMEOUT,
    GRACE_WINDOW,
    MAX_ATTEMPTS,
    STALE_RUNNING_THRESHOLD,
    classify_failure,
    compute_target_utc,
    job_id_for,
    list_enabled_schedules,
    next_expected_run,
    plan_dispatch,
    recover_stale_running,
    resolve_local_schedule_instant,
    run_scheduled_generation,
)

pytestmark = pytest.mark.integration


class FakeRedis:
    """A minimal stand-in for `arq.connections.ArqRedis`, modelling only the
    one behaviour these DB-focused tests need: `enqueue_job` returns `None`
    for a `_job_id` already seen (arq's real dedup semantics), otherwise a
    truthy stand-in. Real queue-level dedup is verified against a real
    Redis in `test_scheduled_briefs_queue.py` — this fake never stands in
    for that claim."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], str | None]] = []
        self._seen_job_ids: set[str] = set()

    async def enqueue_job(
        self, function: str, *args: object, _job_id: str | None = None, **_kwargs: object
    ) -> object | None:
        self.calls.append((function, args, _job_id))
        if _job_id is not None and _job_id in self._seen_job_ids:
            return None
        if _job_id is not None:
            self._seen_job_ids.add(_job_id)
        return object()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


async def _make_user(session: AsyncSession, *, timezone: str = TIMEZONE) -> User:
    user = User(
        email=f"sched-{uuid.uuid4()}@lifeflow.local", display_name="Sched", timezone=timezone
    )
    session.add(user)
    await session.flush()
    return user


async def _enable_scheduling(
    session: AsyncSession, user_id: uuid.UUID, *, briefing_time: str = "07:30"
) -> None:
    session.add(
        Preference(
            user_id=user_id,
            key=SCHEDULED_BRIEFS_ENABLED_KEY,
            value_json={"enabled": True},
            provenance=Provenance.explicit,
        )
    )
    session.add(
        Preference(
            user_id=user_id,
            key=BRIEFING_TIME_KEY,
            value_json={"value": briefing_time},
            provenance=Provenance.explicit,
        )
    )
    await session.flush()


async def _seed_full_user(
    session: AsyncSession,
    *,
    timezone: str = TIMEZONE,
    briefing_time: str = "07:30",
    anchor: date | None = None,
) -> User:
    user = await _make_user(session, timezone=timezone)
    await _enable_scheduling(session, user.id, briefing_time=briefing_time)
    session.add_all(await demo_source_items(user.id, anchor=anchor))
    await session.flush()
    await session.commit()
    return user


# --- Schedule calculation (pure) --------------------------------------------


def test_compute_target_utc_matches_exact_configured_time() -> None:
    target = compute_target_utc(date(2026, 7, 21), "07:30", "Europe/London")
    assert target == datetime(2026, 7, 21, 6, 30, tzinfo=UTC)  # BST, UTC+1


def test_compute_target_utc_spring_forward_gap_lands_at_the_first_valid_instant() -> None:
    """UK clocks jump 01:00 GMT -> 02:00 BST on 2026-03-29 (verified against
    zoneinfo's actual transition data for that year, not assumed). A
    configured 01:30 never occurs; the resolver advances to the first
    wall-clock instant that actually exists after the gap: 02:00:00 BST,
    i.e. 01:00:00 UTC — not "01:30 + the gap size" (02:30 BST), which a
    naive fold=0-only implementation previously, and wrongly, produced."""
    target = compute_target_utc(date(2026, 3, 29), "01:30", "Europe/London")
    assert target == datetime(2026, 3, 29, 1, 0, tzinfo=UTC)
    assert target.astimezone(ZoneInfo("Europe/London")).strftime("%H:%M:%S %Z") == "02:00:00 BST"


def test_resolve_local_schedule_instant_classifies_the_spring_forward_gap_as_nonexistent() -> None:
    resolution = resolve_local_schedule_instant(date(2026, 3, 29), "01:30", "Europe/London")
    assert resolution.classification == "nonexistent"
    assert resolution.utc == datetime(2026, 3, 29, 1, 0, tzinfo=UTC)


def test_compute_target_utc_fall_back_ambiguous_time_picks_first_occurrence() -> None:
    """UK clocks fall back 02:00 BST -> 01:00 GMT on 2026-10-25. 01:30 occurs
    twice; the first (BST, pre-transition) occurrence is used, so the job
    runs exactly once."""
    target = compute_target_utc(date(2026, 10, 25), "01:30", "Europe/London")
    first_occurrence = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)  # 01:30 BST
    second_occurrence = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)  # 01:30 GMT
    assert target == first_occurrence
    assert target < second_occurrence


def test_resolve_local_schedule_instant_classifies_the_fall_back_hour_as_ambiguous() -> None:
    resolution = resolve_local_schedule_instant(date(2026, 10, 25), "01:30", "Europe/London")
    assert resolution.classification == "ambiguous"
    assert resolution.utc == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)


def test_resolve_local_schedule_instant_classifies_an_ordinary_day_as_valid() -> None:
    resolution = resolve_local_schedule_instant(date(2026, 7, 21), "07:30", "Europe/London")
    assert resolution.classification == "valid"
    assert resolution.utc == datetime(2026, 7, 21, 6, 30, tzinfo=UTC)


def test_compute_target_utc_different_timezones_differ_for_the_same_local_time() -> None:
    london = compute_target_utc(date(2026, 7, 21), "08:00", "Europe/London")
    new_york = compute_target_utc(date(2026, 7, 21), "08:00", "America/New_York")
    assert london != new_york
    assert london == datetime(2026, 7, 21, 7, 0, tzinfo=UTC)
    assert new_york == datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def test_compute_target_utc_handles_a_non_one_hour_dst_offset_without_assuming_60_minutes() -> None:
    """Australia/Lord_Howe's DST offset is 30 minutes, not the usual 60 —
    verified against zoneinfo's actual 2026 transition data. Its
    spring-forward gap on 2026-10-04 is 02:00-02:30 local; the resolver
    must find 02:30 (the actual gap size) without any hard-coded
    one-hour assumption."""
    tz = "Australia/Lord_Howe"
    gap_resolution = resolve_local_schedule_instant(date(2026, 10, 4), "02:15", tz)
    assert gap_resolution.classification == "nonexistent"
    assert gap_resolution.utc.astimezone(ZoneInfo(tz)).strftime("%H:%M") == "02:30"

    ordinary_resolution = resolve_local_schedule_instant(date(2026, 10, 4), "01:45", tz)
    assert ordinary_resolution.classification == "valid"


async def test_next_expected_run_and_dispatch_eligibility_agree_on_the_spring_forward_gap(
    session: AsyncSession,
) -> None:
    """The Settings "next run" display (`next_expected_run`) and the
    dispatcher's own due-ness check (`plan_dispatch`, via `compute_target_utc`)
    must never disagree about when a gap-affected schedule actually runs."""
    user = await _make_user(session, timezone="Europe/London")
    await _enable_scheduling(session, user.id, briefing_time="01:30")
    await session.commit()

    just_before = datetime(2026, 3, 29, 0, 59, tzinfo=UTC)
    displayed_next_run = await next_expected_run(
        session,
        user.id,
        now=just_before,
        timezone_name="Europe/London",
        briefing_time="01:30",
    )
    assert displayed_next_run == datetime(2026, 3, 29, 1, 0, tzinfo=UTC)

    plan = await plan_dispatch(session, now=just_before)
    assert plan.not_due == 1
    assert plan.to_enqueue == []

    plan_at_due_instant = await plan_dispatch(session, now=displayed_next_run)
    assert len(plan_at_due_instant.to_enqueue) == 1
    assert plan_at_due_instant.to_enqueue[0].scheduled_for_utc == displayed_next_run


# --- Dispatch planning (DB-only) --------------------------------------------


async def test_disabled_user_is_never_dispatched(session: AsyncSession) -> None:
    user = await _make_user(session)
    await session.commit()
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    plan = await plan_dispatch(session, now=now)
    assert plan.to_enqueue == []
    runs = await ScheduledBriefRunRepository(session, user.id).get_for_local_date(now.date())
    assert runs is None


async def test_enabled_but_not_due_creates_no_run(session: AsyncSession) -> None:
    user = await _make_user(session)
    await _enable_scheduling(session, user.id, briefing_time="23:00")
    await session.commit()
    now = datetime(2026, 7, 21, 6, 0, tzinfo=UTC)  # 07:00 BST, well before 23:00 local
    plan = await plan_dispatch(session, now=now)
    assert plan.to_enqueue == []
    assert plan.not_due == 1
    assert (
        await ScheduledBriefRunRepository(session, user.id).get_for_local_date(now.date()) is None
    )


async def test_enabled_and_due_creates_exactly_one_pending_run(session: AsyncSession) -> None:
    user = await _make_user(session)
    await _enable_scheduling(session, user.id, briefing_time="07:30")
    await session.commit()
    now = datetime(2026, 7, 21, 6, 30, tzinfo=UTC)  # exactly due (07:30 BST)
    plan = await plan_dispatch(session, now=now)
    assert len(plan.to_enqueue) == 1
    run = plan.to_enqueue[0]
    assert run.user_id == user.id
    assert run.status == ScheduledRunStatus.pending
    assert run.queue_job_id == job_id_for(user.id, now.date(), 0)


async def test_timezone_change_before_run_is_picked_up_fresh_each_tick(
    session: AsyncSession,
) -> None:
    user = await _make_user(session, timezone="America/New_York")
    await _enable_scheduling(session, user.id, briefing_time="08:00")
    await session.commit()
    now_not_due_ny = datetime(2026, 7, 21, 6, 0, tzinfo=UTC)  # 02:00 EDT, not due
    plan = await plan_dispatch(session, now=now_not_due_ny)
    assert plan.to_enqueue == []

    user.timezone = "Europe/London"
    await session.flush()
    await session.commit()
    now_due_london = datetime(2026, 7, 21, 7, 0, tzinfo=UTC)  # 08:00 BST, due under the NEW tz
    plan = await plan_dispatch(session, now=now_due_london)
    assert len(plan.to_enqueue) == 1
    assert plan.to_enqueue[0].timezone_snapshot == "Europe/London"


async def test_briefing_time_change_before_run_uses_the_new_time(session: AsyncSession) -> None:
    user = await _make_user(session)
    await _enable_scheduling(session, user.id, briefing_time="20:00")
    await session.commit()
    now = datetime(2026, 7, 21, 6, 30, tzinfo=UTC)  # would be due for 07:30, not 20:00
    plan = await plan_dispatch(session, now=now)
    assert plan.to_enqueue == []

    changed = await session.execute(
        select(Preference).where(Preference.user_id == user.id, Preference.key == BRIEFING_TIME_KEY)
    )
    pref = changed.scalar_one()
    pref.value_json = {"value": "07:30"}
    await session.flush()
    plan = await plan_dispatch(session, now=now)
    assert len(plan.to_enqueue) == 1
    assert plan.to_enqueue[0].briefing_time_snapshot == "07:30"


async def test_briefing_time_change_after_a_successful_run_never_runs_again_that_day(
    session: AsyncSession,
) -> None:
    user = await _make_user(session)
    await _enable_scheduling(session, user.id, briefing_time="07:30")
    await session.commit()
    now = datetime(2026, 7, 21, 6, 30, tzinfo=UTC)
    first_plan = await plan_dispatch(session, now=now)
    assert len(first_plan.to_enqueue) == 1
    first_plan.to_enqueue[0].status = ScheduledRunStatus.succeeded
    await session.flush()

    changed = await session.execute(
        select(Preference).where(Preference.user_id == user.id, Preference.key == BRIEFING_TIME_KEY)
    )
    changed.scalar_one().value_json = {"value": "06:00"}
    await session.flush()
    later_same_day = datetime(2026, 7, 21, 20, 0, tzinfo=UTC)
    second_plan = await plan_dispatch(session, now=later_same_day)
    assert second_plan.to_enqueue == []
    assert second_plan.already_handled == 1
    runs = await session.execute(
        select(ScheduledBriefRun).where(
            ScheduledBriefRun.user_id == user.id, ScheduledBriefRun.local_brief_date == now.date()
        )
    )
    assert len(list(runs.scalars())) == 1


async def test_invalid_timezone_fails_safely_without_crashing(session: AsyncSession) -> None:
    user = await _make_user(session, timezone="Not/AZone")
    await _enable_scheduling(session, user.id)
    await session.commit()
    plan = await plan_dispatch(session, now=datetime(2026, 7, 21, 12, 0, tzinfo=UTC))
    assert plan.to_enqueue == []
    assert plan.invalid_timezone == 1


# --- Catch-up (ADR 0004 D49) -------------------------------------------------


async def test_catch_up_within_grace_window_still_generates(session: AsyncSession) -> None:
    user = await _make_user(session)
    await _enable_scheduling(session, user.id, briefing_time="07:30")
    await session.commit()
    now = datetime(2026, 7, 21, 6, 30, tzinfo=UTC) + timedelta(hours=3)  # 3h late, within 6h
    plan = await plan_dispatch(session, now=now)
    assert len(plan.to_enqueue) == 1
    assert plan.to_enqueue[0].status == ScheduledRunStatus.pending


async def test_catch_up_beyond_grace_window_is_skipped_not_generated(session: AsyncSession) -> None:
    user = await _make_user(session)
    await _enable_scheduling(session, user.id, briefing_time="07:30")
    await session.commit()
    target = datetime(2026, 7, 21, 6, 30, tzinfo=UTC)
    now = target + GRACE_WINDOW + timedelta(hours=1)
    plan = await plan_dispatch(session, now=now)
    assert plan.to_enqueue == []
    assert plan.skipped_grace == 1
    run = await ScheduledBriefRunRepository(session, user.id).get_for_local_date(now.date())
    assert run is not None
    assert run.status == ScheduledRunStatus.skipped
    assert run.error_code == ERROR_MISSED_GRACE_WINDOW


async def test_catch_up_on_the_spring_forward_gap_measures_lateness_from_the_resolved_instant(
    session: AsyncSession,
) -> None:
    """The catch-up grace window must be measured from the resolver's
    actual answer (02:00:00 BST / 01:00 UTC for a configured 01:30 on the UK's
    2026-03-29 gap), not from the naive requested wall-clock time — a bug
    here would silently shift the grace window by the gap size."""
    user = await _make_user(session, timezone="Europe/London")
    await _enable_scheduling(session, user.id, briefing_time="01:30")
    await session.commit()

    resolved_instant = datetime(2026, 3, 29, 1, 0, tzinfo=UTC)
    within_grace = resolved_instant + GRACE_WINDOW - timedelta(minutes=1)
    plan = await plan_dispatch(session, now=within_grace)
    assert len(plan.to_enqueue) == 1
    assert plan.to_enqueue[0].scheduled_for_utc == resolved_instant


async def test_a_skipped_day_never_backfills_and_never_blocks_the_next_day(
    session: AsyncSession,
) -> None:
    user = await _make_user(session)
    await _enable_scheduling(session, user.id, briefing_time="07:30")
    await session.commit()

    day1_target = datetime(2026, 7, 21, 6, 30, tzinfo=UTC)
    day1_too_late = day1_target + GRACE_WINDOW + timedelta(hours=2)
    plan1 = await plan_dispatch(session, now=day1_too_late)
    assert plan1.skipped_grace == 1

    # Ticking again later the same day must not add a second row or a
    # backfilled attempt for day 1.
    plan1_again = await plan_dispatch(session, now=day1_too_late + timedelta(hours=1))
    assert plan1_again.to_enqueue == []
    assert plan1_again.already_handled == 1

    day2_due = datetime(2026, 7, 22, 6, 30, tzinfo=UTC)
    plan2 = await plan_dispatch(session, now=day2_due)
    assert len(plan2.to_enqueue) == 1  # tomorrow's run is unaffected

    all_runs = await session.execute(
        select(ScheduledBriefRun).where(ScheduledBriefRun.user_id == user.id)
    )
    assert len(list(all_runs.scalars())) == 2  # exactly one row per day, no extra backfill


# --- Idempotency and concurrency --------------------------------------------


async def test_repeated_dispatcher_ticks_enqueue_exactly_one_job(session: AsyncSession) -> None:
    user = await _make_user(session)
    await _enable_scheduling(session, user.id, briefing_time="07:30")
    await session.commit()
    now = datetime(2026, 7, 21, 6, 30, tzinfo=UTC)
    first = await plan_dispatch(session, now=now)
    second = await plan_dispatch(session, now=now)
    assert len(first.to_enqueue) == 1
    assert second.to_enqueue == []
    assert second.already_handled == 1


async def test_concurrent_dispatch_ticks_create_exactly_one_run(session: AsyncSession) -> None:
    """Real-Postgres race (pattern per `test_action_concurrency.py`): two
    independent dispatcher ticks, each on its own engine/session, race to
    claim the same user/local-date. The unique constraint is the final
    guard — exactly one row survives."""
    user = await _make_user(session)
    await _enable_scheduling(session, user.id, briefing_time="07:30")
    await session.commit()
    now = datetime(2026, 7, 21, 6, 30, tzinfo=UTC)

    async def tick_once() -> int:
        engine = create_async_engine(TEST_DB_URL)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as racing:
                plan = await plan_dispatch(racing, now=now)
                await racing.commit()
                return len(plan.to_enqueue)
        finally:
            await engine.dispose()

    first, second = await asyncio.gather(tick_once(), tick_once())
    assert first + second == 1  # exactly one of the two actually created it

    runs = await session.execute(
        select(ScheduledBriefRun).where(ScheduledBriefRun.user_id == user.id)
    )
    assert len(list(runs.scalars())) == 1


async def test_two_generation_workers_racing_produce_exactly_one_brief(
    session: AsyncSession,
) -> None:
    """Real-Postgres race for the atomic pending->running claim inside
    `run_scheduled_generation` (test matrix item: two generation workers
    racing create one brief)."""
    user = await _seed_full_user(session, briefing_time="07:30")
    run = ScheduledBriefRun(
        user_id=user.id,
        local_brief_date=date(2026, 7, 21),
        scheduled_for_utc=datetime(2026, 7, 21, 6, 30, tzinfo=UTC),
        timezone_snapshot=TIMEZONE,
        briefing_time_snapshot="07:30",
        status=ScheduledRunStatus.pending,
        queue_job_id=job_id_for(user.id, date(2026, 7, 21), 0),
    )
    session.add(run)
    await session.flush()
    run_id = run.id
    await session.commit()
    now = datetime(2026, 7, 21, 6, 30, 5, tzinfo=UTC)

    async def generate_once() -> None:
        engine = create_async_engine(TEST_DB_URL)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as racing:
                await run_scheduled_generation(racing, FakeRedis(), run_id, now=now)
        finally:
            await engine.dispose()

    await asyncio.gather(generate_once(), generate_once())

    briefs = await session.execute(select(Brief).where(Brief.scheduled_run_id == run_id))
    assert len(list(briefs.scalars())) == 1  # exactly one brief, never two

    refreshed = await session.get(ScheduledBriefRun, run_id, populate_existing=True)
    assert refreshed is not None
    assert refreshed.status == ScheduledRunStatus.succeeded
    assert refreshed.attempt_count == 1  # only one claim ever succeeded


async def test_worker_retry_after_brief_commit_does_not_create_a_second_brief(
    session: AsyncSession,
) -> None:
    """The crash boundary in ADR 0004 D49: a brief was committed and the run
    marked succeeded, but a stale retry (e.g. a duplicate delivery) calls
    the same entry point again — it must find the existing brief, never
    generate another."""
    user = await _seed_full_user(session)
    run = ScheduledBriefRun(
        user_id=user.id,
        local_brief_date=date(2026, 7, 21),
        scheduled_for_utc=datetime(2026, 7, 21, 6, 30, tzinfo=UTC),
        timezone_snapshot=TIMEZONE,
        briefing_time_snapshot="07:30",
        status=ScheduledRunStatus.pending,
        queue_job_id=job_id_for(user.id, date(2026, 7, 21), 0),
    )
    session.add(run)
    await session.flush()
    run_id = run.id
    await session.commit()
    now = datetime(2026, 7, 21, 6, 30, 5, tzinfo=UTC)

    redis = FakeRedis()
    await run_scheduled_generation(session, redis, run_id, now=now)
    first_brief = (
        await session.execute(select(Brief).where(Brief.scheduled_run_id == run_id))
    ).scalar_one()

    # Simulate the worker crashing right after commit, before it could tell
    # arq the job succeeded: the run is re-delivered as `pending` again.
    stale = await session.get(ScheduledBriefRun, run_id, populate_existing=True)
    assert stale is not None
    stale.status = ScheduledRunStatus.pending
    await session.flush()
    await session.commit()

    await run_scheduled_generation(session, redis, run_id, now=now)

    briefs = await session.execute(select(Brief).where(Brief.scheduled_run_id == run_id))
    all_briefs = list(briefs.scalars())
    assert len(all_briefs) == 1
    assert all_briefs[0].id == first_brief.id

    final_run = await session.get(ScheduledBriefRun, run_id, populate_existing=True)
    assert final_run is not None
    assert final_run.status == ScheduledRunStatus.succeeded


async def test_manual_regeneration_remains_available_and_distinct_from_scheduled(
    session: AsyncSession,
) -> None:
    user = await _seed_full_user(session, anchor=REFERENCE.date())
    manual = await BriefService(session, user.id).generate(timezone=TIMEZONE, reference=REFERENCE)
    assert manual.generation_trigger == "manual"
    assert manual.scheduled_run_id is None

    run = ScheduledBriefRun(
        user_id=user.id,
        local_brief_date=date(2026, 7, 22),
        scheduled_for_utc=datetime(2026, 7, 22, 6, 30, tzinfo=UTC),
        timezone_snapshot=TIMEZONE,
        briefing_time_snapshot="07:30",
        status=ScheduledRunStatus.pending,
        queue_job_id=job_id_for(user.id, date(2026, 7, 22), 0),
    )
    session.add(run)
    await session.flush()
    run_id = run.id
    await session.commit()
    await run_scheduled_generation(
        session, FakeRedis(), run_id, now=datetime(2026, 7, 22, 6, 30, tzinfo=UTC)
    )

    scheduled_run = await session.get(ScheduledBriefRun, run_id, populate_existing=True)
    assert scheduled_run is not None
    assert scheduled_run.brief_id is not None
    scheduled_brief = await session.get(Brief, scheduled_run.brief_id)
    assert scheduled_brief is not None
    assert scheduled_brief.generation_trigger == "scheduled"
    assert scheduled_brief.id != manual.id


# --- Stale-running recovery --------------------------------------------------


async def test_stale_running_is_recovered_and_requeued_below_max_attempts(
    session: AsyncSession,
) -> None:
    user = await _make_user(session)
    await _enable_scheduling(session, user.id)
    await session.commit()
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    run = ScheduledBriefRun(
        user_id=user.id,
        local_brief_date=date(2026, 7, 21),
        scheduled_for_utc=now,
        timezone_snapshot=TIMEZONE,
        briefing_time_snapshot="07:30",
        status=ScheduledRunStatus.running,
        started_at=now - STALE_RUNNING_THRESHOLD - timedelta(minutes=1),
        attempt_count=1,
    )
    session.add(run)
    await session.flush()
    await session.commit()

    redis = FakeRedis()
    result = await recover_stale_running(session, redis, now=now)
    assert result.requeued == 1
    assert result.failed == 0
    refreshed = await session.get(ScheduledBriefRun, run.id, populate_existing=True)
    assert refreshed is not None
    assert refreshed.status == ScheduledRunStatus.pending
    assert refreshed.started_at is None
    assert len(redis.calls) == 1


async def test_stale_running_at_max_attempts_fails_permanently_without_requeue(
    session: AsyncSession,
) -> None:
    user = await _make_user(session)
    await _enable_scheduling(session, user.id)
    await session.commit()
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    run = ScheduledBriefRun(
        user_id=user.id,
        local_brief_date=date(2026, 7, 21),
        scheduled_for_utc=now,
        timezone_snapshot=TIMEZONE,
        briefing_time_snapshot="07:30",
        status=ScheduledRunStatus.running,
        started_at=now - STALE_RUNNING_THRESHOLD - timedelta(minutes=1),
        attempt_count=MAX_ATTEMPTS,
    )
    session.add(run)
    await session.flush()
    await session.commit()

    redis = FakeRedis()
    result = await recover_stale_running(session, redis, now=now)
    assert result.requeued == 0
    assert result.failed == 1
    refreshed = await session.get(ScheduledBriefRun, run.id, populate_existing=True)
    assert refreshed is not None
    assert refreshed.status == ScheduledRunStatus.failed
    assert refreshed.error_code == ERROR_WORKER_STALE_TIMEOUT
    assert redis.calls == []


# --- Failure isolation --------------------------------------------------------


async def test_user_deleted_cascades_the_run_and_generation_is_then_a_safe_no_op(
    session: AsyncSession,
) -> None:
    """`ScheduledBriefRun.user_id` cascades on user delete, like every other
    user-owned table (`_user_fk()`) — so "user deleted before execution" in
    practice means the run row itself is gone by the time a (delayed)
    worker picks up the job. The atomic pending-claim then simply matches
    zero rows and the function returns cleanly: no exception, no orphaned
    write. (The dedicated `ERROR_USER_UNAVAILABLE` skip path in
    `run_scheduled_generation` guards a narrower, currently-unreachable
    race — no code in Stage 8 deletes a user out from under an in-flight
    claim — kept as defence in depth for when account deletion ships.)"""
    user = await _make_user(session)
    await _enable_scheduling(session, user.id)
    await session.commit()
    run = ScheduledBriefRun(
        user_id=user.id,
        local_brief_date=date(2026, 7, 21),
        scheduled_for_utc=datetime(2026, 7, 21, 6, 30, tzinfo=UTC),
        timezone_snapshot=TIMEZONE,
        briefing_time_snapshot="07:30",
        status=ScheduledRunStatus.pending,
        queue_job_id=job_id_for(user.id, date(2026, 7, 21), 0),
    )
    session.add(run)
    await session.flush()
    run_id = run.id
    user_id = user.id
    await session.commit()

    await session.delete(await session.get(User, user_id))
    await session.flush()
    await session.commit()

    # `populate_existing=True` forces a real DB round-trip: with
    # `expire_on_commit=False`, a plain `.get()` would return the stale
    # in-memory object from the identity map instead of re-checking the
    # database (the same subtlety `ConnectedAccountRepository` documents).
    assert (
        await session.get(ScheduledBriefRun, run_id, populate_existing=True) is None
    )  # cascaded away with the user

    await run_scheduled_generation(
        session, FakeRedis(), run_id, now=datetime(2026, 7, 21, 6, 30, 5, tzinfo=UTC)
    )  # must not raise, and must leave no trace since there was nothing to act on


async def test_schedule_disabled_after_enqueue_before_execution_is_skipped(
    session: AsyncSession,
) -> None:
    user = await _make_user(session)
    await _enable_scheduling(session, user.id)
    await session.commit()
    run = ScheduledBriefRun(
        user_id=user.id,
        local_brief_date=date(2026, 7, 21),
        scheduled_for_utc=datetime(2026, 7, 21, 6, 30, tzinfo=UTC),
        timezone_snapshot=TIMEZONE,
        briefing_time_snapshot="07:30",
        status=ScheduledRunStatus.pending,
        queue_job_id=job_id_for(user.id, date(2026, 7, 21), 0),
    )
    session.add(run)
    await session.flush()
    run_id = run.id
    await session.commit()

    pref = (
        await session.execute(
            select(Preference).where(
                Preference.user_id == user.id, Preference.key == SCHEDULED_BRIEFS_ENABLED_KEY
            )
        )
    ).scalar_one()
    pref.value_json = {"enabled": False}
    await session.flush()
    await session.commit()

    await run_scheduled_generation(
        session, FakeRedis(), run_id, now=datetime(2026, 7, 21, 6, 30, 5, tzinfo=UTC)
    )
    refreshed = await session.get(ScheduledBriefRun, run_id, populate_existing=True)
    assert refreshed is not None
    assert refreshed.status == ScheduledRunStatus.skipped
    assert refreshed.error_code == ERROR_SCHEDULE_DISABLED


def test_classify_failure_never_leaks_the_original_exception_text() -> None:
    import redis.exceptions as redis_exceptions
    from sqlalchemy.exc import OperationalError

    marker = "unique-marker-that-must-never-reach-the-user-abc123"
    redis_code, redis_message, redis_transient = classify_failure(
        redis_exceptions.ConnectionError(marker)
    )
    assert redis_code == ERROR_REDIS_UNAVAILABLE
    assert marker not in redis_message
    assert redis_transient is True

    _db_code, db_message, db_transient = classify_failure(
        OperationalError(marker, {}, Exception(marker))
    )
    assert db_message == "The database was temporarily unavailable."
    assert marker not in db_message
    assert db_transient is True

    generic_code, generic_message, generic_transient = classify_failure(ValueError(marker))
    assert generic_code == ERROR_GENERATION_FAILED
    assert marker not in generic_message
    assert generic_transient is False


# --- Behaviour: scheduled generation is a normal, non-executing brief -------


async def test_scheduled_generation_respects_sections_never_hides_needs_attention_and_never_executes(
    session: AsyncSession,
) -> None:
    user = await _seed_full_user(session, briefing_time="07:30", anchor=REFERENCE.date())
    section_pref = (
        await session.execute(
            select(Preference).where(
                Preference.user_id == user.id, Preference.key == BRIEF_SECTIONS_KEY
            )
        )
    ).scalar_one_or_none()
    if section_pref is None:
        session.add(
            Preference(
                user_id=user.id,
                key=BRIEF_SECTIONS_KEY,
                value_json={"sections": ["today_upcoming"]},
                provenance=Provenance.explicit,
            )
        )
    else:
        section_pref.value_json = {"sections": ["today_upcoming"]}
    await session.flush()
    await session.commit()

    run = ScheduledBriefRun(
        user_id=user.id,
        local_brief_date=REFERENCE.date(),
        scheduled_for_utc=REFERENCE,
        timezone_snapshot=TIMEZONE,
        briefing_time_snapshot="07:30",
        status=ScheduledRunStatus.pending,
        queue_job_id=job_id_for(user.id, REFERENCE.date(), 0),
    )
    session.add(run)
    await session.flush()
    run_id = run.id
    await session.commit()

    await run_scheduled_generation(session, FakeRedis(), run_id, now=REFERENCE)

    refreshed_run = await session.get(ScheduledBriefRun, run_id, populate_existing=True)
    assert refreshed_run is not None
    assert refreshed_run.status == ScheduledRunStatus.succeeded
    assert refreshed_run.brief_id is not None
    brief = await session.get(Brief, refreshed_run.brief_id)
    assert brief is not None
    assert brief.generation_trigger == "scheduled"
    assert brief.scheduled_run_id == run_id

    displayed = {section["key"] for section in brief.sections_json["sections"]}
    assert "needs_attention" in displayed  # D45: never hideable
    assert "today_upcoming" in displayed
    assert "waiting_for" not in displayed  # user's chosen filter respected
    assert brief.model_metadata["signal_count"] > 0  # extraction never suppressed

    proposals = (
        (await session.execute(select(ActionProposal).where(ActionProposal.user_id == user.id)))
        .scalars()
        .all()
    )
    assert len(proposals) > 0
    assert all(p.status == ProposalStatus.proposed for p in proposals)  # never approved

    executions = (
        (
            await session.execute(
                select(ActionExecution).where(
                    ActionExecution.proposal_id.in_([p.id for p in proposals])
                )
            )
        )
        .scalars()
        .all()
    )
    assert executions == []  # never executed


# --- list_enabled_schedules ---------------------------------------------------


async def test_list_enabled_schedules_only_returns_explicitly_opted_in_users(
    session: AsyncSession,
) -> None:
    enabled_user = await _make_user(session)
    await _enable_scheduling(session, enabled_user.id, briefing_time="06:15")
    disabled_user = await _make_user(session)  # never sets the preference at all
    await session.commit()

    schedules = await list_enabled_schedules(session)
    ids = {schedule.user_id for schedule in schedules}
    assert enabled_user.id in ids
    assert disabled_user.id not in ids
    matched = next(s for s in schedules if s.user_id == enabled_user.id)
    assert matched.briefing_time == "06:15"
    assert matched.timezone == TIMEZONE
