"""IngestionService: pull authorised data through connector interfaces,
normalise it, and store it idempotently.

Idempotency: re-importing the same external item never duplicates it — items
are matched on (user, source_type, external_id); unchanged fingerprints are
skipped, changed ones update in place. A failed connector must not erase
prior data: imports only ever add or update, never delete.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.audit import record_audit_event
from lifeflow_api.connectors.interfaces import CalendarConnector, EmailConnector
from lifeflow_api.models import SourceItem
from lifeflow_api.normalisation import email_to_source_item, event_to_source_item
from lifeflow_api.repositories import ConnectedAccountRepository, SourceItemRepository

RETENTION_DAYS = 30  # assumption A6; retention jobs enforce this at Stage 9


@dataclass
class ImportSummary:
    imported: int = 0
    updated: int = 0
    skipped: int = 0

    def merge(self, other: "ImportSummary") -> "ImportSummary":
        return ImportSummary(
            imported=self.imported + other.imported,
            updated=self.updated + other.updated,
            skipped=self.skipped + other.skipped,
        )


class IngestionService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id
        self._items = SourceItemRepository(session, user_id)

    async def _upsert(self, candidate: SourceItem, sync_time: datetime) -> str:
        candidate.retention_expires_at = sync_time + timedelta(days=RETENTION_DAYS)
        existing = await self._items.get_by_external(candidate.source_type, candidate.external_id)
        if existing is None:
            self._items.add(candidate)
            return "imported"
        if existing.content_fingerprint == candidate.content_fingerprint:
            existing.retention_expires_at = candidate.retention_expires_at
            return "skipped"
        existing.title = candidate.title
        existing.sender_or_organiser = candidate.sender_or_organiser
        existing.occurred_at = candidate.occurred_at
        existing.metadata_json = candidate.metadata_json
        existing.content_fingerprint = candidate.content_fingerprint
        existing.retention_expires_at = candidate.retention_expires_at
        return "updated"

    async def import_sources(
        self,
        *,
        email_connector: EmailConnector,
        calendar_connector: CalendarConnector,
        account_id: uuid.UUID | None,
        since: datetime,
        until: datetime,
    ) -> ImportSummary:
        sync_time = datetime.now(UTC)
        summary = ImportSummary()

        for message in await email_connector.fetch_recent(since=since, until=until):
            item = email_to_source_item(message, user_id=self._user_id, account_id=account_id)
            outcome = await self._upsert(item, sync_time)
            setattr(summary, outcome, getattr(summary, outcome) + 1)

        for event in await calendar_connector.fetch_events(since=since, until=until):
            item = event_to_source_item(event, user_id=self._user_id, account_id=account_id)
            outcome = await self._upsert(item, sync_time)
            setattr(summary, outcome, getattr(summary, outcome) + 1)

        if account_id is not None:
            account = await ConnectedAccountRepository(self._session, self._user_id).get(account_id)
            if account is not None:
                account.last_sync_at = sync_time

        await self._session.flush()
        record_audit_event(
            self._session,
            user_id=self._user_id,
            actor=f"user:{self._user_id}",
            event_type="sync.completed",
            entity_type="source_item",
            entity_id=str(account_id) if account_id else "-",
            metadata={
                "imported": summary.imported,
                "updated": summary.updated,
                "skipped": summary.skipped,
            },
        )
        await self._session.flush()
        return summary
