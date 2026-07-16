"""Data access, one repository per entity (naming-conventions.md).

Ownership rule (threat model T2): every repository over user-owned data is
constructed with the owning `user_id` and filters every query by it. There is
no code path that reads another user's rows. `AuditEventRepository` is
append-only by construction — it exposes no update or delete.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.models import (
    AuditEvent,
    ConnectedAccount,
    Preference,
    Signal,
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
        query = select(Signal).where(Signal.user_id == self._user_id)
        if band is not None:
            query = query.where(Signal.priority_band == band)
        query = query.order_by(Signal.priority_score.desc().nulls_last(), Signal.id).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars())

    def add(self, signal: Signal) -> None:
        if signal.user_id != self._user_id:
            raise ValueError("Signal does not belong to this repository's user.")
        self._session.add(signal)


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
