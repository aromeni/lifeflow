"""Deterministic normalisation of connector DTOs into SourceItem values.

Pure functions: the same DTO always yields byte-identical field values and
the same content fingerprint (canonical JSON, sorted keys, UTC ISO dates).
Anything time-of-import dependent (retention, sync bookkeeping) belongs to
IngestionService, not here.
"""

import hashlib
import json
import uuid
from datetime import UTC
from typing import Any

from lifeflow_api.connectors.interfaces import CalendarEvent, EmailMessage
from lifeflow_api.models import SourceItem, SourceType

_PREVIEW_CHARS = 280


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def email_to_source_item(
    message: EmailMessage, *, user_id: uuid.UUID, account_id: uuid.UUID | None
) -> SourceItem:
    occurred_at = message.sent_at.astimezone(UTC)
    metadata = {
        "folder": str(message.folder),
        "sender_name": message.sender_name,
        "recipients": sorted(message.recipients),
        "thread_id": message.thread_id,
        "body_preview": message.body_text[:_PREVIEW_CHARS],
    }
    return SourceItem(
        user_id=user_id,
        source_type=SourceType.email,
        external_id=message.external_id,
        source_account_id=account_id,
        title=message.subject,
        sender_or_organiser=message.sender_email,
        occurred_at=occurred_at,
        metadata_json=metadata,
        content_fingerprint=_fingerprint(
            {
                "external_id": message.external_id,
                "subject": message.subject,
                "body": message.body_text,
                "sender": message.sender_email,
                "sent_at": occurred_at.isoformat(),
            }
        ),
    )


def event_to_source_item(
    event: CalendarEvent, *, user_id: uuid.UUID, account_id: uuid.UUID | None
) -> SourceItem:
    starts_utc = event.starts_at.astimezone(UTC)
    ends_utc = event.ends_at.astimezone(UTC)
    metadata = {
        "ends_at": ends_utc.isoformat(),
        "all_day": event.all_day,
        "location": event.location,
        "description": event.description[:_PREVIEW_CHARS],
        "attendees": sorted(event.attendees),
    }
    return SourceItem(
        user_id=user_id,
        source_type=SourceType.calendar_event,
        external_id=event.external_id,
        source_account_id=account_id,
        title=event.title,
        sender_or_organiser=event.organiser_email,
        occurred_at=starts_utc,
        metadata_json=metadata,
        content_fingerprint=_fingerprint(
            {
                "external_id": event.external_id,
                "title": event.title,
                "starts_at": starts_utc.isoformat(),
                "ends_at": ends_utc.isoformat(),
                "location": event.location,
                "description": event.description,
            }
        ),
    )
