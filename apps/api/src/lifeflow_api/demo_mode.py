"""Demo mode: import the fictional dataset through the synthetic connectors.

Exercises the exact pipeline real connectors will use (interfaces →
normalisation → idempotent ingestion → audit), with no external credentials.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from pydantic import BaseModel

from lifeflow_api.audit import record_audit_event
from lifeflow_api.config import Settings
from lifeflow_api.connectors.synthetic import SyntheticCalendarConnector, SyntheticEmailConnector
from lifeflow_api.deps import CurrentUser, DbSession
from lifeflow_api.ingestion import IngestionService
from lifeflow_api.models import ConnectedAccount
from lifeflow_api.rate_limit_deps import RateLimited
from lifeflow_api.repositories import ConnectedAccountRepository

router = APIRouter(prefix="/demo")

SYNTHETIC_PROVIDER = "synthetic"
IMPORT_WINDOW_PAST_DAYS = 14  # assumption BD5: constrained recent window
IMPORT_WINDOW_FUTURE_DAYS = 30  # upcoming calendar horizon


class DemoStartResponse(BaseModel):
    imported: int
    updated: int
    skipped: int


def _resolve_now(settings: Settings, timezone: str) -> datetime:
    """The instant the synthetic dataset's fixed day-offsets are materialised
    against. Stage 11A Phase 1 F-002: a Playwright visual-regression run (or
    any other deterministic demo/test execution) can pin this to a fixed
    instant via `demo_clock_override`, gated behind the same
    `e2e_test_controls_enabled` flag `google_api_origin_override` uses, so
    the demo dataset's content stops drifting as real time passes. Nothing
    outside this function ever reads `demo_clock_override` — the real wall
    clock still governs sessions, OAuth, and action-proposal expiry."""
    if settings.e2e_test_controls_enabled and settings.demo_clock_override:
        return datetime.fromisoformat(settings.demo_clock_override).astimezone(ZoneInfo(timezone))
    return datetime.now(ZoneInfo(timezone))


@router.post("/start", response_model=DemoStartResponse, dependencies=[RateLimited("demo_start")])
async def start_demo(request: Request, user: CurrentUser, session: DbSession) -> DemoStartResponse:
    accounts = ConnectedAccountRepository(session, user.id)
    account = await accounts.get_by_provider(SYNTHETIC_PROVIDER)
    if account is None:
        account = ConnectedAccount(
            user_id=user.id, provider=SYNTHETIC_PROVIDER, granted_scopes=["demo"]
        )
        accounts.add(account)
        await session.flush()
        record_audit_event(
            session,
            user_id=user.id,
            actor=f"user:{user.id}",
            event_type="demo.started",
            entity_type="connected_account",
            entity_id=str(account.id),
        )

    now_local = _resolve_now(request.app.state.settings, user.timezone)
    anchor = now_local.date()
    summary = await IngestionService(session, user.id).import_sources(
        email_connector=SyntheticEmailConnector(anchor),
        calendar_connector=SyntheticCalendarConnector(anchor),
        account_id=account.id,
        since=now_local - timedelta(days=IMPORT_WINDOW_PAST_DAYS),
        until=now_local + timedelta(days=IMPORT_WINDOW_FUTURE_DAYS),
    )
    return DemoStartResponse(
        imported=summary.imported, updated=summary.updated, skipped=summary.skipped
    )
