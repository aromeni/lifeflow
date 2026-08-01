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
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
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
    # An explicit, evidenced ask to put something on the calendar (ADR 0003
    # D39) — distinct from `request` (generic, answered with a reply draft)
    # and from `meeting` (an event that already exists on a calendar).
    schedule_request = "schedule_request"
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


class ExecutionOutcome(StrEnum):
    """Stage 7 (ADR 0003 D16): the true state of an external attempt.

    pending — the attempt is durably recorded but the executor call has not
    yet resolved (or the process died before it could). A `pending` row
    older than the staleness threshold is treated as `uncertain`, never left
    ambiguous forever and never silently retried.
    uncertain — the executor call could not be confirmed to have succeeded
    or failed (timeout, connection error, 5xx, or an unverifiable echoed
    resource). This is a distinct, honest terminal-for-now state — not a
    failure and not a success. `ProposalStatus` stays `executing` while an
    execution is `pending` or `uncertain`; the API derives an
    `effective_status` from this column instead.
    """

    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    uncertain = "uncertain"


class ExecutionMode(StrEnum):
    """Which path would/did carry out an approved action (Stage 7
    remediation, independent-review blocker #2/#3). Resolved deterministically
    from the user's currently active connected accounts — never chosen
    reactively after a real call fails, and never a static default.

    simulation — the demo/synthetic path (or, for `create_task`, the
    always-local Stage 6 behaviour).
    real — a Google-connected account with the exact required scope.
    unavailable — neither path exists yet (e.g. nothing connected); the
    policy engine denies approval/execution in this state, so `unavailable`
    is never persisted on an `ActionExecution` row, only shown on a proposal
    preview.
    """

    simulation = "simulation"
    real = "real"
    unavailable = "unavailable"


class Provenance(StrEnum):
    explicit = "explicit"
    inferred = "inferred"


class MemoryStatus(StrEnum):
    """Closed lifecycle for one inferred-memory item (ADR 0004 D55).

    candidate — inferred from evidence, awaiting the user's review. Never
    applied to any outgoing content: inferred memory is suggest-only, so a
    candidate influences nothing until the user confirms it.
    confirmed — the user accepted it; the corresponding explicit preference
    was written and now carries normal explicit authority. The item stays as
    a visible record of what was learned.
    dismissed — the user rejected it; sticky via an evidence fingerprint so
    the same evidence never re-surfaces it (only materially new evidence can).
    superseded — an explicit preference now overrides it, or newer contrary
    evidence replaced its value. Visible but inactive.
    expired — its evidence decayed past the freshness floor with no
    confirmation. Confirmed explicit preferences never decay.
    """

    candidate = "candidate"
    confirmed = "confirmed"
    dismissed = "dismissed"
    superseded = "superseded"
    expired = "expired"


class UserAccountState(StrEnum):
    """Closed lifecycle for a LifeFlow account (Stage 9 Delivery Phase 2,
    ADR 0005 D61).

    active — an ordinary usable account.
    deletion_pending — account deletion was confirmed; the durable operation
    is queued or running. New sync, proposal creation, approval, and
    execution are all blocked, but the account is not yet anonymised (the
    worker has not finished).
    deleted — terminal, anonymised. Direct identity fields are cleared, a
    random non-reversible `deletion_subject_id` replaces the identity, and
    the row can never authenticate again. The same Google identity may create
    a genuinely new account later without reviving this one.
    """

    active = "active"
    deletion_pending = "deletion_pending"
    deleted = "deleted"


class DeletionOperationType(StrEnum):
    """Closed set of destructive operations the shared deletion engine runs
    (ADR 0005 D61-D63). No free-form type is representable."""

    imported_data = "imported_data"
    retention = "retention"
    account_deletion = "account_deletion"


class DeletionRequesterType(StrEnum):
    user = "user"
    system = "system"


