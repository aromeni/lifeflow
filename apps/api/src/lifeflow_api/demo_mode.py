"""Demo mode: import the fictional dataset through the synthetic connectors.

Exercises the exact pipeline real connectors will use (interfaces →
normalisation → idempotent ingestion → audit), with no external credentials.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel

from lifeflow_api.audit import record_audit_event
from lifeflow_api.connectors.synthetic import SyntheticCalendarConnector, SyntheticEmailConnector
from lifeflow_api.deps import CurrentUser, DbSession
from lifeflow_api.ingestion import IngestionService
from lifeflow_api.models import ConnectedAccount
from lifeflow_api.repositories import ConnectedAccountRepository

router = APIRouter(prefix="/demo")

SYNTHETIC_PROVIDER = "synthetic"
IMPORT_WINDOW_PAST_DAYS = 14  # assumption BD5: constrained recent window
IMPORT_WINDOW_FUTURE_DAYS = 30  # upcoming calendar horizon


class DemoStartResponse(BaseModel):
    imported: int
    updated: int
    skipped: int


@router.post("/start", response_model=DemoStartResponse)
async def start_demo(user: CurrentUser, session: DbSession) -> DemoStartResponse:
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

    now_local = datetime.now(ZoneInfo(user.timezone))
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
