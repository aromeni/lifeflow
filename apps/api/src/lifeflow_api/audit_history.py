"""Privacy-safe, owner-scoped audit-history read projection (ADR 0005).

The append-only audit log is an internal safety record, not a presentation
model. This module is the public API: it authenticates, applies the closed
presentation registry (`audit_history_registry`) as an allowlist, and
paginates. Raw actors, entity identifiers, correlation identifiers, and
metadata never cross the API boundary.
"""

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from lifeflow_api.audit_history_registry import (
    AUDIT_EVENT_PRESENTATIONS,
    AuditHistoryCategory,
    AuditHistoryTone,
    safe_action_type_label,
    safe_counts,
    safe_reason_label,
)
from lifeflow_api.deps import CurrentUser, DbSession
from lifeflow_api.models import AuditEvent
from lifeflow_api.rate_limit_deps import RateLimited
from lifeflow_api.repositories import AuditEventRepository

router = APIRouter(prefix="/audit-history")


class AuditHistoryPeriod(StrEnum):
    seven_days = "7d"
    thirty_days = "30d"
    ninety_days = "90d"
    all = "all"


class AuditHistoryActor(StrEnum):
    you = "you"
    lifeflow = "lifeflow"


class AuditHistoryItem(BaseModel):
    id: str
    occurred_at: datetime
    category: AuditHistoryCategory
    actor: AuditHistoryActor
    title: str
    summary: str
    tone: AuditHistoryTone
    # All closed, pre-validated safe values — never the raw metadata — and
    # None/absent whenever the event type doesn't declare the detail, the
    # source key is missing, or the value fails validation (fail closed).
    action_type: str | None = None
    reason: str | None = None
    deleted_count: int | None = None
    preserved_count: int | None = None
    failed_count: int | None = None


class AuditHistoryResponse(BaseModel):
    items: list[AuditHistoryItem]
    next_cursor: str | None


@dataclass(frozen=True)
class Cursor:
    as_of: datetime
    before_timestamp: datetime
    before_id: uuid.UUID


_CURSOR_KEYS = {"v", "as_of", "before_timestamp", "before_id", "category", "period"}
_PERIOD_DAYS: dict[AuditHistoryPeriod, int] = {
    AuditHistoryPeriod.seven_days: 7,
    AuditHistoryPeriod.thirty_days: 30,
    AuditHistoryPeriod.ninety_days: 90,
}


def _encode_cursor(
    *,
    as_of: datetime,
    last_event: AuditEvent,
    category: AuditHistoryCategory,
    period: AuditHistoryPeriod,
) -> str:
    payload = {
        "v": 1,
        "as_of": as_of.isoformat(),
        "before_timestamp": last_event.timestamp.isoformat(),
        "before_id": str(last_event.id),
        "category": category.value,
        "period": period.value,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    )
    return encoded.decode().rstrip("=")


def _aware_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError
    return parsed.astimezone(UTC)


def _decode_cursor(
    value: str,
    *,
    category: AuditHistoryCategory,
    period: AuditHistoryPeriod,
) -> Cursor:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True))
        if not isinstance(payload, dict) or set(payload) != _CURSOR_KEYS:
            raise ValueError
        if (
            type(payload["v"]) is not int
            or payload["v"] != 1
            or payload["category"] != category.value
            or payload["period"] != period.value
        ):
            raise ValueError
        as_of = _aware_datetime(payload["as_of"])
        before_timestamp = _aware_datetime(payload["before_timestamp"])
        before_id = uuid.UUID(payload["before_id"])
        if before_timestamp > as_of:
            raise ValueError
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="Invalid audit-history cursor.") from None
    return Cursor(
        as_of=as_of,
        before_timestamp=before_timestamp,
        before_id=before_id,
    )


def _actor_label(actor: str) -> AuditHistoryActor:
    return AuditHistoryActor.you if actor.startswith("user:") else AuditHistoryActor.lifeflow


def _render(event: AuditEvent) -> AuditHistoryItem:
    presentation = AUDIT_EVENT_PRESENTATIONS[event.event_type]
    metadata = event.safe_metadata_json or {}
    action_type = (
        safe_action_type_label(metadata.get("action_type"))
        if presentation.show_action_type
        else None
    )
    # Writers use either key depending on the failure's origin (policy
    # rejection vs. execution/deletion error); the two never co-occur on the
    # same event, and both are validated against the same closed label set.
    reason = (
        safe_reason_label(metadata.get("reason_code") or metadata.get("error_code"))
        if presentation.show_reason
        else None
    )
    counts = safe_counts(metadata) if presentation.show_counts else {}
    return AuditHistoryItem(
        id=str(event.id),
        occurred_at=event.timestamp,
        category=presentation.category,
        actor=_actor_label(event.actor),
        title=presentation.title,
        summary=presentation.summary,
        tone=presentation.tone,
        action_type=action_type,
        reason=reason,
        deleted_count=counts.get("deleted_count"),
        preserved_count=counts.get("preserved_count"),
        failed_count=counts.get("failed_count"),
    )


@router.get(
    "", response_model=AuditHistoryResponse, dependencies=[RateLimited("privacy_audit_read")]
)
async def list_audit_history(
    user: CurrentUser,
    session: DbSession,
    category: AuditHistoryCategory = AuditHistoryCategory.all,
    period: AuditHistoryPeriod = AuditHistoryPeriod.seven_days,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, min_length=1, max_length=1_024),
) -> AuditHistoryResponse:
    """Return a read-only, privacy-reviewed projection of the owner's log."""
    decoded = (
        _decode_cursor(cursor, category=category, period=period) if cursor is not None else None
    )
    as_of = decoded.as_of if decoded is not None else datetime.now(UTC)
    not_before = (
        as_of - timedelta(days=_PERIOD_DAYS[period])
        if period is not AuditHistoryPeriod.all
        else None
    )
    event_types = {
        event_type
        for event_type, presentation in AUDIT_EVENT_PRESENTATIONS.items()
        if category is AuditHistoryCategory.all or presentation.category is category
    }
    rows = await AuditEventRepository(session, user.id).list_history_page(
        event_types=event_types,
        not_before=not_before,
        not_after=as_of,
        before=((decoded.before_timestamp, decoded.before_id) if decoded is not None else None),
        limit=limit + 1,
    )
    page = rows[:limit]
    return AuditHistoryResponse(
        items=[_render(event) for event in page],
        next_cursor=(
            _encode_cursor(
                as_of=as_of,
                last_event=page[-1],
                category=category,
                period=period,
            )
            if len(rows) > limit
            else None
        ),
    )
