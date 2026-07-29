"""Stage 8 Phase 2: the scheduled daily brief (ADR 0004 D47-D50).

All Phase 2 domain logic lives here as plain, pytest-covered functions, not
in the thin arq glue in `worker_app.py`: DST-correct due-instant
calculation, dispatch planning (pure database logic, independently testable
without a running queue), catch-up and stale-run recovery, and the per-user
generation entry point that reuses `BriefService` exactly as the manual
`/briefs/generate` route does. Every function takes an explicit `now`
(and, where relevant, an explicit Redis pool) — never `datetime.now(UTC)`
or a module-level connection internally — so the full schedule/DST/catch-up
matrix is testable with a controllable clock and a real test Redis.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import redis.exceptions as redis_exceptions
from arq.connections import ArqRedis
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.audit import record_audit_event
from lifeflow_api.brief_composition import BriefService
from lifeflow_api.failure_taxonomy import FailureCode
from lifeflow_api.llm.provider import LLMProvider
from lifeflow_api.models import Brief, Preference, ScheduledBriefRun, ScheduledRunStatus, User
from lifeflow_api.preferences import (
    SCHEDULED_BRIEFS_ENABLED_KEY,
    briefing_schedule,
    scheduled_briefs_enabled,
)
from lifeflow_api.repositories import ScheduledBriefRunRepository

logger = logging.getLogger(__name__)

# ADR 0004 D49: bounded catch-up window, bounded stale-run recovery, no
# multi-day backfill. Not user-configurable — a deliberate, documented
# operational policy, like the brief's own 14d/30d source window.
GRACE_WINDOW = timedelta(hours=6)
STALE_RUNNING_THRESHOLD = timedelta(minutes=10)
MAX_ATTEMPTS = 3

# Closed vocabulary only — never a stack trace, prompt content, or brief
# prose (skill security requirement; ADR 0004 D49). The four
# infrastructure-failure codes below are the app-wide closed taxonomy
# (Stage 9 Delivery Phase 5, `failure_taxonomy.py`); the rest are
# scheduling-specific skip reasons with no equivalent there.
ERROR_MISSED_GRACE_WINDOW = "missed_grace_window"
ERROR_WORKER_STALE_TIMEOUT = FailureCode.worker_stale_timeout.value
ERROR_USER_UNAVAILABLE = "user_unavailable"
ERROR_SCHEDULE_DISABLED = "schedule_disabled_before_execution"
ERROR_INVALID_TIMEZONE = "invalid_timezone"
ERROR_DATABASE_UNAVAILABLE = FailureCode.database_unavailable.value
ERROR_REDIS_UNAVAILABLE = FailureCode.redis_unavailable.value
ERROR_GENERATION_FAILED = FailureCode.generation_error.value
ERROR_WORKER_TIMEOUT = FailureCode.worker_timeout.value

JOB_FUNCTION_NAME = "generate_scheduled_brief"


def job_id_for(user_id: uuid.UUID, local_date: date, attempt: int) -> str:
    """Deterministic arq job id: an internal identifier only (user_id,
    date, attempt count) — never an email address or other personal
    content. A fresh `attempt` suffix on every retry keeps ids unique
    without depending on arq reusing a completed job's id."""
    return f"scheduled-brief:{user_id}:{local_date.isoformat()}:{attempt}"


def job_serializer(data: Any) -> bytes:
    """JSON, not arq's default pickle (skill security requirement): job
    payloads here are always plain internal identifiers, but this queue
    never deserializes pickle regardless of what is ever put on it."""
    return json.dumps(data, default=str).encode("utf-8")


def job_deserializer(data: bytes) -> Any:
    return json.loads(data.decode("utf-8"))


ScheduleClassification = Literal["valid", "ambiguous", "nonexistent"]

# Bounded search for the spring-forward (nonexistent local time) case: real
# civil DST transitions are well under 2 hours (the 2026 UK transition is 1
# hour; Lord Howe Island's is 30 minutes) — 4 hours is generous headroom
# without an unbounded loop, and the search advances in fine (1-minute)
# steps rather than assuming any particular gap size.
_GAP_SEARCH_BOUND = timedelta(hours=4)
_GAP_SEARCH_STEP = timedelta(minutes=1)


@dataclass(frozen=True)
class ScheduleResolution:
    utc: datetime
    classification: ScheduleClassification