class DeletionOperationState(StrEnum):
    """Closed lifecycle for one durable deletion operation (ADR 0005).

    previewed — a durable, owner-scoped preview exists with captured counts
    and a snapshot cutoff, awaiting typed confirmation. Nothing destructive
    has happened. Cancellable.
    pending — confirmed and durably recorded; queued for the worker (or
    awaiting a queue that is temporarily down). No destructive batch has
    committed. Cancellable.
    running — the worker has claimed it and at least started; once any
    destructive batch commits, cancellation is refused.
    succeeded — every in-scope batch completed.
    partially_failed — some batches completed but the operation could not
    finish cleanly (e.g. a best-effort provider revoke failed during account
    deletion, or attempts were exhausted mid-run); a safe error code records
    why. Never silently retried.
    failed — a permanent validation failure or exhausted attempts before any
    destructive work, recorded with a safe code.
    cancelled — cancelled while still previewed or pending; never after a
    destructive batch committed.
    """

    previewed = "previewed"
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    partially_failed = "partially_failed"
    failed = "failed"
    cancelled = "cancelled"


# Cancellation is allowed only before any destructive batch could have
# committed (ADR 0005 §4): while the operation is still previewed or pending.
CANCELLABLE_DELETION_STATES: frozenset[str] = frozenset(
    {DeletionOperationState.previewed, DeletionOperationState.pending}
)
# States in which an operation still occupies the per-(user, type, scope)
# active slot — the partial-unique-index predicate below mirrors this exactly.
ACTIVE_DELETION_STATES: frozenset[str] = frozenset(
    {
        DeletionOperationState.previewed,
        DeletionOperationState.pending,
        DeletionOperationState.running,
    }
)
TERMINAL_DELETION_STATES: frozenset[str] = frozenset(
    {
        DeletionOperationState.succeeded,
        DeletionOperationState.partially_failed,
        DeletionOperationState.failed,
        DeletionOperationState.cancelled,
    }
)


class DeletionConfirmationKind(StrEnum):
    """Which typed confirmation phrase gates a user-requested operation.
    `retention` operations are system-initiated and carry no typed
    confirmation (absent from this enum by construction)."""

    delete_imported_data = "delete_imported_data"
    delete_account = "delete_account"


