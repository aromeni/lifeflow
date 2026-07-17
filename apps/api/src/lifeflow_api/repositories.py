"""Data access, one repository per entity (naming-conventions.md).

Ownership rule (threat model T2): every repository over user-owned data is
constructed with the owning `user_id` and filters every query by it. There is
no code path that reads another user's rows. `AuditEventRepository` is
append-only by construction — it exposes no update or delete.
"""

import builtins
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.models import (
    ActionExecution,
    ActionProposal,
    AuditEvent,
    Brief,
    ConnectedAccount,
    Preference,
    ProposalStatus,
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

    def add(self, user: User) -> None:
        self._session.add(user)


class ConnectedAccountRepository:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id

    async def get(self, account_id: uuid.UUID) -> ConnectedAccount | None:
        result = await self._session.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.id == account_id,
                ConnectedAccount.user_id == self._user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_provider(self, provider: str) -> ConnectedAccount | None:
        result = await self._session.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.provider == provider,
                ConnectedAccount.user_id == self._user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list(self) -> list[ConnectedAccount]:
        result = await self._session.execute(
            select(ConnectedAccount).where(ConnectedAccount.user_id == self._user_id)
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
