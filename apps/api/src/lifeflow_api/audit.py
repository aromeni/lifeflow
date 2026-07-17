"""Audit trail service.

Every state change of interest is recorded as an append-only AuditEvent with
the current correlation ID. Metadata is validated before writing: keys that
look like secrets are rejected outright (threat model T18) — the caller must
fix the call site, not rely on redaction.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.correlation import get_correlation_id
from lifeflow_api.models import AuditEvent
from lifeflow_api.repositories import AuditEventRepository

_FORBIDDEN_KEY_FRAGMENTS = ("token", "secret", "password", "authorization", "cookie")


class UnsafeAuditMetadataError(ValueError):
    """Raised when audit metadata contains secret-shaped keys."""


def _validate_metadata(metadata: dict[str, Any]) -> None:
    for key in metadata:
        lowered = key.lower()
        if any(fragment in lowered for fragment in _FORBIDDEN_KEY_FRAGMENTS):
            raise UnsafeAuditMetadataError(
                f"Audit metadata key '{key}' looks like a secret and is not allowed."
            )


def record_audit_event(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    actor: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append an audit event to the current transaction."""
    metadata = metadata or {}
    _validate_metadata(metadata)
    event = AuditEvent(
        user_id=user_id,
        actor=actor,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        timestamp=datetime.now(UTC),
        safe_metadata_json=metadata,
        correlation_id=get_correlation_id(),
    )
    AuditEventRepository(session, user_id).append(event)
    return event
