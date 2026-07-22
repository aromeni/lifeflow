"""Data access, one repository per entity (naming-conventions.md).

Ownership rule (threat model T2): every repository over user-owned data is
constructed with the owning `user_id` and filters every query by it. There is
no code path that reads another user's rows. `AuditEventRepository` is
append-only by construction — it exposes no update or delete.
"""

import builtins
import uuid
from datetime import date, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.models import (
    ActionExecution,
    ActionProposal,
    AuditEvent,
    Brief,
    ConnectedAccount,
    MemoryEvidence,
    MemoryItem,
    Preference,
    ProposalStatus,
    ScheduledBriefRun,
    Signal,
    SignalStatus,
    SourceItem,
    User,
)


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_google_subject(self, google_subject: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.google_subject == google_subject)
        )
        return result.scalar_one_or_none()

    def add(self, user: User) -> None:
        self._session.add(user)


class ConnectedAccountRepository:
    """Every read here is consent/authorisation-relevant (status, granted
    scopes, `authorisation_revision`) and therefore always uses
    `populate_existing()` (Stage 7 focused remediation): with this app's
    `expire_on_commit=False` session configuration, an object already in the
    session's identity map — e.g. loaded earlier in the same request by
    `execute()`'s own `accounts.list()` call — would otherwise silently
    survive a commit and hand back stale attribute values even when a fresh
    query (or a real `FOR UPDATE` lock) reads a row a concurrent transaction
    has since changed. Never rely on this repository returning a cached
    copy; every call re-reads the database."""

    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id

    async def get(self, account_id: uuid.UUID) -> ConnectedAccount | None:
        result = await self._session.execute(
            select(ConnectedAccount)
            .where(
                ConnectedAccount.id == account_id,
                ConnectedAccount.user_id == self._user_id,
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_by_provider(
        self, provider: str, *, for_update: bool = False
    ) -> ConnectedAccount | None:
        query = (
            select(ConnectedAccount)
            .where(
                ConnectedAccount.provider == provider,
                ConnectedAccount.user_id == self._user_id,
            )
            .execution_options(populate_existing=True)
        )
        if for_update:
            query = query.with_for_update()
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def list(self) -> list[ConnectedAccount]:
        result = await self._session.execute(
            select(ConnectedAccount)
            .where(ConnectedAccount.user_id == self._user_id)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars())

    def add(self, account: ConnectedAccount) -> None:
        if account.user_id != self._user_id:
            raise ValueError("Account does not belong to this repository's user.")
        self._session.add(account)


class PreferenceRepository:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id

    async def get(self, key: str) -> Preference | None:
        result = await self._session.execute(
            select(Preference).where(Preference.key == key, Preference.user_id == self._user_id)
        )
        return result.scalar_one_or_none()

    async def list(self) -> list[Preference]:
        result = await self._session.execute(
            select(Preference).where(Preference.user_id == self._user_id)
        )
        return list(result.scalars())

    def add(self, preference: Preference) -> None:
        if preference.user_id != self._user_id:
            raise ValueError("Preference does not belong to this repository's user.")
        self._session.add(preference)


class SourceItemRepository:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id

    async def get(self, item_id: uuid.UUID) -> SourceItem | None:
        result = await self._session.execute(
            select(SourceItem).where(SourceItem.id == item_id, SourceItem.user_id == self._user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external(self, source_type: str, external_id: str) -> SourceItem | None:
        result = await self._session.execute(
            select(SourceItem).where(
                SourceItem.source_type == source_type,
                SourceItem.external_id == external_id,
                SourceItem.user_id == self._user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        source_type: str | None = None,
        occurring_after: datetime | None = None,
        occurring_before: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SourceItem]:
        query = select(SourceItem).where(SourceItem.user_id == self._user_id)
        if source_type is not None:
            query = query.where(SourceItem.source_type == source_type)
        if occurring_after is not None:
            query = query.where(SourceItem.occurred_at >= occurring_after)
        if occurring_before is not None:
            query = query.where(SourceItem.occurred_at <= occurring_before)
        query = query.order_by(SourceItem.occurred_at.desc(), SourceItem.id).limit(limit)
        result = await self._session.execute(query.offset(offset))
        return list(result.scalars())

    async def list_by_external_ids(
        self, external_ids: builtins.list[str]
    ) -> builtins.list[SourceItem]:
        """Resolve a proposal's `source_refs` back to their `SourceItem`
        rows — used to determine evidence provenance (Stage 7 remediation
        blocker #1). Owner-scoped like every other query here."""
        if not external_ids:
            return []
        result = await self._session.execute(
            select(SourceItem).where(
                SourceItem.user_id == self._user_id,
                SourceItem.external_id.in_(external_ids),
            )
        )
        return list(result.scalars())

    def add(self, item: SourceItem) -> None:
        if item.user_id != self._user_id:
            raise ValueError("Source item does not belong to this repository's user.")
        self._session.add(item)


class SignalRepository:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id

    async def get_by_dedupe_key(self, dedupe_key: str) -> Signal | None:
        result = await self._session.execute(
            select(Signal).where(Signal.dedupe_key == dedupe_key, Signal.user_id == self._user_id)
        )
        return result.scalar_one_or_none()

    async def list_ranked(self, *, band: str | None = None, limit: int = 100) -> list[Signal]:
        query = select(Signal).where(
            Signal.user_id == self._user_id, Signal.status == SignalStatus.active
        )
        if band is not None:
            query = query.where(Signal.priority_band == band)
        query = query.order_by(Signal.priority_score.desc().nulls_last(), Signal.id).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars())

    def add(self, signal: Signal) -> None:
        if signal.user_id != self._user_id:
            raise ValueError("Signal does not belong to this repository's user.")
        self._session.add(signal)


class BriefRepository:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id

    async def get(self, brief_id: uuid.UUID) -> Brief | None:
        result = await self._session.execute(
            select(Brief).where(Brief.id == brief_id, Brief.user_id == self._user_id)
        )
        return result.scalar_one_or_none()

    async def latest(self) -> Brief | None:
        result = await self._session.execute(
            select(Brief)
            .where(Brief.user_id == self._user_id)
            .order_by(Brief.briefing_date.desc(), Brief.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_recent(self, *, limit: int = 30) -> list[Brief]:
        result = await self._session.execute(
            select(Brief)
            .where(Brief.user_id == self._user_id)
            .order_by(Brief.briefing_date.desc(), Brief.version.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def next_version(self, briefing_date: datetime) -> int:
        result = await self._session.execute(
            select(func.max(Brief.version)).where(
                Brief.user_id == self._user_id, Brief.briefing_date == briefing_date
            )
        )
        return (result.scalar_one_or_none() or 0) + 1

    def add(self, brief: Brief) -> None:
        if brief.user_id != self._user_id:
            raise ValueError("Brief does not belong to this repository's user.")
        self._session.add(brief)


class ScheduledBriefRunRepository:
    """User-scoped like every other repository. The dispatcher's cross-user
    "which users are enabled" query and the worker's "load this run before
    its owning user is known" lookup are NOT here by design — both are
    documented exceptions in `lifeflow_api.scheduled_briefs`, since dispatch
    is inherently a system-wide operation; every read it triggers afterwards
    immediately becomes user-scoped again through this class."""

    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id

    async def get(self, run_id: uuid.UUID) -> ScheduledBriefRun | None:
        result = await self._session.execute(
            select(ScheduledBriefRun).where(
                ScheduledBriefRun.id == run_id, ScheduledBriefRun.user_id == self._user_id
            )
        )
        return result.scalar_one_or_none()

    async def get_for_local_date(self, local_date: date) -> ScheduledBriefRun | None:
        result = await self._session.execute(
            select(ScheduledBriefRun).where(
                ScheduledBriefRun.user_id == self._user_id,
                ScheduledBriefRun.local_brief_date == local_date,
            )
        )
        return result.scalar_one_or_none()

    async def latest(self) -> ScheduledBriefRun | None:
        result = await self._session.execute(
            select(ScheduledBriefRun)
            .where(ScheduledBriefRun.user_id == self._user_id)
            .order_by(ScheduledBriefRun.local_brief_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def add(self, run: ScheduledBriefRun) -> None:
        if run.user_id != self._user_id:
            raise ValueError("Scheduled brief run does not belong to this repository's user.")
        self._session.add(run)


class ActionProposalRepository:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id

    async def get(
        self, proposal_id: uuid.UUID, *, for_update: bool = False
    ) -> ActionProposal | None:
        query = select(ActionProposal).where(
            ActionProposal.id == proposal_id,
            ActionProposal.user_id == self._user_id,
        )
        if for_update:
            query = query.with_for_update()
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_origin(
        self, origin_fingerprint: str, *, for_update: bool = False
    ) -> ActionProposal | None:
        query = select(ActionProposal).where(
            ActionProposal.origin_fingerprint == origin_fingerprint,
            ActionProposal.user_id == self._user_id,
        )
        if for_update:
            query = query.with_for_update()
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self, *, statuses: list[ProposalStatus] | None = None, limit: int = 100
    ) -> list[ActionProposal]:
        query = select(ActionProposal).where(ActionProposal.user_id == self._user_id)
        if statuses:
            query = query.where(ActionProposal.status.in_([str(status) for status in statuses]))
        query = query.order_by(ActionProposal.created_at.desc(), ActionProposal.id).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars())

    async def list_user_edited_by_type(
        self, *, action_type: str, statuses: builtins.list[ProposalStatus], limit: int = 100
    ) -> builtins.list[ActionProposal]:
        """The user's own proposals of one action type that they deliberately
        edited (`user_edited_at` set) and that reached one of `statuses` —
        the evidence source for inferred memory (ADR 0004 D53). Owner-scoped
        like every query here; newest first, bounded."""
        result = await self._session.execute(
            select(ActionProposal)
            .where(
                ActionProposal.user_id == self._user_id,
                ActionProposal.action_type == action_type,
                ActionProposal.user_edited_at.is_not(None),
                ActionProposal.status.in_([str(status) for status in statuses]),
            )
            .order_by(ActionProposal.user_edited_at.desc(), ActionProposal.id)
            .limit(limit)
        )
        return list(result.scalars())

    async def list_due_for_expiry(self, now: datetime) -> builtins.list[ActionProposal]:
        result = await self._session.execute(
            select(ActionProposal)
            .where(
                ActionProposal.user_id == self._user_id,
                ActionProposal.status.in_(
                    [
                        ProposalStatus.proposed,
                        ProposalStatus.edited,
                        ProposalStatus.approved,
                    ]
                ),
                ActionProposal.expires_at <= now,
            )
            .with_for_update()
        )
        return list(result.scalars())

    def add(self, proposal: ActionProposal) -> None:
        if proposal.user_id != self._user_id:
            raise ValueError("Action proposal does not belong to this repository's user.")
        self._session.add(proposal)


class ActionExecutionRepository:
    """Execution ownership is enforced through the proposal join."""

    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id

    async def get_by_proposal(self, proposal_id: uuid.UUID) -> ActionExecution | None:
        result = await self._session.execute(
            select(ActionExecution)
            .join(ActionProposal, ActionProposal.id == ActionExecution.proposal_id)
            .where(
                ActionExecution.proposal_id == proposal_id,
                ActionProposal.user_id == self._user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, idempotency_key: str) -> ActionExecution | None:
        result = await self._session.execute(
            select(ActionExecution)
            .join(ActionProposal, ActionProposal.id == ActionExecution.proposal_id)
            .where(
                ActionExecution.idempotency_key == idempotency_key,
                ActionProposal.user_id == self._user_id,
            )
        )
        return result.scalar_one_or_none()

    def add(self, execution: ActionExecution, *, proposal: ActionProposal) -> None:
        if proposal.user_id != self._user_id or execution.proposal_id != proposal.id:
            raise ValueError("Action execution does not belong to this repository's user.")
        self._session.add(execution)


class MemoryItemRepository:
    """One row per user per closed registry key (ADR 0004 D52/D55). Owner-
    scoped like every repository here; the `(user_id, memory_key)` unique
    constraint is the final guard against two conflicting active memories."""

    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id

    async def get(self, item_id: uuid.UUID, *, for_update: bool = False) -> MemoryItem | None:
        query = select(MemoryItem).where(
            MemoryItem.id == item_id, MemoryItem.user_id == self._user_id
        )
        if for_update:
            query = query.with_for_update()
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_key(self, memory_key: str, *, for_update: bool = False) -> MemoryItem | None:
        query = select(MemoryItem).where(
            MemoryItem.memory_key == memory_key, MemoryItem.user_id == self._user_id
        )
        if for_update:
            query = query.with_for_update()
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self, *, statuses: builtins.list[str] | None = None
    ) -> builtins.list[MemoryItem]:
        query = select(MemoryItem).where(MemoryItem.user_id == self._user_id)
        if statuses is not None:
            query = query.where(MemoryItem.status.in_(statuses))
        query = query.order_by(MemoryItem.updated_at.desc(), MemoryItem.id)
        result = await self._session.execute(query)
        return list(result.scalars())

    def add(self, item: MemoryItem) -> None:
        if item.user_id != self._user_id:
            raise ValueError("Memory item does not belong to this repository's user.")
        self._session.add(item)

    async def delete(self, item: MemoryItem) -> None:
        if item.user_id != self._user_id:
            raise ValueError("Memory item does not belong to this repository's user.")
        # DB-level ON DELETE CASCADE removes the item's evidence rows too.
        await self._session.delete(item)

    async def delete_all(self) -> int:
        """Erase every inferred-memory item (and, by DB cascade, its evidence)
        for this user. Atomic single statement; returns the count removed."""
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                delete(MemoryItem).where(MemoryItem.user_id == self._user_id)
            ),
        )
        return int(result.rowcount or 0)


class MemoryEvidenceRepository:
    """Safe, deduplicated references to the deliberate user actions that
    support an inferred memory (ADR 0004 D53). Owner-scoped; never stores a
    draft body, only a normalised derived value and a reason code."""

    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id

    async def list_for_item(self, memory_item_id: uuid.UUID) -> builtins.list[MemoryEvidence]:
        result = await self._session.execute(
            select(MemoryEvidence)
            .where(
                MemoryEvidence.memory_item_id == memory_item_id,
                MemoryEvidence.user_id == self._user_id,
            )
            .order_by(MemoryEvidence.observed_at, MemoryEvidence.id)
        )
        return list(result.scalars())

    async def existing_proposal_ids(self, memory_item_id: uuid.UUID) -> set[uuid.UUID]:
        """The proposal ids already recorded as evidence for this item — used
        to make recompute idempotent (never double-count a proposal)."""
        result = await self._session.execute(
            select(MemoryEvidence.source_proposal_id).where(
                MemoryEvidence.memory_item_id == memory_item_id,
                MemoryEvidence.user_id == self._user_id,
                MemoryEvidence.source_proposal_id.is_not(None),
            )
        )
        return {pid for (pid,) in result.all() if pid is not None}

    def add(self, evidence: MemoryEvidence) -> None:
        if evidence.user_id != self._user_id:
            raise ValueError("Memory evidence does not belong to this repository's user.")
        self._session.add(evidence)


class AuditEventRepository:
    """Append-only: intentionally no update or delete methods (T18)."""

    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id

    def append(self, event: AuditEvent) -> None:
        if event.user_id != self._user_id:
            raise ValueError("Audit event does not belong to this repository's user.")
        self._session.add(event)

    async def list(self, limit: int = 100) -> list[AuditEvent]:
        result = await self._session.execute(
            select(AuditEvent)
            .where(AuditEvent.user_id == self._user_id)
            .order_by(AuditEvent.timestamp.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def list_for_entity(
        self, *, entity_type: str, entity_id: str, limit: int = 100
    ) -> builtins.list[AuditEvent]:
        result = await self._session.execute(
            select(AuditEvent)
            .where(
                AuditEvent.user_id == self._user_id,
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == entity_id,
            )
            .order_by(AuditEvent.timestamp, AuditEvent.id)
            .limit(limit)
        )
        return list(result.scalars())
