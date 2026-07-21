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
from datetime import UTC, datetime
from typing import Any, ClassVar

from arq import cron
from arq.connections import ArqRedis, RedisSettings
from arq.cron import CronJob
from sqlalchemy.ext.asyncio import async_sessionmaker

from lifeflow_api.config import get_settings
from lifeflow_api.db import create_engine
from lifeflow_api.scheduled_briefs import (
    dispatch_tick,
    job_deserializer,
    job_serializer,
    run_scheduled_generation,
)

logger = logging.getLogger(__name__)


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    ctx["engine"] = engine
    ctx["sessionmaker"] = async_sessionmaker(engine, expire_on_commit=False)
    ctx["llm_provider"] = None
    if settings.llm_extraction_enabled and settings.anthropic_api_key:
        from lifeflow_api.llm.anthropic_provider import AnthropicProvider

        ctx["llm_provider"] = AnthropicProvider(
            settings.anthropic_api_key, model=settings.anthropic_model
        )
    logger.info("scheduled_briefs.worker_started")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()
    logger.info("scheduled_briefs.worker_stopped")


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
        "skipped_grace=%s recovered_stale=%s recovery_failed=%s",
        result.due,
        result.enqueued,
        result.deduplicated,
        result.skipped_grace,
        result.recovered_stale,
        result.recovery_failed,
    )


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


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    functions: ClassVar[list[Callable[..., Awaitable[None]]]] = [generate_scheduled_brief]
    cron_jobs: ClassVar[list[CronJob]] = [
        # `second=0` (the arq default) fires once per minute, at :00 —
        # matching ADR 0004 D48's "a modest interval, preferably once per
        # minute", not a per-user schedule registered dynamically.
        cron(dispatch_scheduled_briefs, second=0, run_at_startup=True, max_tries=1)
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


__all__ = ["WorkerSettings", "dispatch_scheduled_briefs", "generate_scheduled_brief"]
