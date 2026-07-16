"""Core domain entities (skill §7, ADR 0001).

Conventions (docs/architecture/naming-conventions.md):
- entity classes are singular nouns; tables are snake_case plurals;
- enum values are Python StrEnums stored as strings (validated at the
  Pydantic boundary; portable migrations);
- every user-owned table carries `user_id` — ownership is enforced in every
  repository query (threat model T2);
- timestamps are timezone-aware and stored in UTC.

Safety by construction: `ActionType` and `RiskLevel` are closed enums.
Sending email, deleting events, and purchases are not representable.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from lifeflow_api.db import Base


class OnboardingState(StrEnum):
    new = "new"
    in_progress = "in_progress"
    complete = "complete"


class AccountStatus(StrEnum):
    active = "active"
    expired = "expired"
    revoked = "revoked"
    disconnected = "disconnected"


class SourceType(StrEnum):
    email = "email"
    calendar_event = "calendar_event"
    internal_task = "internal_task"


class SignalStatus(StrEnum):
    active = "active"
    dismissed = "dismissed"


class SignalType(StrEnum):
    request = "request"
    commitment = "commitment"
    deadline = "deadline"
    meeting = "meeting"
    follow_up = "follow_up"
    conflict = "conflict"


class ActionType(StrEnum):
    """Closed set of proposable actions. High-risk actions (send email,
    delete event, purchase) are prohibited in the MVP and intentionally
    absent — they cannot be proposed, approved, or executed."""

    create_task = "create_task"
    create_gmail_draft = "create_gmail_draft"
    create_calendar_event = "create_calendar_event"


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    # "high" intentionally absent: prohibited in the MVP.


class ProposalStatus(StrEnum):
    proposed = "proposed"
    edited = "edited"
    approved = "approved"
    rejected = "rejected"
    executing = "executing"
    executed = "executed"
    failed = "failed"
    expired = "expired"


class Provenance(StrEnum):
    explicit = "explicit"
    inferred = "inferred"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/London")
    locale: Mapped[str] = mapped_column(String(16), default="en-GB")
    onboarding_state: Mapped[str] = mapped_column(String(20), default=OnboardingState.new)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConnectedAccount(Base):
    __tablename__ = "connected_accounts"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    provider: Mapped[str] = mapped_column(String(40))
    # Ciphertext envelopes from TokenCipher — never plaintext (threat model T1).
    encrypted_access_token: Mapped[str | None] = mapped_column(Text)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text)
    granted_scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default=AccountStatus.active)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceItem(Base):
    __tablename__ = "source_items"
    __table_args__ = (
        # Re-importing the same external item must not duplicate it.
        UniqueConstraint("user_id", "source_type", "external_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    source_type: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(512))
    source_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connected_accounts.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text)
    sender_or_organiser: Mapped[str | None] = mapped_column(String(320))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    retention_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_signals_user_dedupe"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    signal_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float)
    urgency: Mapped[float] = mapped_column(Float)
    importance: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default=SignalStatus.active)
    extraction_version: Mapped[str] = mapped_column(String(40))
    # Priority engine outputs (skill §8): explainable score with reason codes.
    priority_score: Mapped[float | None] = mapped_column(Float)
    priority_band: Mapped[str | None] = mapped_column(String(10))
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    # sha256(signal_type | sorted evidence) — re-extraction upserts, never duplicates.
    dedupe_key: Mapped[str] = mapped_column(String(64))


class Brief(Base):
    __tablename__ = "briefs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    briefing_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    summary: Mapped[str] = mapped_column(Text)
    sections_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_window: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    model_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ActionProposal(Base):
    __tablename__ = "action_proposals"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    action_type: Mapped[str] = mapped_column(String(40))
    rationale: Mapped[str] = mapped_column(Text)
    source_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    risk_level: Mapped[str] = mapped_column(String(10))
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default=ProposalStatus.proposed)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActionExecution(Base):
    __tablename__ = "action_executions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("action_proposals.id", ondelete="CASCADE"), index=True
    )
    # Duplicate execution attempts collide here instead of acting twice
    # (threat model T12).
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64))


class Preference(Base):
    __tablename__ = "preferences"
    __table_args__ = (UniqueConstraint("user_id", "key"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    key: Mapped[str] = mapped_column(String(100))
    value_json: Mapped[Any] = mapped_column(JSON)
    provenance: Mapped[str] = mapped_column(String(10), default=Provenance.explicit)
    confidence: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditEvent(Base):
    """Append-only. The repository exposes no update or delete operations;
    metadata is validated against secret-shaped keys before writing
    (threat model T18)."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_user_time", "user_id", "timestamp"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    actor: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    safe_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(128))
