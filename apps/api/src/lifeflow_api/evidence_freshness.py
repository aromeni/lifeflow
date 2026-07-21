"""Read-only evidence-freshness surface (Stage 8 Phase 2 focused remediation).

Scheduled briefs deliberately never trigger Google sync (ADR 0004 D47) — a
scheduled brief only ever uses whatever `SourceItem`s a previous, manual sync
already produced. This module exists so Settings/Today can say that
truthfully: per connected account, whether it is connected, whether it has
ever been synced, and how old that evidence is — without exposing OAuth
internals, sync cursors, or any provider identifier beyond a plain provider
name. Depends only on Postgres (`ConnectedAccount`), never Redis, so it stays
available even when the scheduler is not (see `scheduled_brief_status.py` for
that separate, Redis-dependent concern).
"""

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from lifeflow_api.deps import CurrentUser, DbSession
from lifeflow_api.models import AccountStatus
from lifeflow_api.repositories import ConnectedAccountRepository

router = APIRouter(prefix="/evidence-freshness")

# Age bands for display only — not a policy input (nothing reads these to
# decide whether to generate a brief; that's governed entirely by D47/D49).
FRESH_WITHIN = timedelta(hours=24)
AGING_WITHIN = timedelta(days=7)

FreshnessBand = Literal["fresh", "aging", "stale"]
SyncState = Literal["never_synced", "synced"]


class EvidenceFreshnessAccount(BaseModel):
    provider: str
    connected: bool
    sync_state: SyncState
    last_synced_at: datetime | None
    freshness_band: FreshnessBand | None


class EvidenceFreshnessResponse(BaseModel):
    accounts: list[EvidenceFreshnessAccount]
    scheduled_briefs_use_latest_synced_evidence: bool


def _freshness_band(last_synced_at: datetime, *, now: datetime) -> FreshnessBand:
    age = now - last_synced_at
    if age <= FRESH_WITHIN:
        return "fresh"
    if age <= AGING_WITHIN:
        return "aging"
    return "stale"


@router.get("", response_model=EvidenceFreshnessResponse)
async def get_evidence_freshness(
    user: CurrentUser, session: DbSession
) -> EvidenceFreshnessResponse:
    accounts = await ConnectedAccountRepository(session, user.id).list()
    now = datetime.now(UTC)

    views = [
        EvidenceFreshnessAccount(
            provider=account.provider,
            connected=account.status == AccountStatus.active,
            sync_state="synced" if account.last_sync_at is not None else "never_synced",
            last_synced_at=account.last_sync_at,
            freshness_band=(
                _freshness_band(account.last_sync_at, now=now)
                if account.last_sync_at is not None
                else None
            ),
        )
        for account in accounts
    ]
    return EvidenceFreshnessResponse(
        accounts=views,
        # Always true today (ADR 0004 D47): stated explicitly here, not just
        # in prose, so the frontend never has to assume it.
        scheduled_briefs_use_latest_synced_evidence=True,
    )


__all__ = ["EvidenceFreshnessAccount", "EvidenceFreshnessResponse", "router"]
