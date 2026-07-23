"""Stage 8 Phase 2: the arq worker glue (ADR 0004 D48).

`worker_app.py` is deliberately thin — these tests check the wiring itself
(startup/shutdown lifecycle, and that the two entry points correctly
delegate to `scheduled_briefs`), not the domain logic, which
`test_scheduled_briefs.py` already covers in full.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL, _test_settings
from tests.test_scheduled_briefs import FakeRedis, _enable_scheduling, _make_user

from lifeflow_api.models import ScheduledBriefRun, ScheduledRunStatus
from lifeflow_api.scheduled_briefs import job_deserializer, job_id_for, job_serializer
from lifeflow_api.worker_app import (
    WorkerSettings,
    dispatch_scheduled_briefs,
    generate_scheduled_brief,
    on_shutdown,
    on_startup,
)

pytestmark = pytest.mark.integration


async def test_on_startup_populates_ctx_and_on_shutdown_disposes_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("lifeflow_api.worker_app.get_settings", lambda: _test_settings("test"))
    ctx: dict[str, object] = {}
    await on_startup(ctx)
    assert "engine" in ctx
    assert "sessionmaker" in ctx
    assert ctx["llm_provider"] is None  # LLM extraction is off in test settings

    async with ctx["sessionmaker"]() as session:  # type: ignore[operator]
        await session.execute(select(1))

    await on_shutdown(ctx)  # must not raise


async def test_dispatch_scheduled_briefs_delegates_to_dispatch_tick() -> None:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            user = await _make_user(session)
            await _enable_scheduling(session, user.id, briefing_time="00:00")
            await session.commit()

        redis = FakeRedis()
        ctx = {"redis": redis, "sessionmaker": maker}
        await dispatch_scheduled_briefs(ctx)

        async with maker() as session:
            runs = (
                (
                    await session.execute(
                        select(ScheduledBriefRun).where(ScheduledBriefRun.user_id == user.id)
                    )
                )
                .scalars()
                .all()
            )
        # `now` inside the real wrapper is wall-clock, so whether today's UTC
        # local-midnight instant is already due varies by run time; either
        # way, dispatch_tick must have been reached without error and any
        # run it created must be well-formed.
        for run in runs:
            assert run.status in {ScheduledRunStatus.pending, ScheduledRunStatus.skipped}
    finally:
        await engine.dispose()


async def test_generate_scheduled_brief_delegates_to_run_scheduled_generation() -> None:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            user = await _make_user(session)
            await _enable_scheduling(session, user.id)
            run = ScheduledBriefRun(
                user_id=user.id,
                local_brief_date=date(2020, 1, 1),  # deliberately harmless/past
                scheduled_for_utc=datetime(2020, 1, 1, tzinfo=UTC),
                timezone_snapshot="Europe/London",
                briefing_time_snapshot="00:00",
                status=ScheduledRunStatus.pending,
                queue_job_id=job_id_for(user.id, date(2020, 1, 1), 0),
            )
            session.add(run)
            await session.flush()
            run_id = run.id
            await session.commit()

        ctx = {"redis": FakeRedis(), "sessionmaker": maker, "llm_provider": None}
        await generate_scheduled_brief(ctx, str(run_id))

        async with maker() as session:
            refreshed = await session.get(ScheduledBriefRun, run_id, populate_existing=True)
            assert refreshed is not None
            assert refreshed.status in {ScheduledRunStatus.succeeded, ScheduledRunStatus.failed}
    finally:
        await engine.dispose()


def test_worker_settings_uses_json_serialization_and_a_single_retry_authority() -> None:
    assert WorkerSettings.job_serializer is job_serializer
    assert WorkerSettings.job_deserializer is job_deserializer
    assert WorkerSettings.max_tries == 1  # arq never auto-retries; scheduled_briefs owns retries
    assert generate_scheduled_brief in WorkerSettings.functions
    # Stage 8 Phase 3 (ADR 0004 D54/D56) added the memory recompute task and a
    # daily memory-expiry cron on the same worker; no new queue.
    function_names = {getattr(fn, "__name__", "") for fn in WorkerSettings.functions}
    assert "recompute_user_memory" in function_names
    # Stage 9 Delivery Phase 2 (ADR 0005) added the deletion-operation job and a
    # per-minute deletion cron (retention scan + pending-drain + stale recovery)
    # on the same worker; still no new queue.
    assert "run_deletion_operation" in function_names
    cron_names = {job.name for job in WorkerSettings.cron_jobs}
    assert cron_names == {
        "cron:dispatch_scheduled_briefs",
        "cron:expire_stale_memory",
        "cron:dispatch_deletion_operations",
    }


def test_job_serializer_round_trips_a_plain_identifier_payload() -> None:
    # JSON has no tuple type, so a tuple argument comes back as a list —
    # exactly as real arq payloads do; this is a defining, accepted
    # property of choosing JSON over pickle here (ADR 0004 D48).
    payload = {"f": "generate_scheduled_brief", "a": ["abc-123"], "k": {}, "t": 1, "et": 0}
    assert job_deserializer(job_serializer(payload)) == payload
