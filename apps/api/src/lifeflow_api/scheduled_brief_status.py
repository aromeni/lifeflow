"""Read-only scheduled-brief status (ADR 0004 D48/D49/D50).

The smallest useful surface Settings/Today need: whether the user has
opted in, their configured time/timezone, the next expected run, the
latest run's outcome, the brief it produced (if any), and whether the
scheduler is currently reachable at all. Never exposes ARQ internals,
Redis keys, or stack traces.
"""

import logging
from datetime import UTC, date, datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from lifeflow_api.deps import CurrentUser, DbSession
from lifeflow_api.models import Brief
from lifeflow_api.preferences import (
    BRIEFING_TIME_KEY,
    SCHEDULED_BRIEFS_ENABLED_KEY,
    resolved_preferences,
)
from lifeflow_api.repositories import ScheduledBriefRunRepository
from lifeflow_api.scheduled_briefs import next_expected_run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduled-briefs")


class ScheduledBriefStatusResponse(BaseModel):
    enabled: bool
    timezone: str
    briefing_time: str
    # None only when disabled — there is nothing to be "next" about.
    next_run_at: datetime | None
    latest_run_status: str | None
    latest_run_local_date: date | None
    latest_run_completed_at: datetime | None
    latest_run_error_code: str | None
    latest_brief_id: str | None
    latest_brief_version: int | None
    scheduler_available: bool


async def _scheduler_capability_ready(redis_url: str) -> bool:
    """A short-timeout, best-effort ping — never allowed to hang the API,
    and never raised past this function (Redis being down must not break
    ordinary routes)."""
    try:
        import redis.asyncio as aioredis

        client: aioredis.Redis = aioredis.from_url(  # type: ignore[no-untyped-call]
            redis_url, socket_connect_timeout=0.5, socket_timeout=0.5
        )
    except Exception:
        return False
    try:
        return bool(await client.ping())
    except Exception:
        return False
    finally:
        await client.aclose()


@router.get("/status", response_model=ScheduledBriefStatusResponse)
async def get_scheduled_brief_status(
    request: Request, user: CurrentUser, session: DbSession
) -> ScheduledBriefStatusResponse:
    resolved = await resolved_preferences(session, user.id)
    enabled = bool(resolved[SCHEDULED_BRIEFS_ENABLED_KEY]["enabled"])
    briefing_time = str(resolved[BRIEFING_TIME_KEY]["value"])

    next_run_at = None
    if enabled:
        next_run_at = await next_expected_run(
            session,
            user.id,
            now=datetime.now(UTC),
            timezone_name=user.timezone,
            briefing_time=briefing_time,
        )

    latest_run = await ScheduledBriefRunRepository(session, user.id).latest()
    latest_brief_id: str | None = None
    latest_brief_version: int | None = None
    if latest_run is not None and latest_run.brief_id is not None:
        brief = await session.get(Brief, latest_run.brief_id)
        if brief is not None:
            latest_brief_id = str(brief.id)
            latest_brief_version = brief.version

    # Read from THIS app instance's settings (`request.app.state.settings`),
    # never the process-wide `get_settings()` cache — the two can differ
    # (e.g. per-test app instances), and this must reflect the app actually
    # serving the request.
    scheduler_available = await _scheduler_capability_ready(request.app.state.settings.redis_url)

    return ScheduledBriefStatusResponse(
        enabled=enabled,
        timezone=user.timezone,
        briefing_time=briefing_time,
        next_run_at=next_run_at,
        latest_run_status=str(latest_run.status) if latest_run is not None else None,
        latest_run_local_date=latest_run.local_brief_date if latest_run is not None else None,
        latest_run_completed_at=latest_run.completed_at if latest_run is not None else None,
        latest_run_error_code=latest_run.error_code if latest_run is not None else None,
        latest_brief_id=latest_brief_id,
        latest_brief_version=latest_brief_version,
        scheduler_available=scheduler_available,
    )


__all__ = ["ScheduledBriefStatusResponse", "router"]