def resolve_local_schedule_instant(
    local_date: date, briefing_time: str, timezone_name: str
) -> ScheduleResolution:
    """Classify and resolve `briefing_time` on `local_date` in
    `timezone_name` (ADR 0004 D48).

    Builds both PEP 495 fold candidates for the requested wall-clock time,
    round-trips each through UTC and back to local time, and classifies by
    which candidates survive that round trip:

    - both folds round-trip to the *same* UTC instant: `valid` — an
      ordinary, unambiguous day;
    - both folds round-trip successfully but to *two different* UTC
      instants: `ambiguous` (fall-back) — the wall-clock time genuinely
      occurs twice; the earlier UTC instant is used, so the job runs
      exactly once;
    - *neither* fold round-trips: `nonexistent` (spring-forward gap) — the
      wall-clock time was skipped entirely. A bounded forward search (no
      hard-coded offset, so it works for a 30-minute gap as well as a
      60-minute one) finds the first local instant that actually exists
      after the gap.

    This replaces a prior implementation that relied on `fold=0`'s default
    behaviour without classifying or round-trip-verifying it: that gave a
    plausible-looking but not independently-derived answer for the gap case
    (`requested time + gap size`, e.g. 02:30 BST for a requested 01:30 on
    the UK's spring transition) rather than the actual first valid instant
    after the gap (02:00 BST) that this function now returns.
    """
    hour, minute = (int(part) for part in briefing_time.split(":"))
    naive = datetime.combine(local_date, time(hour, minute))
    tz = ZoneInfo(timezone_name)

    valid_utc_instants: set[datetime] = set()
    for fold in (0, 1):
        aware = naive.replace(tzinfo=tz, fold=fold)
        utc = aware.astimezone(UTC)
        roundtrip = utc.astimezone(tz).replace(tzinfo=None)
        if roundtrip == naive:
            valid_utc_instants.add(utc)

    if len(valid_utc_instants) >= 2:
        return ScheduleResolution(utc=min(valid_utc_instants), classification="ambiguous")
    if len(valid_utc_instants) == 1:
        return ScheduleResolution(utc=next(iter(valid_utc_instants)), classification="valid")

    return ScheduleResolution(
        utc=_first_valid_instant_after_gap(naive, tz), classification="nonexistent"
    )


def _first_valid_instant_after_gap(naive: datetime, tz: ZoneInfo) -> datetime:
    """Step forward from a nonexistent wall-clock time in fine increments
    until the wall-clock time round-trips correctly again — i.e. actually
    exists. Bounded and increment-based rather than "add the gap size",
    since the gap size is exactly what a nonexistent local time cannot
    report about itself in general (arbitrary zones, arbitrary gaps)."""
    candidate = naive
    elapsed = timedelta()
    while elapsed <= _GAP_SEARCH_BOUND:
        aware = candidate.replace(tzinfo=tz, fold=0)
        utc = aware.astimezone(UTC)
        if utc.astimezone(tz).replace(tzinfo=None) == candidate:
            return utc
        candidate += _GAP_SEARCH_STEP
        elapsed += _GAP_SEARCH_STEP
    raise ValueError(
        f"No valid local instant found within {_GAP_SEARCH_BOUND} after {naive} in {tz.key}"
    )


def compute_target_utc(local_date: date, briefing_time: str, timezone_name: str) -> datetime:
    """The UTC instant `briefing_time` on `local_date` in `timezone_name`
    refers to (ADR 0004 D48). Thin wrapper over
    `resolve_local_schedule_instant` for the many callers (dispatch
    planning, catch-up comparisons, `next_expected_run`) that only need the
    resolved instant, not the ambiguous/nonexistent classification."""
    return resolve_local_schedule_instant(local_date, briefing_time, timezone_name).utc


@dataclass(frozen=True)
class EnabledSchedule:
    user_id: uuid.UUID
    timezone: str
    briefing_time: str


async def list_enabled_schedules(session: AsyncSession) -> list[EnabledSchedule]:
    """Cross-user by necessity: the dispatcher must discover every opted-in
    user before any per-user (and therefore ownership-scoped) work begins.
    A deliberate, documented exception to the per-user-repository
    convention (see `ScheduledBriefRunRepository`) — everything this
    function's callers do afterwards is user-scoped again."""
    result = await session.execute(
        select(Preference.user_id).where(Preference.key == SCHEDULED_BRIEFS_ENABLED_KEY)
    )
    schedules: list[EnabledSchedule] = []
    for (user_id,) in result.all():
        if not await scheduled_briefs_enabled(session, user_id):
            continue
        user = await session.get(User, user_id)
        if user is None:
            continue
        briefing_time = await briefing_schedule(session, user_id)
        schedules.append(
            EnabledSchedule(user_id=user_id, timezone=user.timezone, briefing_time=briefing_time)
        )
    return schedules


