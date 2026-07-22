"""Privacy & Connections Control Centre — the consolidated, read-only privacy
surface (Stage 9 Delivery Phase 1, ADR 0005).

This is a truthful projection over data the user already owns: which provider
accounts are connected and with exactly which granted scopes, how fresh the
synced evidence is, owner-scoped counts of every stored category, and the
provisional retention defaults. It is strictly non-destructive — it adds no
deletion, no account-deletion, no retention *enforcement* (Delivery Phase 2),
no audit timeline (Delivery Phase 3), and no rate limiting (Delivery Phase 4).

Safety by construction: the response carries no OAuth token or ciphertext, no
sync cursor, no `authorisation_revision`, no provider message/event id, no
proposal payload/hash, and no audit `safe_metadata` internals — only counts,
statuses, scope labels, and freshness bands. Depends only on PostgreSQL, never
Redis, so it stays fully available when the scheduler/queue is down.

The inventory intentionally issues owner-scoped `func.count()` queries across
several entity tables from one place: an inventory is inherently a cross-entity
projection (like the documented cross-cutting reads in `scheduled_briefs`).
Every query filters by `user_id`; there is no code path that counts another
user's rows (threat model T2).
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.config import Settings
from lifeflow_api.deps import CurrentUser, DbSession
from lifeflow_api.evidence_freshness import FreshnessBand, _freshness_band
from lifeflow_api.google_scopes import (
    CALENDAR_EVENTS_SCOPE,
    CALENDAR_READONLY_SCOPE,
    GMAIL_COMPOSE_SCOPE,
    GMAIL_READONLY_SCOPE,
)
from lifeflow_api.models import (
    AccountStatus,
    ActionExecution,
    ActionProposal,
    AuditEvent,
    Brief,
    ConnectedAccount,
    MemoryEvidence,
    MemoryItem,
    Preference,
    ScheduledBriefRun,
    Signal,
    SourceItem,
)

router = APIRouter(prefix="/privacy")

# Human-facing labels for the exact scopes the product can hold. Sign-in
# identity scopes (openid/email/profile) are handled by their own OIDC client
# and are not stored on `connected_accounts`, but are mapped here so a truthful
# label exists if one is ever encountered. Any unrecognised scope renders as a
# neutral "Other access" — never as broader access than was granted.
_SCOPE_LABELS: dict[str, str] = {
    GMAIL_READONLY_SCOPE: "View Gmail evidence",
    GMAIL_COMPOSE_SCOPE: "Create Gmail drafts",
    CALENDAR_READONLY_SCOPE: "View Calendar evidence",
    CALENDAR_EVENTS_SCOPE: "Create Calendar events",
    "openid": "Basic sign-in identity",
    "email": "Basic sign-in identity",
    "profile": "Basic sign-in identity",
}


def scope_label(scope: str) -> str:
    return _SCOPE_LABELS.get(scope, "Other access")


class GrantedScopeView(BaseModel):
    scope: str
    label: str


class ConnectionSummaryView(BaseModel):
    account_id: str
    provider: str
    status: str
    connected: bool
    granted_scopes: list[GrantedScopeView]
    last_synced_at: datetime | None
    freshness_band: FreshnessBand | None
    ever_synced: bool
    can_disconnect: bool
    can_reconnect: bool


class InventoryView(BaseModel):
    """Owner-scoped counts only — never any stored content."""

    connected_accounts: int
    source_items: int
    signals: int
    briefs: int
    brief_versions: int
    action_proposals: int
    action_executions: int
    scheduled_brief_runs: int
    preferences: int
    memory_items: int
    memory_evidence: int
    audit_events: int


class RetentionClassView(BaseModel):
    key: str
    label: str
    description: str
    # None means "no fixed horizon" (e.g. Signals follow their source's
    # lifecycle; pending/uncertain executions are never auto-deleted).
    retention_days: int | None
    enforced: bool  # always False in Delivery Phase 1 — enforcement is Phase 2.


class RetentionView(BaseModel):
    enforcement_active: bool
    classes: list[RetentionClassView]
    notes: list[str]


class PrivacySummaryResponse(BaseModel):
    connections: list[ConnectionSummaryView]
    inventory: InventoryView
    retention: RetentionView


def _connection_view(account: ConnectedAccount, *, now: datetime) -> ConnectionSummaryView:
    connected = account.status == AccountStatus.active
    return ConnectionSummaryView(
        account_id=str(account.id),
        provider=account.provider,
        status=account.status,
        connected=connected,
        granted_scopes=[
            GrantedScopeView(scope=scope, label=scope_label(scope))
            for scope in account.granted_scopes
        ],
        last_synced_at=account.last_sync_at,
        freshness_band=(
            _freshness_band(account.last_sync_at, now=now)
            if account.last_sync_at is not None
            else None
        ),
        ever_synced=account.last_sync_at is not None,
        can_disconnect=connected,
        # Reconnect is always offered for a provider that supports OAuth; it
        # re-runs consent and (per ADR 0003) advances the authorisation
        # revision, so it is safe even from a disconnected/revoked state.
        can_reconnect=account.provider == "google",
    )


async def _count(session: AsyncSession, stmt: Select[tuple[int]]) -> int:
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def build_inventory(session: AsyncSession, user_id: uuid.UUID) -> InventoryView:
    """Every count is owner-scoped by `user_id`. Executions carry no `user_id`
    of their own; ownership is enforced through the join to the owning
    proposal, exactly as `ActionExecutionRepository` does."""
    return InventoryView(
        connected_accounts=await _count(
            session,
            select(func.count())
            .select_from(ConnectedAccount)
            .where(ConnectedAccount.user_id == user_id),
        ),
        source_items=await _count(
            session,
            select(func.count()).select_from(SourceItem).where(SourceItem.user_id == user_id),
        ),
        signals=await _count(
            session, select(func.count()).select_from(Signal).where(Signal.user_id == user_id)
        ),
        briefs=await _count(
            session,
            select(func.count(func.distinct(Brief.briefing_date))).where(Brief.user_id == user_id),
        ),
        brief_versions=await _count(
            session, select(func.count()).select_from(Brief).where(Brief.user_id == user_id)
        ),
        action_proposals=await _count(
            session,
            select(func.count())
            .select_from(ActionProposal)
            .where(ActionProposal.user_id == user_id),
        ),
        action_executions=await _count(
            session,
            select(func.count())
            .select_from(ActionExecution)
            .join(ActionProposal, ActionProposal.id == ActionExecution.proposal_id)
            .where(ActionProposal.user_id == user_id),
        ),
        scheduled_brief_runs=await _count(
            session,
            select(func.count())
            .select_from(ScheduledBriefRun)
            .where(ScheduledBriefRun.user_id == user_id),
        ),
        preferences=await _count(
            session,
            select(func.count()).select_from(Preference).where(Preference.user_id == user_id),
        ),
        memory_items=await _count(
            session,
            select(func.count()).select_from(MemoryItem).where(MemoryItem.user_id == user_id),
        ),
        memory_evidence=await _count(
            session,
            select(func.count())
            .select_from(MemoryEvidence)
            .where(MemoryEvidence.user_id == user_id),
        ),
        audit_events=await _count(
            session,
            select(func.count()).select_from(AuditEvent).where(AuditEvent.user_id == user_id),
        ),
    )


def build_retention(settings: Settings) -> RetentionView:
    """The provisional product retention defaults (ADR 0005). Read-only and
    NOT enforced in Delivery Phase 1 — `enforced` is always False and the
    notes say so plainly, so the UI can never imply enforcement exists yet."""
    classes = [
        RetentionClassView(
            key="source_items",
            label="Imported emails & events",
            description="Normalised references LifeFlow imported from Gmail and Calendar.",
            retention_days=settings.retention_source_items_days,
            enforced=False,
        ),
        RetentionClassView(
            key="signals",
            label="Detected signals",
            description="Kept for as long as the source item they were derived from is kept.",
            retention_days=None,
            enforced=False,
        ),
        RetentionClassView(
            key="brief_versions",
            label="Daily brief versions",
            description="Every regenerated version of a daily brief.",
            retention_days=settings.retention_brief_versions_days,
            enforced=False,
        ),
        RetentionClassView(
            key="unapproved_proposals",
            label="Rejected, expired & unapproved proposals",
            description="Proposed actions you never approved.",
            retention_days=settings.retention_unapproved_proposals_days,
            enforced=False,
        ),
        RetentionClassView(
            key="approved_terminal",
            label="Approved actions & completed executions",
            description="A minimised history of what you approved and what was carried out.",
            retention_days=settings.retention_approved_terminal_days,
            enforced=False,
        ),
        RetentionClassView(
            key="pending_uncertain_executions",
            label="Unresolved external outcomes",
            description=(
                "Executions still pending or with an uncertain result are never "
                "automatically deleted before they are reconciled."
            ),
            retention_days=None,
            enforced=False,
        ),
        RetentionClassView(
            key="scheduled_brief_runs",
            label="Scheduled brief history",
            description="Records of scheduled daily-brief attempts.",
            retention_days=settings.retention_scheduled_runs_days,
            enforced=False,
        ),
        RetentionClassView(
            key="memory_evidence",
            label="Expired or dismissed learned-preference evidence",
            description="Safe derived tokens behind inferred memory you did not confirm.",
            retention_days=settings.retention_memory_evidence_days,
            enforced=False,
        ),
        RetentionClassView(
            key="audit_tombstones",
            label="Audit records",
            description="Content-free records of what LifeFlow observed, proposed and executed.",
            retention_days=settings.retention_audit_tombstone_days,
            enforced=False,
        ),
        RetentionClassView(
            key="operational_logs",
            label="Operational logs",
            description="Diagnostic logs that never contain your message content.",
            retention_days=settings.retention_operational_logs_days,
            enforced=False,
        ),
        RetentionClassView(
            key="aggregated_metrics",
            label="Aggregated metrics",
            description="Non-personal, aggregate health metrics.",
            retention_days=settings.retention_aggregated_metrics_days,
            enforced=False,
        ),
    ]
    return RetentionView(
        enforcement_active=False,
        classes=classes,
        notes=[
            "These are provisional product defaults for the pilot, not legal mandates.",
            "Automatic deletion enforcement arrives in a later phase; nothing is auto-deleted yet.",
            "Executions that are pending or uncertain are preserved for reconciliation.",
            "Confirmed explicit preferences do not expire when inferred-memory evidence ages.",
        ],
    )


@router.get("/summary", response_model=PrivacySummaryResponse)
async def get_privacy_summary(
    request: Request, user: CurrentUser, session: DbSession
) -> PrivacySummaryResponse:
    now = datetime.now(UTC)
    accounts = await session.execute(
        select(ConnectedAccount)
        .where(ConnectedAccount.user_id == user.id)
        .order_by(ConnectedAccount.provider)
        .execution_options(populate_existing=True)
    )
    connections = [_connection_view(account, now=now) for account in accounts.scalars()]
    inventory = await build_inventory(session, user.id)
    # Read the app's own settings (never the cached module global) so a
    # deployment's configured retention horizons are reflected truthfully.
    settings: Settings = request.app.state.settings
    retention = build_retention(settings)
    return PrivacySummaryResponse(connections=connections, inventory=inventory, retention=retention)


__all__ = [
    "PrivacySummaryResponse",
    "build_inventory",
    "build_retention",
    "router",
    "scope_label",
]
