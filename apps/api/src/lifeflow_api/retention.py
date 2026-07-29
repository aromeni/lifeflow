"""Retention enforcement (Stage 9 Delivery Phase 2, ADR 0005 D62).

The daily retention scan creates durable, system-initiated deletion operations
and runs them through the *same* planner and worker semantics as user-requested
imported-data deletion — retention can never bypass a preservation rule. It is
age-scoped (validated global settings) rather than account-scoped, uses a
controllable clock, is idempotent across repeated cron ticks and multiple
workers (the per-day scope key + partial unique index guarantee at most one
active retention operation per user per day), and is bounded so an initial
rollout never triggers a multi-year backfill storm.

Preserved by construction (never age-deleted): pending/uncertain executions,
confirmed explicit preferences, and approved/executed proposal history (kept as
minimised tombstones under the longer approved-terminal horizon).
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.audit import record_audit_event
from lifeflow_api.deletion_ops import (
    DataDeletionOperationRepository,
    scope_key_for,
)
from lifeflow_api.deletion_planner import Counts, apply_derived_decisions
from lifeflow_api.models import (
    ActionExecution,
    ActionProposal,
    Brief,
    DataDeletionOperation,
    DeletionOperationState,
    DeletionOperationType,
    DeletionRequesterType,
    ExecutionOutcome,
    MemoryItem,
    MemoryStatus,
    ProposalStatus,
    ScheduledBriefRun,
    ScheduledRunStatus,
    SourceItem,
)

logger = logging.getLogger(__name__)

CAT_BRIEFS = "briefs"
CAT_UNAPPROVED_PROPOSALS = "action_proposals"
CAT_SCHEDULED_RUNS = "scheduled_brief_runs"
CAT_MEMORY_ITEMS = "memory_items"
CAT_SOURCE_ITEMS = "source_items"

_UNAPPROVED_STATUSES = (
    ProposalStatus.proposed,
    ProposalStatus.edited,
    ProposalStatus.rejected,
    ProposalStatus.expired,
)


@dataclass(frozen=True)
class RetentionHorizons:
    source_items_days: int
    brief_versions_days: int
    unapproved_proposals_days: int
    scheduled_runs_days: int
    memory_evidence_days: int

    def cutoff(self, days: int, *, now: datetime) -> datetime:
        return now - timedelta(days=days)


async def _expired_source_external_ids(
    session: AsyncSession, user_id: uuid.UUID, *, cutoff: datetime
) -> set[str]:
    rows = await session.execute(
        select(SourceItem.external_id).where(
            SourceItem.user_id == user_id, SourceItem.created_at <= cutoff
        )
    )
    return {r[0] for r in rows.all()}


async def _all_external_ids(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    rows = await session.execute(
        select(SourceItem.external_id).where(SourceItem.user_id == user_id)
    )
    return {r[0] for r in rows.all()}


@dataclass
class RetentionStep:
    done: bool
    progressed: bool


async def run_retention_step(
    session: AsyncSession,
    operation: DataDeletionOperation,
    *,
    horizons: RetentionHorizons,
    now: datetime,
    batch_size: int,
) -> RetentionStep:
    """One bounded phase step for a retention operation, uniform with the other
    drivers. Phase `derived` applies the reference-graph decisions for expired
    source evidence (shared verbatim with imported-data deletion) plus the
    modest age-based categories; phase `sources` bulk-deletes expired source
    items in bounded batches."""
    user_id = operation.user_id
    cursor = dict(operation.resume_cursor_json or {})
    phase = cursor.get("phase", "derived")
    deleted = Counts(dict(operation.deleted_counts_json or {}))
    source_cutoff = horizons.cutoff(horizons.source_items_days, now=now)

    if phase == "derived":
        removed = await _expired_source_external_ids(session, user_id, cutoff=source_cutoff)
        surviving = await _all_external_ids(session, user_id) - removed
        # Identical dependency semantics as imported-data deletion (§11).
        await apply_derived_decisions(
            session, user_id, removed=removed, surviving=surviving, deleted=deleted
        )
        await _delete_age_based_categories(
            session, user_id, horizons=horizons, now=now, deleted=deleted
        )
        operation.resume_cursor_json = {"phase": "sources"}
        operation.deleted_counts_json = deleted.to_json()
        return RetentionStep(done=False, progressed=True)

    if phase == "sources":
        ids = (
            (
                await session.execute(
                    select(SourceItem.id)
                    .where(SourceItem.user_id == user_id, SourceItem.created_at <= source_cutoff)
                    .order_by(SourceItem.id)
                    .limit(batch_size)
                )
            )
            .scalars()
            .all()
        )
        if ids:
            await session.execute(delete(SourceItem).where(SourceItem.id.in_(ids)))
            deleted.add(CAT_SOURCE_ITEMS, len(ids))
            operation.deleted_counts_json = deleted.to_json()
            return RetentionStep(done=False, progressed=True)
        operation.resume_cursor_json = {"phase": "done"}
        return RetentionStep(done=True, progressed=True)

    return RetentionStep(done=True, progressed=False)


async def _delete_age_based_categories(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    horizons: RetentionHorizons,
    now: datetime,
    deleted: Counts,
) -> None:
    # Expired brief versions.
    brief_cutoff = horizons.cutoff(horizons.brief_versions_days, now=now)
    brief_ids = (
        (
            await session.execute(
                select(Brief.id).where(Brief.user_id == user_id, Brief.generated_at <= brief_cutoff)
            )
        )
        .scalars()
        .all()
    )
    if brief_ids:
        await session.execute(delete(Brief).where(Brief.id.in_(brief_ids)))
        deleted.add(CAT_BRIEFS, len(brief_ids))

    # Expired unapproved proposals with no pending/uncertain execution. Approved
    # and executed history follow the longer approved-terminal horizon and are
    # never swept here; a pending/uncertain execution is never deleted.
    proposal_cutoff = horizons.cutoff(horizons.unapproved_proposals_days, now=now)
    unapproved = (
        (
            await session.execute(
                select(ActionProposal.id).where(
                    ActionProposal.user_id == user_id,
                    ActionProposal.status.in_(_UNAPPROVED_STATUSES),
                    ActionProposal.approved_at.is_(None),
                    ActionProposal.created_at <= proposal_cutoff,
                )
            )
        )
        .scalars()
        .all()
    )
    deletable_proposals: list[uuid.UUID] = []
    for proposal_id in unapproved:
        outcome = (
            await session.execute(
                select(ActionExecution.outcome).where(ActionExecution.proposal_id == proposal_id)
            )
        ).scalar_one_or_none()
        if outcome in (ExecutionOutcome.pending, ExecutionOutcome.uncertain):
            continue
        deletable_proposals.append(proposal_id)
    if deletable_proposals:
        await session.execute(
            delete(ActionProposal).where(ActionProposal.id.in_(deletable_proposals))
        )
        deleted.add(CAT_UNAPPROVED_PROPOSALS, len(deletable_proposals))

    # Expired terminal scheduled-brief runs.
    run_cutoff = horizons.cutoff(horizons.scheduled_runs_days, now=now)
    run_ids = (
        (
            await session.execute(
                select(ScheduledBriefRun.id).where(
                    ScheduledBriefRun.user_id == user_id,
                    ScheduledBriefRun.completed_at.isnot(None),
                    ScheduledBriefRun.completed_at <= run_cutoff,
                    ScheduledBriefRun.status.in_(
                        (
                            ScheduledRunStatus.succeeded,
                            ScheduledRunStatus.failed,
                            ScheduledRunStatus.skipped,
                        )
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    if run_ids:
        await session.execute(delete(ScheduledBriefRun).where(ScheduledBriefRun.id.in_(run_ids)))
        deleted.add(CAT_SCHEDULED_RUNS, len(run_ids))

    # Expired/dismissed inferred-memory candidates (never a confirmed one, whose
    # explicit preference does not expire).
    memory_cutoff = horizons.cutoff(horizons.memory_evidence_days, now=now)
    memory_ids = (
        (
            await session.execute(
                select(MemoryItem.id).where(
                    MemoryItem.user_id == user_id,
                    MemoryItem.status.in_((MemoryStatus.expired, MemoryStatus.dismissed)),
                    MemoryItem.updated_at <= memory_cutoff,
                )
            )
        )
        .scalars()
        .all()
    )
    if memory_ids:
        await session.execute(delete(MemoryItem).where(MemoryItem.id.in_(memory_ids)))
        deleted.add(CAT_MEMORY_ITEMS, len(memory_ids))


async def _users_with_expired_data(
    session: AsyncSession, *, source_cutoff: datetime, limit: int
) -> list[uuid.UUID]:
    """Bounded scan for users with expired source items — the primary retention
    trigger. Cross-user by necessity (like the scheduled-brief dispatcher);
    every operation it creates is owner-scoped thereafter."""
    rows = await session.execute(
        select(SourceItem.user_id)
        .where(SourceItem.created_at <= source_cutoff)
        .group_by(SourceItem.user_id)
        .order_by(SourceItem.user_id)
        .limit(limit)
    )
    return [r[0] for r in rows.all()]


@dataclass
class RetentionScanResult:
    created: int = 0
    reused: int = 0


async def scan_and_create_retention_operations(
    session: AsyncSession,
    *,
    horizons: RetentionHorizons,
    now: datetime,
    max_operations: int,
) -> tuple[RetentionScanResult, list[uuid.UUID]]:
    """Create (or reuse) one durable retention operation per user with expired
    data for today's bucket, up to `max_operations`. Returns the result and the
    ids of freshly-created pending operations for the caller to enqueue."""
    source_cutoff = horizons.cutoff(horizons.source_items_days, now=now)
    bucket = now.date().isoformat()
    scope_key = scope_key_for(DeletionOperationType.retention, retention_bucket=bucket)
    result = RetentionScanResult()
    enqueue_ids: list[uuid.UUID] = []
    for user_id in await _users_with_expired_data(
        session, source_cutoff=source_cutoff, limit=max_operations
    ):
        repo = DataDeletionOperationRepository(session, user_id)
        existing = await repo.get_active(DeletionOperationType.retention, scope_key)
        if existing is not None:
            result.reused += 1
            continue
        operation = DataDeletionOperation(
            user_id=user_id,
            operation_type=DeletionOperationType.retention,
            requester_type=DeletionRequesterType.system,
            scope_key=scope_key,
            scope_json={"bucket": bucket},
            snapshot_cutoff=now,
            state=DeletionOperationState.pending,
            preview_expires_at=None,
        )
        try:
            async with session.begin_nested():
                repo.add(operation)
                await session.flush()
        except Exception:
            # Another cron worker created it first — the partial unique index is
            # the final guard; yield silently (idempotent across workers).
            result.reused += 1
            continue
        record_audit_event(
            session,
            user_id=user_id,
            actor="system:retention",
            event_type="retention.operation_started",
            entity_type="data_deletion_operation",
            entity_id=str(operation.id),
            metadata={"bucket": bucket},
        )
        result.created += 1
        enqueue_ids.append(operation.id)
    await session.flush()
    return result, enqueue_ids


__all__ = [
    "RetentionHorizons",
    "RetentionScanResult",
    "RetentionStep",
    "run_retention_step",
    "scan_and_create_retention_operations",
]