@dataclass
class DispatchPlan:
    to_enqueue: list[ScheduledBriefRun] = field(default_factory=list)
    skipped_grace: int = 0
    already_handled: int = 0
    not_due: int = 0
    invalid_timezone: int = 0


async def plan_dispatch(session: AsyncSession, *, now: datetime) -> DispatchPlan:
    """Pure database logic — no Redis. Creates `pending`/`skipped` rows and
    returns the newly created `pending` ones for the caller to enqueue.
    Independently testable without a running queue."""
    plan = DispatchPlan()
    for schedule in await list_enabled_schedules(session):
        try:
            local_date = now.astimezone(ZoneInfo(schedule.timezone)).date()
        except ZoneInfoNotFoundError:
            logger.warning(
                "scheduled_briefs.invalid_timezone user_id=%s timezone=%s",
                schedule.user_id,
                schedule.timezone,
            )
            plan.invalid_timezone += 1
            continue

        runs = ScheduledBriefRunRepository(session, schedule.user_id)
        if await runs.get_for_local_date(local_date) is not None:
            plan.already_handled += 1
            continue

        target_utc = compute_target_utc(local_date, schedule.briefing_time, schedule.timezone)
        if now < target_utc:
            plan.not_due += 1
            continue

        run = ScheduledBriefRun(
            user_id=schedule.user_id,
            local_brief_date=local_date,
            scheduled_for_utc=target_utc,
            timezone_snapshot=schedule.timezone,
            briefing_time_snapshot=schedule.briefing_time,
        )
        if now - target_utc > GRACE_WINDOW:
            run.status = ScheduledRunStatus.skipped
            run.error_code = ERROR_MISSED_GRACE_WINDOW
            run.error_message = "Missed the catch-up window; no brief was generated for this date."
            run.completed_at = now
        else:
            run.status = ScheduledRunStatus.pending
            run.queue_job_id = job_id_for(schedule.user_id, local_date, 0)

        try:
            async with session.begin_nested():
                runs.add(run)
                await session.flush()
        except IntegrityError:
            # Another dispatcher tick/process already claimed this
            # user/local-date — the database uniqueness constraint
            # (ADR 0004 D48) is the final guard; yield to it silently.
            plan.already_handled += 1
            continue

        if run.status == ScheduledRunStatus.skipped:
            record_audit_event(
                session,
                user_id=schedule.user_id,
                actor="system:scheduler",
                event_type="scheduled_brief.skipped",
                entity_type="scheduled_brief_run",
                entity_id=str(run.id),
                metadata={"local_brief_date": local_date.isoformat(), "error_code": run.error_code},
            )
            plan.skipped_grace += 1
        else:
            plan.to_enqueue.append(run)
    return plan


@dataclass
class DispatchTickResult:
    due: int = 0
    enqueued: int = 0
    deduplicated: int = 0
    skipped_grace: int = 0
    recovered_stale: int = 0
    recovery_failed: int = 0
    drained: int = 0


# Stage 9 Delivery Phase 5: a distinct sentinel from ARQ's own `None`
# (meaning "deduplicated, a job with this id is already queued") — a Redis
# failure must never be mistaken for a successful dedup.
_ENQUEUE_FAILED = object()


async def _try_enqueue_job(redis: ArqRedis, external_id: str, job_id: str | None) -> Any:
    """Fails open, exactly like the deletion engine's `_enqueue` and the
    memory-recompute enqueue: any Redis error is logged and reported via the
    sentinel rather than raised, so one blip never aborts the whole cron
    tick (or the exception-handling path in `run_scheduled_generation`) —
    the row is simply left `enqueued_at=None` for `_recover_never_enqueued`
    to pick up on a later tick."""
    try:
        return await redis.enqueue_job(JOB_FUNCTION_NAME, external_id, _job_id=job_id)
    except Exception:
        logger.warning("scheduled_briefs.enqueue_failed job_id=%s", job_id, exc_info=True)
        return _ENQUEUE_FAILED