class ScheduledRunStatus(StrEnum):
    """Closed lifecycle for one user's one local-date scheduled brief
    attempt (ADR 0004 D48/D49).

    pending — claimed by the dispatcher, enqueued, not yet started.
    running — the worker has picked it up; a row stuck here past the stale
    threshold is recovered (requeued or failed), never left hanging forever.
    succeeded — a brief was generated and linked via `Brief.scheduled_run_id`.
    failed — a permanent error, or a transient error that exhausted retries.
    skipped — never attempted: outside the catch-up window, the user was
    deleted/disabled, or scheduling was turned off before the job ran.
    """

    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"


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
    # Google ID token `sub` claim — the sole identity key for Google sign-in
    # (ADR 0003 D15). NULL for dev-login users. Never matched by email; no
    # automatic account linking. Cleared on account deletion (ADR 0005 D61) so
    # the same Google identity can create a genuinely new account later.
    google_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    # Account deletion lifecycle (Stage 9 Delivery Phase 2, ADR 0005 D61).
    # `active` for every ordinary account; `deletion_pending` once deletion is
    # confirmed; `deleted` once anonymisation completes. A non-active account
    # cannot authenticate (`get_current_user`) or use ordinary APIs.
    account_state: Mapped[str] = mapped_column(String(20), default=UserAccountState.active)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A random, non-reversible identifier assigned at deletion. It replaces the
    # user identity in retained content-free tombstones; it is never derived
    # from the email, Google subject, or original id.
    deletion_subject_id: Mapped[uuid.UUID | None] = mapped_column(unique=True)


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
    # Incremental-sync cursors keyed by source type, e.g. {"gmail": {...},
    # "calendar": {...}} — each value a serialised `GoogleSyncCursor`
    # (committed cursor kept separate from mid-pagination continuation state,
    # Stage 7 remediation blocker #3). The two APIs' cursor types are
    # unrelated and never share a slot (ADR 0003 D21).
    sync_cursors: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Monotonic counter (Stage 7 remediation blocker #1): incremented every
    # time connector consent is (re)granted — new connect, reconnect, a
    # materially different scope grant, or a disconnect-then-reconnect.
    # Never incremented for an ordinary access-token refresh
    # (`GoogleTokenService.get_valid_access_token`), so an approval stays
    # valid across routine refreshes but goes stale the moment the
    # underlying authorisation actually changes.
    authorisation_revision: Mapped[int] = mapped_column(default=1)
    # Non-secret key-version identifiers (Stage 11A Phase 4A, F-P3-03): the
    # `key_id` recorded inside the matching envelope's own `v1:<key_id>:...`
    # prefix, kept as a queryable column so the rotation service can select
    # "rows not yet on the active key" without decrypting anything. NULL
    # means the corresponding ciphertext column is also NULL (no credential
    # stored). Never key material, never a token — safe to log or index.
    access_token_key_id: Mapped[str | None] = mapped_column(String(40))
    refresh_token_key_id: Mapped[str | None] = mapped_column(String(40))


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
    # When LifeFlow imported/observed this item (Stage 9 Delivery Phase 2). This
    # is the import instant, distinct from `occurred_at` (the email/event's own
    # date): imported-data deletion snapshots on this column so provider data
    # synced *after* an operation begins is never silently swept into its scope.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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


class BriefStatus(StrEnum):
    """Honest generation states surfaced to the user (skill §12).

    complete — sections composed from persisted signals.
    empty — generation ran but there were no signals to report.
    degraded — optional LLM prose failed or was rejected; the deterministic
    fallback summary is shown. Facts are unaffected (they never come from
    the LLM).
    partial — one or more configured sources are unavailable, a persisted
    signal was omitted because its source evidence could not be resolved, or
    an action-proposal candidate was skipped because its source data could
    not be validated.
    """

    complete = "complete"
    empty = "empty"
    degraded = "degraded"
    partial = "partial"


class Brief(Base):
    __tablename__ = "briefs"
    __table_args__ = (
        # Regeneration creates a new version; earlier versions are kept so the
        # user can always inspect what the system said before.
        UniqueConstraint("user_id", "briefing_date", "version", name="uq_briefs_user_date_version"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    briefing_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(20), default=BriefStatus.complete)
    summary: Mapped[str] = mapped_column(Text)
    sections_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_window: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    model_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Phase 2 (ADR 0004 D49): "manual" (the existing on-demand route) or
    # "scheduled". `scheduled_run_id` is a real, unique, nullable column
    # (not JSON-only) so a crashed-and-retried worker can look up "did this
    # run already produce a brief?" with a simple indexed query, and the
    # frontend can distinguish manual/scheduled without parsing metadata.
    generation_trigger: Mapped[str] = mapped_column(String(20), default="manual")
    # `use_alter` (Stage 8 Phase 2): `scheduled_brief_runs.brief_id` points
    # back at this table, so the two form a genuine FK cycle — SQLAlchemy's
    # declarative metadata (used directly by `Base.metadata.create_all` in
    # tests, bypassing Alembic) can only order that with one side deferred
    # to a post-create ALTER TABLE.
    scheduled_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "scheduled_brief_runs.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_briefs_scheduled_run_id",
        ),
        unique=True,
    )


