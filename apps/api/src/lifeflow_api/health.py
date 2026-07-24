"""Liveness, readiness, and public capability endpoints.

/health — liveness: the process is up; no dependencies are touched.
/ready  — readiness: dependencies (currently PostgreSQL) are reachable.
/config — public, unauthenticated capability flags the frontend needs before
          any session exists (e.g. whether to render "Sign in with Google").

Stage 9 Delivery Phase 4 (ADR 0005 D64/D81): all three routes are explicit
rate-limit exemptions, never silently unclassified. `/health` and `/ready`
are infrastructure liveness/readiness probes that must never be throttled —
limiting them could make an orchestrator kill a healthy process. `/config` is
a static, cost-free, unauthenticated capability flag with no user data,
needed before any session or CSRF context exists on every page load.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from lifeflow_api.db import check_database
from lifeflow_api.google_wiring import google_integration_ready

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthStatus(BaseModel):
    status: str


class PublicConfig(BaseModel):
    # Reuses `google_wiring.google_integration_ready` — the same check the
    # sync/execute routes use — so this can never claim Google is available
    # when it isn't actually wired (ADR 0003 D23).
    google_oauth_enabled: bool


@router.get("/health")
async def health() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/config")
async def config(request: Request) -> PublicConfig:
    return PublicConfig(google_oauth_enabled=google_integration_ready(request))


@router.get(
    "/ready",
    response_model=HealthStatus,
    responses={503: {"description": "A dependency is unavailable"}},
)
async def ready(request: Request) -> JSONResponse:
    try:
        await check_database(request.app.state.engine)
    except Exception:
        logger.error("Readiness check failed: database unreachable", exc_info=True)
        return JSONResponse(
            status_code=503, content=HealthStatus(status="unavailable").model_dump()
        )
    return JSONResponse(status_code=200, content=HealthStatus(status="ok").model_dump())