async def _recover_never_enqueued(session: AsyncSession, redis: ArqRedis, *, now: datetime) -> int:
    """The scheduled-brief analogue of the deletion engine's pending-drain
    pass: a run left `status=pending, enqueued_at=None` — either because
    `dispatch_tick`'s own enqueue attempt failed a moment ago, or because
    the transient-retry re-enqueue in `run_scheduled_generation` failed —
    is retried here on the next tick using its already-assigned
    `queue_job_id`, so ARQ's own dedup guard still applies correctly."""
    pending = await session.execute(
        select(ScheduledBriefRun).where(
            ScheduledBriefRun.status == ScheduledRunStatus.pending,
            ScheduledBriefRun.enqueued_at.is_(None),
        )
    )
    drained = 0
    for run in pending.scalars():
        job = await _try_enqueue_job(redis, str(run.id), run.queue_job_id)
        if job is _ENQUEUE_FAILED:
            continue
        run.enqueued_at = now
        drained += 1
    return drained


async def dispatch_tick(
    redis: ArqRedis, session: AsyncSession, *, now: datetime
) -> DispatchTickResult:
    """One cron tick: plan (DB-only), enqueue what's due, then recover any
    stale `running` rows. Called once a minute by the arq cron job."""
    plan = await plan_dispatch(session, now=now)
    enqueued = 0
    deduplicated = 0
    for run in plan.to_enqueue:
        job = await _try_enqueue_job(redis, str(run.id), run.queue_job_id)
        if job is _ENQUEUE_FAILED:
            continue
        run.enqueued_at = now
        if job is None:
            deduplicated += 1
            logger.info(
                "scheduled_briefs.enqueue_deduplicated run_id=%s job_id=%s",
                run.id,
                run.queue_job_id,
            )
        else:
            enqueued += 1
            record_audit_event(
                session,
                user_id=run.user_id,
                actor="system:scheduler",
                event_type="scheduled_brief.enqueued",
                entity_type="scheduled_brief_run",
                entity_id=str(run.id),
                metadata={
                    "local_brief_date": run.local_brief_date.isoformat(),
                    "job_id": run.queue_job_id,
                    "lag_seconds": int((now - run.scheduled_for_utc).total_seconds()),
                },
            )
    await session.flush()
    recovery = await recover_stale_running(session, redis, now=now)
    drained = await _recover_never_enqueued(session, redis, now=now)
    await session.commit()
    return DispatchTickResult(
        due=len(plan.to_enqueue) + plan.skipped_grace,
        enqueued=enqueued,
        deduplicated=deduplicated,
        skipped_grace=plan.skipped_grace,
        recovered_stale=recovery.requeued,
        drained=drained,
        recovery_failed=recovery.failed,
    )


@dataclass
class RecoveryResult:
    requeued: int = 0
    failed: int = 0


async def recover_stale_running(
    session: AsyncSession, redis: ArqRedis, *, now: datetime
) -> RecoveryResult:
    """A run stuck `running` past the stale threshold means its worker
    crashed without resolving it — never left hanging forever
    (ADR 0004 D49). Cross-user by necessity, like `list_enabled_schedules`."""
    cutoff = now - STALE_RUNNING_THRESHOLD
    result = await session.execute(
        select(ScheduledBriefRun).where(
            ScheduledBriefRun.status == ScheduledRunStatus.running,
            ScheduledBriefRun.started_at < cutoff,
        )
    )
    outcome = RecoveryResult()
    for run in result.scalars():
        if run.attempt_count >= MAX_ATTEMPTS:
            run.status = ScheduledRunStatus.failed
            run.error_code = ERROR_WORKER_STALE_TIMEOUT
            run.error_message = "The worker did not finish in time after repeated attempts."
            run.completed_at = now
            record_audit_event(
                session,
                user_id=run.user_id,
                actor="system:scheduler",
                event_type="scheduled_brief.failed",
                entity_type="scheduled_brief_run",
                entity_id=str(run.id),
                metadata={"error_code": run.error_code},
            )
            outcome.failed += 1
            continue
        run.status = ScheduledRunStatus.pending
        run.queue_job_id = job_id_for(run.user_id, run.local_brief_date, run.attempt_count)
        run.started_at = None
        # A stale enqueue timestamp from the run's earlier (now-stale)
        # attempt must never survive a failed re-enqueue here, or
        # `_recover_never_enqueued`'s `enqueued_at IS NULL` filter would
        # never find this row again on a later tick.
        run.enqueued_at = None
        job = await _try_enqueue_job(redis, str(run.id), run.queue_job_id)
        if job is _ENQUEUE_FAILED:
            continue
        run.enqueued_at = now
        record_audit_event(
            session,
            user_id=run.user_id,
            actor="system:scheduler",
            event_type="scheduled_brief.enqueued",
            entity_type="scheduled_brief_run",
            entity_id=str(run.id),
            metadata={"job_id": run.queue_job_id, "recovered": True},
        )
        outcome.requeued += 1
    await session.flush()
    return outcome


