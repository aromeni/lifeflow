"""Durable deletion engine — operation lifecycle and run dispatcher
(Stage 9 Delivery Phase 2, ADR 0005).

Owner-scoped preview/confirm/cancel for user-requested operations, an atomic
worker claim (conditional `UPDATE … RETURNING`, so two workers never process
one operation), a heartbeat, stale-operation recovery, a pending-operation
drain for the Redis-was-down case, and a uniform per-type batch loop that
commits each bounded batch and finalises with a content-free audit tombstone.

Every destructive step routes through `deletion_planner` (imported-data +
retention share the exact dependency semantics) or `account_deletion`; nothing
here embeds its own deletion rules.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from arq.connections import ArqRedis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.account_deletion import (
    ProviderRevoker,
    account_disposition_lines,
    count_account_deletion_plan,
    run_account_deletion_step,
)
from lifeflow_api.audit import record_audit_event
from lifeflow_api.config import Settings
from lifeflow_api.deletion_ops import (
    ERROR_MAX_ATTEMPTS,
    ERROR_PROVIDER_REVOKE_FAILED,
    ERROR_WORKER_STALE_TIMEOUT,
    JOB_FUNCTION_NAME,
    DataDeletionOperationRepository,
    DeletionOperationNotFoundError,
    InvalidConfirmationError,
    InvalidDeletionStateError,
    PreviewChangedError,
    PreviewExpiredError,
    StaleDeletionVersionError,
    expected_phrase,
    scope_key_for,
)
from lifeflow_api.deletion_planner import (
    CAT_SOURCE_ITEMS,
    PHASE_DERIVED,
    PHASE_DONE,
    PHASE_SOURCES,
    Counts,
    count_imported_data_plan,
    delete_source_items_batch,
    hash_lines,
    imported_data_disposition_lines,
    run_derived_cleanup,
)
from lifeflow_api.memory_inference import recompute_user_memory
from lifeflow_api.models import (
    CANCELLABLE_DELETION_STATES,
    TERMINAL_DELETION_STATES,
    ConnectedAccount,
    DataDeletionOperation,
    DeletionConfirmationKind,
    DeletionOperationState,
    DeletionOperationType,
    DeletionRequesterType,
    User,
    UserAccountState,
)
from lifeflow_api.retention import RetentionHorizons, run_retention_step

logger = logging.getLogger(__name__)

# Bumped whenever the planner's disposition rules change, so a preview computed
# under an older policy is invalidated at confirmation even if the record set is
# unchanged (Stage 9 Delivery Phase 2 focused remediation).
PLAN_POLICY_VERSION = "1"


async def compute_plan_fingerprint(session: AsyncSession, operation: DataDeletionOperation) -> str:
    """A deterministic, content-free digest of the affected record ids and their
    planned dispositions (plus policy version, type, scope, and snapshot). Two
    equivalent plans hash identically; any material disposition change hashes
    differently. Never contains personal content or provider identifiers."""
    prefix = [
        f"policy={PLAN_POLICY_VERSION}",
        f"type={operation.operation_type}",
        f"scope={operation.scope_key}",
        f"cutoff={operation.snapshot_cutoff.isoformat()}",
    ]
    if operation.operation_type == DeletionOperationType.imported_data:
        account_id = operation.source_account_id
        if account_id is None:  # pragma: no cover - imported_data always has an account
            return hash_lines(prefix)
        lines = await imported_data_disposition_lines(
            session,
            operation.user_id,
            source_account_id=account_id,
            snapshot_cutoff=operation.snapshot_cutoff,
        )
    elif operation.operation_type == DeletionOperationType.account_deletion:
        lines = await account_disposition_lines(session, operation.user_id)
    else:  # pragma: no cover - retention has no reviewed preview to bind
        lines = []
    return hash_lines(prefix + lines)


def _event_type(operation_type: str, suffix: str) -> str:
    """Safe audit event-type names (§15)."""
    if operation_type == DeletionOperationType.imported_data:
        return f"data.import_deletion_{suffix}"
    if operation_type == DeletionOperationType.account_deletion:
        return f"account.deletion_{suffix}"
    return f"retention.operation_{suffix}"


def _audit(
    session: AsyncSession, operation: DataDeletionOperation, suffix: str, actor: str
) -> None:
    record_audit_event(
        session,
        user_id=operation.user_id,
        actor=actor,
        event_type=_event_type(operation.operation_type, suffix),
        entity_type="data_deletion_operation",
        entity_id=str(operation.id),
        metadata={
            "operation_type": operation.operation_type,
            "state": operation.state,
            **({"error_code": operation.safe_error_code} if operation.safe_error_code else {}),
        },
    )


# --- preview creation (owner-scoped, durable) -------------------------------


async def create_imported_data_preview(
    session: AsyncSession,
    user: User,
    *,
    source_account_id: uuid.UUID,
    now: datetime,
    ttl_minutes: int,
) -> DataDeletionOperation:
    """Create (or reuse the existing active) imported-data deletion preview for
    one owned account. Reusing the active operation is the documented rule that
    makes two equivalent preview requests never create two concurrent
    operations (§5)."""
    account = await session.get(ConnectedAccount, source_account_id)
    if account is None or account.user_id != user.id:
        raise DeletionOperationNotFoundError("No such connected account for this user.")
    repo = DataDeletionOperationRepository(session, user.id)
    scope_key = scope_key_for(
        DeletionOperationType.imported_data, source_account_id=source_account_id
    )
    existing = await repo.get_active(DeletionOperationType.imported_data, scope_key)
    if existing is not None:
        return existing

    plan = await count_imported_data_plan(
        session, user.id, source_account_id=source_account_id, snapshot_cutoff=now
    )
    operation = DataDeletionOperation(
        user_id=user.id,
        operation_type=DeletionOperationType.imported_data,
        requester_type=DeletionRequesterType.user,
        source_account_id=source_account_id,
        scope_key=scope_key,
        scope_json={"source_account_id": str(source_account_id), "provider": account.provider},
        snapshot_cutoff=now,
        state=DeletionOperationState.previewed,
        typed_confirmation_kind=DeletionConfirmationKind.delete_imported_data,
        preview_counts_json=plan.preview_counts.to_json(),
        preserved_counts_json=plan.preserved_counts.to_json(),
        preview_expires_at=now + timedelta(minutes=ttl_minutes),
        plan_policy_version=PLAN_POLICY_VERSION,
    )
    operation.plan_fingerprint = await compute_plan_fingerprint(session, operation)
    repo.add(operation)
    await session.flush()
    _audit(session, operation, "previewed", actor=f"user:{user.id}")
    return operation


async def create_account_deletion_preview(
    session: AsyncSession, user: User, *, now: datetime, ttl_minutes: int
) -> DataDeletionOperation:
    repo = DataDeletionOperationRepository(session, user.id)
    scope_key = scope_key_for(DeletionOperationType.account_deletion)
    existing = await repo.get_active(DeletionOperationType.account_deletion, scope_key)
    if existing is not None:
        return existing

    plan = await count_account_deletion_plan(session, user.id)
    operation = DataDeletionOperation(
        user_id=user.id,
        operation_type=DeletionOperationType.account_deletion,
        requester_type=DeletionRequesterType.user,
        scope_key=scope_key,
        scope_json={},
        snapshot_cutoff=now,
        state=DeletionOperationState.previewed,
        typed_confirmation_kind=DeletionConfirmationKind.delete_account,
        preview_counts_json=plan.preview_counts.to_json(),
        preserved_counts_json=plan.preserved_counts.to_json(),
        preview_expires_at=now + timedelta(minutes=ttl_minutes),
        plan_policy_version=PLAN_POLICY_VERSION,
    )
    operation.plan_fingerprint = await compute_plan_fingerprint(session, operation)
    repo.add(operation)
    await session.flush()
    _audit(session, operation, "previewed", actor=f"user:{user.id}")
    return operation


# --- confirm / cancel -------------------------------------------------------


async def _refresh_preview(
    session: AsyncSession,
    operation: DataDeletionOperation,
    *,
    now: datetime,
    ttl_minutes: int,
) -> None:
    """Recompute the counts and fingerprint of a preview whose plan changed,
    bump its version, and extend its window — keeping it `previewed` so the user
    can review and re-confirm the refreshed plan."""
    if operation.operation_type == DeletionOperationType.imported_data:
        account_id = operation.source_account_id
        if account_id is not None:
            plan = await count_imported_data_plan(
                session,
                operation.user_id,
                source_account_id=account_id,
                snapshot_cutoff=operation.snapshot_cutoff,
            )
            operation.preview_counts_json = plan.preview_counts.to_json()
            operation.preserved_counts_json = plan.preserved_counts.to_json()
    elif operation.operation_type == DeletionOperationType.account_deletion:
        account_plan = await count_account_deletion_plan(session, operation.user_id)
        operation.preview_counts_json = account_plan.preview_counts.to_json()
        operation.preserved_counts_json = account_plan.preserved_counts.to_json()
    operation.plan_policy_version = PLAN_POLICY_VERSION
    operation.plan_fingerprint = await compute_plan_fingerprint(session, operation)
    operation.preview_expires_at = now + timedelta(minutes=ttl_minutes)
    operation.version += 1
    _audit(session, operation, "previewed", actor=f"user:{operation.user_id}")
    await session.flush()


async def confirm_operation(
    session: AsyncSession,
    user: User,
    operation_id: uuid.UUID,
    *,
    expected_version: int,
    phrase: str,
    now: datetime,
    preview_ttl_minutes: int,
) -> DataDeletionOperation:
    """Validate the typed confirmation, verify the plan is unchanged since it was
    reviewed, and transition previewed → pending. Idempotent: re-confirming an
    already-pending/running operation returns it unchanged. The row is locked
    `FOR UPDATE`, so two confirmers racing serialise — one confirms, the other
    sees the resulting state — and they can never confirm two different plan
    versions."""
    locked = await session.execute(
        select(DataDeletionOperation)
        .where(
            DataDeletionOperation.id == operation_id,
            DataDeletionOperation.user_id == user.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    operation = locked.scalar_one_or_none()
    if operation is None:
        raise DeletionOperationNotFoundError("No such deletion operation.")
    if operation.state in (DeletionOperationState.pending, DeletionOperationState.running):
        return operation  # already confirmed — idempotent
    if operation.state in TERMINAL_DELETION_STATES:
        raise InvalidDeletionStateError("This operation has already finished.")
    if operation.state != DeletionOperationState.previewed:  # pragma: no cover - exhaustive guard
        raise InvalidDeletionStateError("This operation cannot be confirmed.")
    if operation.preview_expires_at is not None and now > operation.preview_expires_at:
        raise PreviewExpiredError("This preview has expired; start a new one.")
    if operation.version != expected_version:
        raise StaleDeletionVersionError("This preview changed; review it again.")
    if phrase != expected_phrase(operation.typed_confirmation_kind):
        raise InvalidConfirmationError("The confirmation phrase did not match exactly.")

    # Bind the confirmation to the reviewed plan: recompute against the original
    # snapshot and refuse to run if a disposition changed (proposal approved,
    # execution now pending/uncertain, dependency added/removed, a mixed signal
    # became fully unsupported, or the plan policy changed).
    current_fingerprint = await compute_plan_fingerprint(session, operation)
    if (
        operation.plan_policy_version != PLAN_POLICY_VERSION
        or operation.plan_fingerprint != current_fingerprint
    ):
        await _refresh_preview(session, operation, now=now, ttl_minutes=preview_ttl_minutes)
        raise PreviewChangedError(
            "What would be deleted changed since you reviewed it; review the refreshed preview."
        )

    operation.state = DeletionOperationState.pending
    operation.version += 1
    if operation.operation_type == DeletionOperationType.account_deletion:
        # Block new sync/proposal/approval/execution immediately (§12), before
        # the worker runs.
        user.account_state = UserAccountState.deletion_pending
    _audit(session, operation, "requested", actor=f"user:{user.id}")
    await session.flush()
    return operation


async def cancel_operation(
    session: AsyncSession, user: User, operation_id: uuid.UUID, *, now: datetime
) -> DataDeletionOperation:
    """Cancel while still previewed or pending — never once a destructive batch
    could have committed (§4)."""
    operation = await DataDeletionOperationRepository(session, user.id).get(operation_id)
    if operation is None:
        raise DeletionOperationNotFoundError("No such deletion operation.")
    if operation.state not in CANCELLABLE_DELETION_STATES:
        raise InvalidDeletionStateError("This operation can no longer be cancelled.")
    operation.state = DeletionOperationState.cancelled
    operation.cancellation_requested_at = now
    operation.completed_at = now
    operation.version += 1
    if operation.operation_type == DeletionOperationType.account_deletion:
        user.account_state = UserAccountState.active  # restore — deletion abandoned
    _audit(session, operation, "cancelled", actor=f"user:{user.id}")
    await session.flush()
    return operation


# --- worker: atomic claim, heartbeat, recovery, drain -----------------------


async def claim_operation(
    session: AsyncSession, operation_id: uuid.UUID, *, now: datetime
) -> DataDeletionOperation | None:
    """Atomically transition pending → running and bump the attempt count. Only
    one worker can win (conditional UPDATE); the loser gets None. Stale
    `running` operations are returned to pending by `recover_stale_operations`
    first, so this only ever claims pending — never steals a live run."""
    claimed = (
        await session.execute(
            update(DataDeletionOperation)
            .where(
                DataDeletionOperation.id == operation_id,
                DataDeletionOperation.state == DeletionOperationState.pending,
            )
            .values(
                state=DeletionOperationState.running,
                started_at=now,
                heartbeat_at=now,
                attempt_count=DataDeletionOperation.attempt_count + 1,
            )
            .returning(DataDeletionOperation.id)
        )
    ).first()
    await session.commit()
    if claimed is None:
        return None
    return await session.get(DataDeletionOperation, operation_id, populate_existing=True)


@dataclass
class RecoveryResult:
    requeued: int = 0
    failed: int = 0
    drained: int = 0


async def recover_stale_operations(
    session: AsyncSession,
    redis: ArqRedis | None,
    *,
    now: datetime,
    heartbeat_timeout: timedelta,
    max_attempts: int,
) -> RecoveryResult:
    """Recover `running` operations whose worker died (heartbeat older than the
    timeout) and drain `pending` operations that were never enqueued (Redis was
    down at confirm time). Cross-user by necessity."""
    result = RecoveryResult()
    cutoff = now - heartbeat_timeout
    stale = (
        (
            await session.execute(
                select(DataDeletionOperation).where(
                    DataDeletionOperation.state == DeletionOperationState.running,
                    DataDeletionOperation.heartbeat_at < cutoff,
                )
            )
        )
        .scalars()
        .all()
    )
    for operation in stale:
        if operation.attempt_count >= max_attempts:
            operation.state = DeletionOperationState.partially_failed
            operation.safe_error_code = ERROR_WORKER_STALE_TIMEOUT
            operation.safe_error_message = "The worker did not finish after repeated attempts."
            operation.completed_at = now
            _audit(session, operation, "partially_failed", actor="system:deletion")
            result.failed += 1
        else:
            operation.state = DeletionOperationState.pending
            operation.started_at = None
            result.requeued += 1
            if redis is not None:
                await _enqueue(redis, operation, now)
    # Drain pending operations that never made it onto the queue.
    pending = (
        (
            await session.execute(
                select(DataDeletionOperation).where(
                    DataDeletionOperation.state == DeletionOperationState.pending,
                    DataDeletionOperation.enqueued_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for operation in pending:
        if redis is not None:
            await _enqueue(redis, operation, now)
            result.drained += 1
    await session.commit()
    return result


async def _enqueue(redis: ArqRedis, operation: DataDeletionOperation, now: datetime) -> None:
    await redis.enqueue_job(JOB_FUNCTION_NAME, str(operation.id))
    operation.enqueued_at = now


# --- run one operation to completion (bounded batches) ----------------------


async def run_operation(
    session: AsyncSession,
    operation_id: uuid.UUID,
    *,
    now: datetime,
    horizons: RetentionHorizons,
    batch_size: int,
    max_attempts: int,
    revoker: ProviderRevoker | None = None,
) -> None:
    """The worker body. Claims the operation, then processes bounded batches —
    committing each — until done, and finalises with a safe terminal state and
    audit tombstone. A crash mid-loop leaves it `running`; stale recovery
    re-enqueues it and the resume cursor continues where it left off."""
    operation = await claim_operation(session, operation_id, now=now)
    if operation is None:
        return  # already claimed, terminal, or gone — never act twice
    if operation.attempt_count > max_attempts:
        operation.state = DeletionOperationState.failed
        operation.safe_error_code = ERROR_MAX_ATTEMPTS
        operation.safe_error_message = "This operation exceeded the maximum attempts."
        operation.completed_at = now
        _audit(session, operation, "failed", actor="system:deletion")
        await session.commit()
        return

    _audit(session, operation, "started", actor="system:deletion")
    await session.commit()

    while True:
        done = await _run_one_batch(
            session, operation, now=now, horizons=horizons, batch_size=batch_size, revoker=revoker
        )
        operation.heartbeat_at = now
        await session.commit()
        if done:
            break

    provider_revoke_failed = bool(
        (operation.resume_cursor_json or {}).get("provider_revoke_failed")
    )
    if provider_revoke_failed:
        operation.state = DeletionOperationState.partially_failed
        operation.safe_error_code = ERROR_PROVIDER_REVOKE_FAILED
        operation.safe_error_message = (
            "Provider access could not be revoked; local data was still erased."
        )
        _audit(session, operation, "partially_failed", actor="system:deletion")
    else:
        operation.state = DeletionOperationState.succeeded
        _audit(session, operation, "completed", actor="system:deletion")
    operation.completed_at = now
    await session.commit()


async def _run_one_batch(
    session: AsyncSession,
    operation: DataDeletionOperation,
    *,
    now: datetime,
    horizons: RetentionHorizons,
    batch_size: int,
    revoker: ProviderRevoker | None,
) -> bool:
    """Dispatch one bounded batch by operation type. Returns whether the
    operation is now complete."""
    if operation.operation_type == DeletionOperationType.imported_data:
        return await _run_imported_data_batch(session, operation, now=now, batch_size=batch_size)
    if operation.operation_type == DeletionOperationType.account_deletion:
        step = await run_account_deletion_step(
            session, operation, now=now, batch_size=batch_size, revoker=revoker
        )
        return step.done
    retention_step = await run_retention_step(
        session, operation, horizons=horizons, now=now, batch_size=batch_size
    )
    return retention_step.done


async def _run_imported_data_batch(
    session: AsyncSession,
    operation: DataDeletionOperation,
    *,
    now: datetime,
    batch_size: int,
) -> bool:
    cursor = dict(operation.resume_cursor_json or {})
    phase = cursor.get("phase", PHASE_DERIVED)
    deleted = Counts(dict(operation.deleted_counts_json or {}))
    account_id = operation.source_account_id
    if account_id is None:  # pragma: no cover - imported_data always has an account
        return True

    if phase == PHASE_DERIVED:
        await run_derived_cleanup(
            session,
            operation.user_id,
            source_account_id=account_id,
            snapshot_cutoff=operation.snapshot_cutoff,
            deleted=deleted,
        )
        # Recompute inferred memory after evidence changed (§8) — idempotent,
        # never deletes a confirmed explicit preference.
        await recompute_user_memory(session, operation.user_id, now=now)
        operation.resume_cursor_json = {"phase": PHASE_SOURCES}
        operation.deleted_counts_json = deleted.to_json()
        return False

    if phase == PHASE_SOURCES:
        n = await delete_source_items_batch(
            session,
            operation.user_id,
            source_account_id=account_id,
            snapshot_cutoff=operation.snapshot_cutoff,
            limit=batch_size,
        )
        if n:
            deleted.add(CAT_SOURCE_ITEMS, n)
            operation.deleted_counts_json = deleted.to_json()
            return False
        operation.resume_cursor_json = {"phase": PHASE_DONE}
        return True

    return True


# --- guards used by mutation routes -----------------------------------------


def account_is_active(user: User) -> bool:
    return user.account_state == UserAccountState.active


def build_settings_horizons(settings: Settings) -> RetentionHorizons:
    """RetentionHorizons from validated app settings (kept here so callers do
    not reach into config field names directly)."""
    return RetentionHorizons(
        source_items_days=settings.retention_source_items_days,
        brief_versions_days=settings.retention_brief_versions_days,
        unapproved_proposals_days=settings.retention_unapproved_proposals_days,
        scheduled_runs_days=settings.retention_scheduled_runs_days,
        memory_evidence_days=settings.retention_memory_evidence_days,
    )


__all__ = [
    "PLAN_POLICY_VERSION",
    "RecoveryResult",
    "account_is_active",
    "build_settings_horizons",
    "cancel_operation",
    "claim_operation",
    "compute_plan_fingerprint",
    "confirm_operation",
    "create_account_deletion_preview",
    "create_imported_data_preview",
    "recover_stale_operations",
    "run_operation",
]