class ScheduledBriefRun(Base):
    """One user's one local-date scheduled-brief attempt (ADR 0004 D48/D49).

    The unique constraint is the final duplicate guard: no process, retry,
    or race can ever produce two rows for the same user and local date."""

    __tablename__ = "scheduled_brief_runs"
    __table_args__ = (
        UniqueConstraint("user_id", "local_brief_date", name="uq_scheduled_brief_runs_user_date"),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')",
            name="ck_scheduled_brief_runs_status",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    local_brief_date: Mapped[Any] = mapped_column(Date)
    scheduled_for_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Snapshots of the settings that produced `scheduled_for_utc` — kept even
    # though they can be looked up live, so a later preference/timezone
    # change never rewrites the history of what this run was actually based on.
    timezone_snapshot: Mapped[str] = mapped_column(String(64))
    briefing_time_snapshot: Mapped[str] = mapped_column(String(5))
    status: Mapped[str] = mapped_column(String(20), default=ScheduledRunStatus.pending)
    queue_job_id: Mapped[str | None] = mapped_column(String(160))
    brief_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("briefs.id", ondelete="SET NULL"), unique=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Closed-vocabulary safe codes only (e.g. "missed_grace_window",
    # "worker_stale_timeout") — never a stack trace or personal content.
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ActionProposal(Base):
    __tablename__ = "action_proposals"
    __table_args__ = (
        UniqueConstraint("user_id", "origin_fingerprint", name="uq_action_proposals_user_origin"),
        CheckConstraint(
            "action_type IN ('create_task', 'create_gmail_draft', 'create_calendar_event')",
            name="ck_action_proposals_action_type",
        ),
        CheckConstraint("risk_level IN ('low', 'medium')", name="ck_action_proposals_risk"),
        CheckConstraint(
            "status IN ('proposed', 'edited', 'approved', 'rejected', "
            "'executing', 'executed', 'failed', 'expired')",
            name="ck_action_proposals_status",
        ),
        CheckConstraint("version >= 1", name="ck_action_proposals_version"),
        # NULL passes a SQL CHECK (unknown = pass) so this only ever
        # constrains an approved row — `unavailable` is never persisted here
        # (Stage 7 remediation blocker #1).
        CheckConstraint(
            "approved_execution_mode IN ('simulation', 'real')",
            name="ck_action_proposals_approved_execution_mode",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    origin_brief_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("briefs.id", ondelete="SET NULL"), index=True
    )
    origin_fingerprint: Mapped[str] = mapped_column(String(64))
    action_type: Mapped[str] = mapped_column(String(40))
    rationale: Mapped[str] = mapped_column(Text)
    source_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(default=1)
    risk_level: Mapped[str] = mapped_column(String(10))
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default=ProposalStatus.proposed)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_action_type: Mapped[str | None] = mapped_column(String(40))
    approved_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    approved_payload_hash: Mapped[str | None] = mapped_column(String(64))
    approved_binding_hash: Mapped[str | None] = mapped_column(String(64))
    approved_version: Mapped[int | None] = mapped_column()
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Immutable approval-bound execution-context snapshot (Stage 7
    # remediation blocker #1): captured once, at approval, from
    # `execution_context.resolve_execution_context()`. `execute()` must
    # revalidate the CURRENT context against this exact snapshot and refuse
    # to run on any difference — never recompute "what would run now" and
    # trust it blindly.
    approved_execution_mode: Mapped[str | None] = mapped_column(String(20))
    approved_provider: Mapped[str | None] = mapped_column(String(20))
    approved_connected_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connected_accounts.id", ondelete="SET NULL")
    )
    approved_authorisation_revision: Mapped[int | None] = mapped_column()
    approved_required_scope: Mapped[str | None] = mapped_column(String(200))
    approved_source_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connected_accounts.id", ondelete="SET NULL")
    )
    approved_execution_context_hash: Mapped[str | None] = mapped_column(String(64))
    user_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ActionExecution(Base):
    __tablename__ = "action_executions"
    __table_args__ = (
        UniqueConstraint("proposal_id", name="uq_action_executions_proposal"),
        CheckConstraint(
            "outcome IN ('pending', 'succeeded', 'failed', 'uncertain')",
            name="ck_action_executions_outcome",
        ),
        CheckConstraint(
            "execution_mode IN ('simulation', 'real')",
            name="ck_action_executions_execution_mode",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("action_proposals.id", ondelete="CASCADE"), index=True
    )
    # Duplicate execution attempts collide here instead of acting twice
    # (threat model T12).
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    approved_action_type: Mapped[str] = mapped_column(String(40))
    approved_proposal_version: Mapped[int] = mapped_column()
    executed_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    executed_payload_hash: Mapped[str] = mapped_column(String(64))
    approval_binding_hash: Mapped[str] = mapped_column(String(64))
    # Which path actually ran (Stage 7 remediation): persisted at creation,
    # never recomputed later, so a historical record stays truthful even if
    # the user's connected accounts change afterwards.
    execution_mode: Mapped[str] = mapped_column(String(20))
    # pending/succeeded/failed/uncertain (ADR 0003 D16). Durably committed as
    # `pending` before any real external call is made, independent of the
    # request's main transaction, so a crash or network failure cannot erase
    # the fact that an attempt happened.
    outcome: Mapped[str] = mapped_column(String(20), default=ExecutionOutcome.pending)
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


class MemoryItem(Base):
    """One inferred-memory item per user per closed registry key (ADR 0004
    D52/D55). Inferred, `provenance="inferred"` knowledge derived from the
    user's own deliberate in-app behaviour — never applied to outgoing
    content until the user confirms it into an explicit preference.

    The `(user_id, memory_key)` unique constraint is the final guard against
    two conflicting active memories for the same fact; the whole lifecycle is
    a single mutating row, not a stream of competing rows."""

    __tablename__ = "memory_items"
    __table_args__ = (
        UniqueConstraint("user_id", "memory_key", name="uq_memory_items_user_key"),
        CheckConstraint(
            "status IN ('candidate', 'confirmed', 'dismissed', 'superseded', 'expired')",
            name="ck_memory_items_status",
        ),
        # Suggest-only is the only application mode Phase 3 ships (D55): an
        # inferred value is never applied automatically, only after the user
        # confirms it into an explicit preference.
        CheckConstraint(
            "application_mode IN ('suggest_only')",
            name="ck_memory_items_application_mode",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_memory_items_confidence"),
        CheckConstraint("version >= 1", name="ck_memory_items_version"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    memory_key: Mapped[str] = mapped_column(String(100))
    # The normalised inferred value, e.g. {"value": "Kind regards"} — a short
    # closing token, never the draft body it was derived from (D53).
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default=MemoryStatus.candidate)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    first_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the item's evidence decays past the freshness floor (D54); display
    # and expiry only, never a policy input.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    application_mode: Mapped[str] = mapped_column(String(20), default="suggest_only")
    # The explicit preference key a confirmation writes to (D55) — the only
    # channel through which this memory can ever affect behaviour.
    corresponding_preference_key: Mapped[str | None] = mapped_column(String(100))
    # Recomputed display flag: an explicit preference for the same fact exists
    # and takes precedence, so this inferred value is not applied (D55).
    overridden_by_explicit: Mapped[bool] = mapped_column(default=False)
    # Sticky-dismissal guard (D55): a hash of the contributing evidence set at
    # dismissal. Recompute keeps the item dismissed until this fingerprint
    # changes (materially new evidence).
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_fingerprint: Mapped[str | None] = mapped_column(String(64))
    # Optimistic-concurrency guard: user edits/confirms/dismisses carry an
    # expected version; a stale write is a 409, never a silent overwrite.
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MemoryEvidence(Base):
    """A safe, deduplicated reference to one deliberate user action that
    supports an inferred memory (ADR 0004 D53). Stores only a normalised
    derived value (e.g. a sign-off token) and a reason code — never the draft
    body, recipients, subject, or any inbound content.

    The `(memory_item_id, source_proposal_id)` unique constraint makes
    inference idempotent: re-running a recompute over the same proposal never
    double-counts it."""

    __tablename__ = "memory_evidence"
    __table_args__ = (
        UniqueConstraint(
            "memory_item_id", "source_proposal_id", name="uq_memory_evidence_item_source"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    memory_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memory_items.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = _user_fk()
    evidence_type: Mapped[str] = mapped_column(String(60))
    # The proposal whose deliberate user edit + approval is the evidence.
    # SET NULL (not CASCADE): if the proposal is ever deleted, the evidence's
    # safe derived value survives for history; recompute tolerates the null.
    source_proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("action_proposals.id", ondelete="SET NULL")
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The normalised derived value only (e.g. "Kind regards") — never a body.
    derived_value: Mapped[str] = mapped_column(String(100))
    # Closed-vocabulary safe code (e.g. "approved_edited_draft").
    reason_code: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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


class DataDeletionOperation(Base):
    """One durable, owner-scoped destructive operation (Stage 9 Delivery
    Phase 2, ADR 0005). The single engine behind imported-data deletion,
    retention enforcement, and account deletion.

    The row is content-free by construction: it never stores message bodies,
    recipients, payloads, provider ids, or the typed confirmation phrase — only
    a scope descriptor (account id / retention bucket), counts, safe reason
    codes, and resume state. It survives worker crashes: the durable state
    (`state`, `resume_cursor_json`, `deleted_counts_json`) plus a fresh
    database query is authoritative on resume — never the queue payload, which
    carries only this row's id.

    `scope_key` is a short deterministic descriptor of the scope
    (`account:<uuid>` / `account` / `retention:<date>`) used by the partial
    unique index to guarantee at most one *active* operation per
    (user, type, scope). `version` is the optimistic-concurrency guard a
    confirmation must match.
    """

    __tablename__ = "data_deletion_operations"
    __table_args__ = (
        CheckConstraint(
            "operation_type IN ('imported_data', 'retention', 'account_deletion')",
            name="ck_data_deletion_operations_type",
        ),
        CheckConstraint(
            "requester_type IN ('user', 'system')",
            name="ck_data_deletion_operations_requester",
        ),
        CheckConstraint(
            "state IN ('previewed', 'pending', 'running', 'succeeded', "
            "'partially_failed', 'failed', 'cancelled')",
            name="ck_data_deletion_operations_state",
        ),
        CheckConstraint("version >= 1", name="ck_data_deletion_operations_version"),
        CheckConstraint("attempt_count >= 0", name="ck_data_deletion_operations_attempts"),
        Index("ix_data_deletion_operations_user_state", "user_id", "state"),
        Index("ix_data_deletion_operations_type_state", "operation_type", "state"),
        # At most one active operation per (user, type, scope). The predicate
        # mirrors `ACTIVE_DELETION_STATES` exactly: a terminal operation frees
        # the slot so the user can start a fresh one for the same scope.
        Index(
            "uq_data_deletion_operations_active_scope",
            "user_id",
            "operation_type",
            "scope_key",
            unique=True,
            postgresql_where=text(
                "state IN ('previewed', 'pending', 'running')"  # pragma: allowlist secret
            ),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    operation_type: Mapped[str] = mapped_column(String(20))
    requester_type: Mapped[str] = mapped_column(String(10))
    source_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connected_accounts.id", ondelete="SET NULL")
    )
    scope_key: Mapped[str] = mapped_column(String(80))
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    snapshot_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(20), default=DeletionOperationState.previewed)
    # NULL for system-initiated retention operations (no typed confirmation).
    typed_confirmation_kind: Mapped[str | None] = mapped_column(String(30))
    preview_counts_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    preserved_counts_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    deleted_counts_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Content-free binding of the confirmation to the reviewed plan (Stage 9
    # Delivery Phase 2 focused remediation): a deterministic sha256 of the
    # affected record ids + their planned dispositions, plus the plan-policy
    # version. At confirmation the plan is recomputed against the same snapshot
    # and compared; a material change refreshes the preview and refuses to run.
    plan_fingerprint: Mapped[str | None] = mapped_column(String(64))
    plan_policy_version: Mapped[str | None] = mapped_column(String(16))
    resume_cursor_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    # A user preview goes stale after this instant and can no longer be
    # confirmed (ADR 0005 §5). System retention operations set it far ahead.
    preview_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Closed-vocabulary safe codes only (e.g. "provider_revoke_failed",
    # "worker_stale_timeout") — never a stack trace or personal content.
    safe_error_code: Mapped[str | None] = mapped_column(String(64))
    safe_error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