async def next_expected_run(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    now: datetime,
    timezone_name: str,
    briefing_time: str,
) -> datetime:
    """The local date/target-instant the next scheduled run will use —
    today's if not yet claimed and still inside the catch-up window,
    otherwise tomorrow's. Display-only (Settings "next run"); the
    dispatcher always recomputes independently and is the sole authority."""
    local_date = now.astimezone(ZoneInfo(timezone_name)).date()
    existing_today = await ScheduledBriefRunRepository(session, user_id).get_for_local_date(
        local_date
    )
    if existing_today is None:
        target = compute_target_utc(local_date, briefing_time, timezone_name)
        if now <= target + GRACE_WINDOW:
            return target
    tomorrow = local_date + timedelta(days=1)
    return compute_target_utc(tomorrow, briefing_time, timezone_name)


def classify_failure(exc: BaseException) -> tuple[str, str, bool]:
    """(error_code, safe_message, is_transient). Never includes the
    original exception text — it could contain source content or internals
    — only a fixed, safe, closed-vocabulary message per class."""
    if isinstance(exc, redis_exceptions.RedisError):
        return ERROR_REDIS_UNAVAILABLE, "The job queue was temporarily unavailable.", True
    if isinstance(exc, OperationalError):
        return ERROR_DATABASE_UNAVAILABLE, "The database was temporarily unavailable.", True
    if isinstance(exc, TimeoutError):
        return ERROR_WORKER_TIMEOUT, "Brief generation timed out.", True
    return ERROR_GENERATION_FAILED, "Brief generation failed and was not completed.", False


async def _mark_terminal(
    session: AsyncSession,
    run: ScheduledBriefRun,
    *,
    status: ScheduledRunStatus,
    error_code: str,
    message: str,
    now: datetime,
) -> None:
    run.status = status
    run.error_code = error_code
    run.error_message = message
    run.completed_at = now
    record_audit_event(
        session,
        user_id=run.user_id,
        actor="system:scheduler",
        event_type=f"scheduled_brief.{status}",
        entity_type="scheduled_brief_run",
        entity_id=str(run.id),
        metadata={"error_code": error_code},
    )
    await session.commit()


