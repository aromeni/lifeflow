"""Liveness, readiness, and public capability endpoints.

/health — liveness: the process is up; no dependencies are touched. Must
          never fail because Google (or any per-account provider) is
          unavailable — provider health is per-connected-account, not a
          property of the process.
/ready  — readiness: PostgreSQL is reachable (blocking — the API cannot
          safely serve its core functions without it) and, best-effort,
          whether Redis is reachable (never blocking — rate limiting is
          fail-open, ADR 0005 D64, and Redis is an optional dependency for
          the API process even when configured, ADR 0004 D48; a queue/worker
          outage is its own separately-reported, per-feature status, e.g.
          `GET /scheduled-briefs/status`). Reported as a closed, safe
          dependency-name list, never a connection string or exception.
/config — public, unauthenticated capability flags the frontend needs before
          any session exists (e.g. whether to render "Sign in with Google").
          Stage 11A Phase 6A.1: three independent booleans — provider
          configuration and each of the two split OAuth flows — so the
          frontend can represent the same split the backend already
          enforces, rather than collapsing both flows onto one flag.
/metrics — Prometheus text-exposition operational metrics (Stage 9 Delivery
          Phase 5, `metrics.py`); bounded-cardinality labels only, never a
          user id, email, or exception message (threat model T6).

Stage 9 Delivery Phase 4 (ADR 0005 D64/D81): all four routes are explicit
rate-limit exemptions, never silently unclassified. `/health` and `/ready`
are infrastructure liveness/readiness probes that must never be throttled —
limiting them could make an orchestrator kill a healthy process. `/config` is
a static, cost-free, unauthenticated capability flag with no user data,
needed before any session or CSRF context exists on every page load.
`/metrics` is scraped frequently by design (Stage 9 Delivery Phase 5) and
must never be throttled for the same reason as the liveness/readiness probes.

Stage 9 Delivery Phase 5: the Redis ping below is uncached, run fresh on
every `/ready` call — deliberately, not an oversight. It is a single bounded
`PING` (`worker_health_check_timeout_seconds`, default 0.5s), not an
expensive provider round-trip, so its cost at ordinary orchestrator probe
frequencies (every few seconds to a minute) is negligible; a cache would add
staleness risk for no measured benefit. The PostgreSQL check is likewise
uncached, unchanged from before this phase.
"""

import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from lifeflow_api.db import check_database
from lifeflow_api.google_wiring import google_integration_ready
from lifeflow_api.metrics import (
    database_readiness_failures_total,
    redis_degraded_total,
    render_latest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthStatus(BaseModel):
    status: str


class ReadyStatus(BaseModel):
    status: str
    # A closed, bounded-cardinality list of safe dependency names (today,
    # only ever `["redis"]` or `[]`) — never a hostname, connection string,
    # or exception. Empty (the default) means every checked dependency is
    # reachable.
    degraded_dependencies: list[str] = []


class PublicConfig(BaseModel):
    # Stage 11A Phase 6A.1: three independent, content-free capability
    # booleans — never a client ID, secret, redirect URI, account address,
    # project ID, or token. `google_provider_configured` reuses
    # `google_wiring.google_integration_ready` (ADR 0003 D23) and is
    # configuration-completeness only; it must never by itself imply either
    # OAuth flow is authorised for a user to start. Each per-flow boolean
    # already folds provider-configuredness into its own value, so the
    # frontend never has to combine them itself and can't accidentally
    # treat "configured" as "authorised" the way the pre-Phase-6A.1 landing
    # page did.
    google_provider_configured: bool
    google_oidc_signin_enabled: bool
    google_connector_oauth_enabled: bool


async def check_redis(redis_url: str, *, timeout_seconds: float) -> bool:
    """A short-timeout, best-effort ping — never allowed to hang the
    request, and never raises past this function (Redis being down must
    never break an ordinary route or readiness itself, per its fail-open
    architecture). Shared by `/ready` and `GET /scheduled-briefs/status`."""
    try:
        import redis.asyncio as aioredis

        client: aioredis.Redis = aioredis.from_url(  # type: ignore[no-untyped-call]
            redis_url, socket_connect_timeout=timeout_seconds, socket_timeout=timeout_seconds
        )
    except Exception:
        return False
    try:
        return bool(await client.ping())
    except Exception:
        return False
    finally:
        await client.aclose()


@router.get("/health")
async def health() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/config")
async def config(request: Request) -> PublicConfig:
    settings = request.app.state.settings
    provider_configured = google_integration_ready(request)
    return PublicConfig(
        google_provider_configured=provider_configured,
        google_oidc_signin_enabled=provider_configured and settings.google_oidc_signin_enabled,
        google_connector_oauth_enabled=(
            provider_configured and settings.google_connector_oauth_enabled
        ),
    )


@router.get("/metrics")
async def metrics() -> Response:
    body, content_type = render_latest()
    return Response(content=body, media_type=content_type)


@router.get(
    "/ready",
    response_model=ReadyStatus,
    responses={503: {"description": "A required dependency is unavailable"}},
)
async def ready(request: Request) -> JSONResponse:
    try:
        await check_database(request.app.state.engine)
    except Exception:
        logger.error("Readiness check failed: database unreachable", exc_info=True)
        database_readiness_failures_total.inc()
        return JSONResponse(
            status_code=503, content=HealthStatus(status="unavailable").model_dump()
        )
    settings = request.app.state.settings
    redis_ok = await check_redis(
        settings.redis_url, timeout_seconds=settings.worker_health_check_timeout_seconds
    )
    degraded = [] if redis_ok else ["redis"]
    if degraded:
        logger.warning("readiness.degraded dependencies=%s", degraded)
        redis_degraded_total.inc()
    return JSONResponse(
        status_code=200,
        content=ReadyStatus(status="ok", degraded_dependencies=degraded).model_dump(),
    )
