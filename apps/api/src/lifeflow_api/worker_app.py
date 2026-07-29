"""Stage 8 Phase 2: arq worker glue (ADR 0004 D48).

Deliberately thin: every decision — dispatch planning, DST/catch-up
handling, per-user generation, failure classification — lives in
`lifeflow_api.scheduled_briefs`, an ordinary pytest-covered module. This
file only wires that logic to arq's cron/job/lifecycle hooks and to a
database session and Redis pool, matching the pattern the app already uses
for the LLM provider and Google clients (off/absent by default; explicit
opt-in via configuration).

Run locally with:
    uv run arq lifeflow_api.worker_app.WorkerSettings
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from arq import cron
from arq.connections import ArqRedis, RedisSettings
from arq.cron import CronJob
from sqlalchemy.ext.asyncio import async_sessionmaker

from lifeflow_api.action_proposal_service import recover_stale_pending_executions
from lifeflow_api.config import get_settings
from lifeflow_api.correlation import with_worker_correlation
from lifeflow_api.db import create_engine
from lifeflow_api.deletion import (
    build_settings_horizons,
    recover_stale_operations,
    run_operation,
)
from lifeflow_api.logging_setup import configure_logging
from lifeflow_api.memory_inference import expire_all_stale_memory
from lifeflow_api.memory_inference import recompute_user_memory as run_recompute
from lifeflow_api.metrics import stale_pending_recovered_total, with_worker_metrics
from lifeflow_api.retention import scan_and_create_retention_operations
from lifeflow_api.scheduled_briefs import (
    dispatch_tick,
    job_deserializer,
    job_serializer,
    run_scheduled_generation,
)
from lifeflow_api.timeouts import (
    database_statement_timeout_ms,
    google_httpx_timeout,
)

logger = logging.getLogger(__name__)


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    # Stage 9 Delivery Phase 5: without this, `with_worker_correlation`'s
    # per-job correlation id is set in a contextvar that nothing ever reads
    # — the worker process previously used Python's default plain-text
    # logging, silently dropping the very traceability this phase added.
    # Matches `main.py::create_app`'s identical call for the API process.
    configure_logging(settings.log_level)
    engine = create_engine(
        settings.database_url, statement_timeout_ms=database_statement_timeout_ms(settings)
    )
    ctx["engine"] = engine
    ctx["sessionmaker"] = async_sessionmaker(engine, expire_on_commit=False)
    ctx["llm_provider"] = None
    if settings.llm_extraction_enabled and settings.anthropic_api_key:
        from lifeflow_api.llm.anthropic_provider import AnthropicProvider

        ctx["llm_provider"] = AnthropicProvider(
            settings.anthropic_api_key, model=settings.anthropic_model
        )
    # Real, best-effort provider revocation for account deletion (Stage 9
    # Delivery Phase 2). Wired only when Google is genuinely configured; demo/CI
    # leave it None, so local credential erasure still happens and nothing ever
    # blocks on a provider call. This is the production composition root for the
    # revoker — mirroring how the disconnect route obtains its OAuth client.
    ctx["google_http_client"] = None
    ctx["revoker"] = None
    if settings.google_oauth_enabled and settings.token_key:
        import httpx

        from lifeflow_api.google.oauth import GoogleOAuthClient
        from lifeflow_api.google_wiring import build_account_revoker
        from lifeflow_api.security.token_cipher import AesGcmTokenCipher

        http = httpx.AsyncClient(timeout=google_httpx_timeout(settings))
        ctx["google_http_client"] = http
        cipher = AesGcmTokenCipher(settings.token_key, settings.token_key_id)
        ctx["revoker"] = build_account_revoker(cipher, GoogleOAuthClient(http))
    logger.info("scheduled_briefs.worker_started")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()
    http = ctx.get("google_http_client")
    if http is not None:
        await http.aclose()
    logger.info("scheduled_briefs.worker_stopped")


@with_worker_metrics("dispatch_scheduled_briefs")
@with_worker_correlation
async def dispatch_scheduled_briefs(ctx: dict[str, Any]) -> None:
    """The per-minute cron entry point (ADR 0004 D48): one static job, never
    one cron entry per user."""
    redis: ArqRedis = ctx["redis"]
    sessionmaker = ctx["sessionmaker"]
    now = datetime.now(UTC)
    async with sessionmaker() as session:
        result = await dispatch_tick(redis, session, now=now)
    logger.info(
        "scheduled_briefs.dispatch_tick due=%s enqueued=%s deduplicated=%s "
        "skipped_grace=%s recovered_stale=%s recovery_failed=%s drained=%s",
        result.due,
        result.enqueued,
        result.deduplicated,
        result.skipped_grace,
        result.recovered_stale,
        result.recovery_failed,
        result.drained,
    )
    recovered_total = result.recovered_stale + result.drained
    if recovered_total:
        stale_pending_recovered_total.labels(kind="scheduled_brief_run").inc(recovered_total)


@with_worker_metrics("generate_scheduled_brief")
@with_worker_correlation
async def generate_scheduled_brief(ctx: dict[str, Any], run_id: str) -> None:
    """The per-user job body. `run_id` is the only argument — an internal
    identifier, never user content — and every other fact (enablement,
    timezone, briefing time) is reloaded from PostgreSQL, never trusted
    from the queue payload."""
    redis: ArqRedis = ctx["redis"]
    sessionmaker = ctx["sessionmaker"]
    llm_provider = ctx.get("llm_provider")
    now = datetime.now(UTC)
    async with sessionmaker() as session:
        await run_scheduled_generation(
            session, redis, uuid.UUID(run_id), now=now, llm_provider=llm_provider
        )


@with_worker_metrics("recompute_user_memory")
@with_worker_correlation
async def recompute_user_memory(ctx: dict[str, Any], user_id: str) -> None:
    """Stage 8 Phase 3 (ADR 0004 D56): recompute one user's inferred memory.

    Named to match `memory_inference.JOB_FUNCTION_NAME` so arq routes the
    enqueued job here (the same convention `generate_scheduled_brief` uses).
    `user_id` is the only argument — never draft content — and every fact is
    reloaded from PostgreSQL. Best-effort and idempotent: the recompute
    rescans the user's recent eligible proposals, so a missed enqueue
    self-heals here; it commits its own work and never approves or executes
    anything."""
    sessionmaker = ctx["sessionmaker"]
    now = datetime.now(UTC)
    async with sessionmaker() as session:
        await run_recompute(session, uuid.UUID(user_id), now=now)
        await session.commit()
    logger.info("memory.recompute_done user_id=%s", user_id)


@with_worker_metrics("expire_stale_memory")
@with_worker_correlation
async def expire_stale_memory(ctx: dict[str, Any]) -> None:
    """Daily maintenance (ADR 0004 D54): expire inferred-memory candidates
    whose confidence has decayed below the floor, for every user — so a stale
    candidate is never represented as active even if its owner never opens
    Settings again (expiry must not depend on a user action). Idempotent and
    safe to run repeatedly; confirmed explicit preferences are never touched."""
    sessionmaker = ctx["sessionmaker"]
    now = datetime.now(UTC)
    async with sessionmaker() as session:
        expired = await expire_all_stale_memory(session, now=now)
    logger.info("memory.expire_stale_done expired=%s", expired)


@with_worker_metrics("run_deletion_operation")
@with_worker_correlation
async def run_deletion_operation(ctx: dict[str, Any], operation_id: str) -> None:
    """Stage 9 Delivery Phase 2 (ADR 0005): run one durable deletion operation
    to completion in bounded batches. `operation_id` is the only argument — an
    internal identifier, never scope, counts, or personal data — and every
    other fact is reloaded from PostgreSQL. Idempotent and resumable: a crash
    leaves the operation `running` for the cron to recover."""
    sessionmaker = ctx["sessionmaker"]
    settings = get_settings()
    now = datetime.now(UTC)
    async with sessionmaker() as session:
        await run_operation(
            session,
            uuid.UUID(operation_id),
            now=now,
            horizons=build_settings_horizons(settings),
            batch_size=settings.deletion_batch_size,
            max_attempts=settings.deletion_max_attempts,
            # The real best-effort provider revoker (built in on_startup when
            # Google is configured; None otherwise — local erasure still runs).
            revoker=ctx.get("revoker"),
        )
    logger.info("deletion.operation_done operation_id=%s", operation_id)


@with_worker_metrics("dispatch_deletion_operations")
@with_worker_correlation
async def dispatch_deletion_operations(ctx: dict[str, Any]) -> None:
    """Per-minute cron: create today's retention operations (when enabled),
    then drain any `pending` operations that were never enqueued (Redis was
    down at confirm time) and recover `running` operations whose worker died.
    One static cron job, never one entry per user."""
    redis: ArqRedis = ctx["redis"]
    sessionmaker = ctx["sessionmaker"]
    settings = get_settings()
    now = datetime.now(UTC)
    async with sessionmaker() as session:
        if settings.retention_enforcement_enabled:
            result, _ = await scan_and_create_retention_operations(
                session,
                horizons=build_settings_horizons(settings),
                now=now,
                max_operations=settings.retention_max_operations_per_tick,
            )
            await session.commit()
            logger.info(
                "deletion.retention_scan created=%s reused=%s", result.created, result.reused
            )
        recovery = await recover_stale_operations(
            session,
            redis,
            now=now,
            heartbeat_timeout=timedelta(minutes=settings.deletion_heartbeat_timeout_minutes),
            max_attempts=settings.deletion_max_attempts,
        )
    logger.info(
        "deletion.dispatch_tick drained=%s requeued=%s failed=%s",
        recovery.drained,
        recovery.requeued,
        recovery.failed,
    )
    recovered_total = recovery.drained + recovery.requeued
    if recovered_total:
        stale_pending_recovered_total.labels(kind="deletion_operation").inc(recovered_total)


@with_worker_metrics("recover_stale_action_executions")
@with_worker_correlation
async def recover_stale_action_executions(ctx: dict[str, Any]) -> None:
    """Stage 9 Delivery Phase 5 (§10): per-minute cross-user sweep for
    `ActionExecution` rows stuck `pending` past `STALE_PENDING_AGE` (a
    worker that crashed after the durable pre-call commit but before the
    real executor call resolved). Flips them to `uncertain` — the same
    terminal-for-now, never-auto-retried state `execute()`'s own re-entry
    guard already assigns — without depending on anyone ever revisiting
    that specific proposal. One static cron job, never one entry per user."""
    sessionmaker = ctx["sessionmaker"]
    now = datetime.now(UTC)
    async with sessionmaker() as session:
        recovered = await recover_stale_pending_executions(session, now=now)
    if recovered:
        logger.info("execution.stale_pending_recovered count=%s", recovered)
        stale_pending_recovered_total.labels(kind="action_execution").inc(recovered)


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    functions: ClassVar[list[Callable[..., Awaitable[None]]]] = [
        generate_scheduled_brief,
        recompute_user_memory,
        run_deletion_operation,
    ]
    # mypy: arq's `WorkerCoroutine` protocol requires (among the call
    # signature) a `__qualname__: str` attribute — satisfied at runtime by
    # every plain `async def` (including `with_worker_correlation`'s
    # `functools.wraps`-decorated wrapper, which copies it from the
    # original), but not by the abstract `Callable[..., Awaitable[T]]` type
    # that decorator's return annotation gives these functions from mypy's
    # perspective. A real, structural typeshed limitation for this specific
    # arq Protocol, not a real type error — every `cron(...)` here.
    cron_jobs: ClassVar[list[CronJob]] = [
        # `second=0` (the arq default) fires once per minute, at :00 —
        # matching ADR 0004 D48's "a modest interval, preferably once per
        # minute", not a per-user schedule registered dynamically.
        cron(dispatch_scheduled_briefs, second=0, run_at_startup=True, max_tries=1),  # type: ignore[arg-type]
        # Stage 9 Delivery Phase 2 (ADR 0005): retention scan + pending-drain +
        # stale-operation recovery, once a minute. One static job.
        cron(dispatch_deletion_operations, second=0, run_at_startup=True, max_tries=1),  # type: ignore[arg-type]
        # Once a day at 03:00 UTC — inferred-memory decay is a 30-day
        # half-life, so daily maintenance is ample to keep stale candidates
        # from being shown as active (ADR 0004 D54). Read-time expiry on the
        # memory API is the fast path between runs; this guarantees expiry even
        # for a user who never opens Settings again.
        cron(expire_stale_memory, hour=3, minute=0, second=0, max_tries=1),  # type: ignore[arg-type]
        # Stage 9 Delivery Phase 5: cross-user stale-pending-execution sweep,
        # once a minute — the durable-execution-recovery analogue of the two
        # cron jobs above, closing the one gap those two didn't already
        # cover (see `recover_stale_action_executions` docstring).
        cron(recover_stale_action_executions, second=0, run_at_startup=True, max_tries=1),  # type: ignore[arg-type]
    ]
    redis_settings = _redis_settings()
    on_startup = on_startup
    on_shutdown = on_shutdown
    job_serializer = job_serializer
    job_deserializer = job_deserializer
    # Retries are handled entirely inside `scheduled_briefs` (bounded,
    # classified, and recorded on the durable run row) — arq's own
    # automatic per-job retry is disabled so there is exactly one retry
    # authority, not two that could disagree.
    max_tries = 1


__all__ = [
    "WorkerSettings",
    "dispatch_deletion_operations",
    "dispatch_scheduled_briefs",
    "expire_stale_memory",
    "generate_scheduled_brief",
    "recompute_user_memory",
    "recover_stale_action_executions",
    "run_deletion_operation",
]