async def run_scheduled_generation(
    session: AsyncSession,
    redis: ArqRedis,
    run_id: uuid.UUID,
    *,
    now: datetime,
    llm_provider: LLMProvider | None = None,
) -> None:
    """The per-user scheduled-generation entry point (ADR 0004 D48/D49).

    Reuses `BriefService` exactly like the manual `/briefs/generate` route
    — there is no separate scheduler-specific brief implementation. Never
    approves or executes a proposal: it only calls the same
    extraction/composition/proposal-generation pipeline every brief goes
    through, which itself never approves anything.
    """
    claim = await session.execute(
        update(ScheduledBriefRun)
        .where(
            ScheduledBriefRun.id == run_id,
            ScheduledBriefRun.status == ScheduledRunStatus.pending,
        )
        .values(
            status=ScheduledRunStatus.running,
            started_at=now,
            attempt_count=ScheduledBriefRun.attempt_count + 1,
        )
        .returning(ScheduledBriefRun.id)
    )
    claimed = claim.first()
    await session.commit()
    if claimed is None:
        # Already claimed by a racing worker, already terminal, or the run
        # no longer exists — never act twice on the same run (two
        # generation workers racing must produce exactly one brief).
        return

    run = await session.get(ScheduledBriefRun, run_id, populate_existing=True)
    if run is None:
        # The claim above matched a row, but `ScheduledBriefRun.user_id`
        # cascades on user delete like every other user-owned table
        # (`_user_fk()`) — a delete landing in the gap between the claim
        # commit and this read removes the run itself. Nothing to act on.
        return

    # Reachable only in the same narrow gap as above, if a delete lands
    # between this line and the one above (the run row survived long enough
    # to be re-fetched, but not the user). No feature deletes a user today,
    # so this is defence in depth for when account deletion ships.
    user = await session.get(User, run.user_id)
    if user is None:
        await _mark_terminal(
            session,
            run,
            status=ScheduledRunStatus.skipped,
            error_code=ERROR_USER_UNAVAILABLE,
            message="The user account is no longer available.",
            now=now,
        )
        return
    if not await scheduled_briefs_enabled(session, run.user_id):
        await _mark_terminal(
            session,
            run,
            status=ScheduledRunStatus.skipped,
            error_code=ERROR_SCHEDULE_DISABLED,
            message="Scheduled briefs were turned off before this run executed.",
            now=now,
        )
        return

    # Idempotency across a worker crash after the brief committed but
    # before this run was marked succeeded (ADR 0004 D49): find it first,
    # never regenerate.
    existing_brief = (
        await session.execute(select(Brief).where(Brief.scheduled_run_id == run.id))
    ).scalar_one_or_none()
    if existing_brief is not None:
        run.brief_id = existing_brief.id
        run.status = ScheduledRunStatus.succeeded
        run.completed_at = now
        record_audit_event(
            session,
            user_id=run.user_id,
            actor="system:scheduler",
            event_type="scheduled_brief.succeeded",
            entity_type="scheduled_brief_run",
            entity_id=str(run.id),
            metadata={"brief_id": str(existing_brief.id), "recovered_existing": True},
        )
        await session.commit()
        return

    try:
        brief = await BriefService(session, run.user_id, llm_provider=llm_provider).generate(
            timezone=run.timezone_snapshot,
            reference=now,
            generation_trigger="scheduled",
            scheduled_run_id=run.id,
        )
    except Exception as exc:
        await session.rollback()
        reloaded = await session.get(ScheduledBriefRun, run_id, populate_existing=True)
        if reloaded is None:  # pragma: no cover - defensive
            return
        error_code, message, transient = classify_failure(exc)
        if transient and reloaded.attempt_count < MAX_ATTEMPTS:
            reloaded.status = ScheduledRunStatus.pending
            reloaded.queue_job_id = job_id_for(
                reloaded.user_id, reloaded.local_brief_date, reloaded.attempt_count
            )
            reloaded.error_code = error_code
            reloaded.error_message = message
            # Cleared before committing (not just on a failed enqueue below):
            # `_recover_never_enqueued`'s `enqueued_at IS NULL` filter must
            # see this row as needing a retry even if Redis is down right
            # now, and this commit is the durability checkpoint a crash
            # right after it must leave consistent.
            reloaded.enqueued_at = None
            await session.commit()
            job = await _try_enqueue_job(redis, str(reloaded.id), reloaded.queue_job_id)
            if job is not _ENQUEUE_FAILED:
                reloaded.enqueued_at = now
            await session.commit()
        else:
            await _mark_terminal(
                session,
                reloaded,
                status=ScheduledRunStatus.failed,
                error_code=error_code,
                message=message,
                now=now,
            )
        logger.warning(
            "scheduled_briefs.generation_failed run_id=%s error_code=%s", run_id, error_code
        )
        return

    run.brief_id = brief.id
    run.status = ScheduledRunStatus.succeeded
    run.completed_at = now
    record_audit_event(
        session,
        user_id=run.user_id,
        actor="system:scheduler",
        event_type="scheduled_brief.succeeded",
        entity_type="scheduled_brief_run",
        entity_id=str(run.id),
        metadata={"brief_id": str(brief.id), "brief_version": brief.version},
    )
    await session.commit()


__all__ = [
    "ERROR_DATABASE_UNAVAILABLE",
    "ERROR_GENERATION_FAILED",
    "ERROR_INVALID_TIMEZONE",
    "ERROR_MISSED_GRACE_WINDOW",
    "ERROR_REDIS_UNAVAILABLE",
    "ERROR_SCHEDULE_DISABLED",
    "ERROR_USER_UNAVAILABLE",
    "ERROR_WORKER_STALE_TIMEOUT",
    "ERROR_WORKER_TIMEOUT",
    "GRACE_WINDOW",
    "JOB_FUNCTION_NAME",
    "MAX_ATTEMPTS",
    "STALE_RUNNING_THRESHOLD",
    "DispatchPlan",
    "DispatchTickResult",
    "EnabledSchedule",
    "RecoveryResult",
    "ScheduleClassification",
    "ScheduleResolution",
    "classify_failure",
    "compute_target_utc",
    "dispatch_tick",
    "job_deserializer",
    "job_id_for",
    "job_serializer",
    "list_enabled_schedules",
    "next_expected_run",
    "plan_dispatch",
    "recover_stale_running",
    "resolve_local_schedule_instant",
    "run_scheduled_generation",
]
