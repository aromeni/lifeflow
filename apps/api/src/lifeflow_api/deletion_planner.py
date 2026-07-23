"""Deterministic derived-data deletion planner (Stage 9 Delivery Phase 2,
ADR 0005 D63).

One planner defines *every* delete/preserve/recompute/minimise decision, so
imported-data deletion, retention enforcement, and account deletion can never
diverge, and a preview's counts can never disagree with what the worker
actually does — both call the same owner-scoped scoping queries here.

Reference graph (established by the extraction pipeline): a `Signal`'s
`evidence_refs` and an `ActionProposal`'s `source_refs` are both lists of
`SourceItem.external_id` strings, resolved through a `{external_id: item}` map.
So "the evidence behind this derived record" is exactly "the SourceItems whose
external_id appears in its refs". A derived record is *fully unsupported* when
none of its refs resolve to a **surviving** SourceItem.

Preservation invariants (never violated by any operation type):
- a pending or uncertain `ActionExecution` is never deleted, and its proposal
  is preserved (minimised) so the unresolved outcome stays explainable;
- a confirmed explicit `Preference` is never deleted because inference
  evidence aged or was removed;
- approved/executed proposal history is preserved as a **content-free
  tombstone**, never exposed and never fully deleted while its execution
  history matters.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.models import (
    ActionExecution,
    ActionProposal,
    ExecutionOutcome,
    MemoryEvidence,
    ProposalStatus,
    Signal,
    SourceItem,
)

# --- category keys (stable count vocabulary shared by preview and worker) ---
CAT_SOURCE_ITEMS = "source_items"
CAT_SIGNALS = "signals"
CAT_PROPOSALS = "action_proposals"
CAT_EXECUTIONS = "action_executions"
CAT_MEMORY_EVIDENCE = "memory_evidence"

# preservation / disposition buckets surfaced in previews (§6)
DISPOSITION_PRESERVED_PENDING_UNCERTAIN = "preserved_pending_uncertain_executions"
DISPOSITION_MINIMISED_HISTORY = "minimised_proposal_history"
DISPOSITION_RECOMPUTED_SIGNALS = "recomputed_signals"
DISPOSITION_SOURCE_REFERENCE_REMOVED = "source_reference_removed"

# The unapproved proposal statuses whose rows may be hard-deleted when they are
# solely derived from removed evidence (§8). Approved/executing/executed are
# never here: their history is preserved as a minimised tombstone instead.
_UNAPPROVED_DELETABLE_STATUSES: frozenset[str] = frozenset(
    {
        ProposalStatus.proposed,
        ProposalStatus.edited,
        ProposalStatus.rejected,
        ProposalStatus.expired,
    }
)

# The safe, content-free shape every minimised proposal tombstone collapses to.
# Everything with personal/provider content (payload, rationale, recipients,
# attendees, approved payloads, provider ids, source snippets) is cleared.
_TOMBSTONE_RATIONALE = "[minimised: source evidence deleted]"


@dataclass
class Counts:
    """Per-category counts plus disposition buckets. Serialisable to JSON for
    the durable operation row; never contains any record content."""

    values: dict[str, int] = field(default_factory=dict)

    def add(self, key: str, n: int = 1) -> None:
        if n:
            self.values[key] = self.values.get(key, 0) + n

    def to_json(self) -> dict[str, int]:
        return dict(sorted(self.values.items()))


def source_items_in_scope_stmt(
    user_id: uuid.UUID, *, source_account_id: uuid.UUID, snapshot_cutoff: datetime
) -> Select[tuple[SourceItem]]:
    """Imported-data scope: one account, imported at or before the snapshot.
    Provider data synced *after* the snapshot (created_at > cutoff) is never
    swept in (§7)."""
    return select(SourceItem).where(
        SourceItem.user_id == user_id,
        SourceItem.source_account_id == source_account_id,
        SourceItem.created_at <= snapshot_cutoff,
    )


async def _count(session: AsyncSession, stmt: Select[tuple[SourceItem]]) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    )


async def _external_ids_in_scope(
    session: AsyncSession, user_id: uuid.UUID, *, source_account_id: uuid.UUID, cutoff: datetime
) -> set[str]:
    rows = await session.execute(
        select(SourceItem.external_id).where(
            SourceItem.user_id == user_id,
            SourceItem.source_account_id == source_account_id,
            SourceItem.created_at <= cutoff,
        )
    )
    return {r[0] for r in rows.all()}


async def _surviving_external_ids(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    removed: set[str],
    source_account_id: uuid.UUID,
    cutoff: datetime,
) -> set[str]:
    """External ids that will still resolve to a SourceItem after the removed
    set is deleted: every SourceItem the user owns except the in-scope ones."""
    rows = await session.execute(
        select(SourceItem.external_id).where(SourceItem.user_id == user_id)
    )
    all_ids = {r[0] for r in rows.all()}
    return all_ids - removed


@dataclass
class ProposalDisposition:
    delete_ids: list[uuid.UUID] = field(default_factory=list)
    minimise_ids: list[uuid.UUID] = field(default_factory=list)
    preserve_uncertain_ids: list[uuid.UUID] = field(default_factory=list)
    recompute_ids: list[uuid.UUID] = field(default_factory=list)  # prune deleted refs, keep


async def classify_signals(
    session: AsyncSession, user_id: uuid.UUID, *, removed: set[str], surviving: set[str]
) -> tuple[list[uuid.UUID], list[tuple[uuid.UUID, list[str]]]]:
    """(fully-unsupported signal ids to delete, [(retained id, pruned refs)]).

    A signal is deleted only when *none* of its evidence refs survive; if any
    ref still resolves to a surviving SourceItem it is retained with the
    deleted refs pruned out (never keep a dangling reference to deleted
    content)."""
    rows = await session.execute(
        select(Signal.id, Signal.evidence_refs).where(Signal.user_id == user_id)
    )
    delete_ids: list[uuid.UUID] = []
    recompute: list[tuple[uuid.UUID, list[str]]] = []
    for signal_id, refs in rows.all():
        ref_set = set(refs or [])
        if not ref_set & removed:
            continue  # unaffected — no evidence in the removed set
        remaining = [r for r in (refs or []) if r in surviving]
        if remaining:
            recompute.append((signal_id, remaining))
        else:
            delete_ids.append(signal_id)
    return delete_ids, recompute


async def classify_proposals(
    session: AsyncSession, user_id: uuid.UUID, *, removed: set[str], surviving: set[str]
) -> ProposalDisposition:
    """Decide each affected proposal's fate (§8). Only proposals with at least
    one ref in the removed set are affected; the rest are untouched."""
    rows = await session.execute(
        select(
            ActionProposal.id,
            ActionProposal.source_refs,
            ActionProposal.status,
            ActionProposal.approved_at,
        ).where(ActionProposal.user_id == user_id)
    )
    disposition = ProposalDisposition()
    for proposal_id, refs, status, approved_at in rows.all():
        ref_set = set(refs or [])
        if not ref_set & removed:
            continue
        remaining = [r for r in (refs or []) if r in surviving]
        execution = (
            await session.execute(
                select(ActionExecution.outcome).where(ActionExecution.proposal_id == proposal_id)
            )
        ).scalar_one_or_none()

        if execution in (ExecutionOutcome.pending, ExecutionOutcome.uncertain):
            # Never delete; the proposal is minimised so the unresolved
            # external outcome stays explainable.
            disposition.preserve_uncertain_ids.append(proposal_id)
        elif execution in (ExecutionOutcome.succeeded, ExecutionOutcome.failed):
            disposition.minimise_ids.append(proposal_id)
        elif approved_at is not None:
            # Approved (with or without a terminal execution) — preserve a
            # minimised tombstone for approval history.
            disposition.minimise_ids.append(proposal_id)
        elif status in _UNAPPROVED_DELETABLE_STATUSES and not remaining:
            disposition.delete_ids.append(proposal_id)
        else:
            # Unapproved but mixed-source (some evidence survives): retain and
            # prune the deleted refs.
            disposition.recompute_ids.append(proposal_id)
    return disposition


def minimise_proposal(proposal: ActionProposal) -> None:
    """Collapse a proposal to a content-free tombstone in place (§8). Retains
    only what explains that an action happened: type, status, timestamps, ids.
    Clears every field that could carry personal or provider content."""
    proposal.rationale = _TOMBSTONE_RATIONALE
    proposal.payload_json = {}
    proposal.source_refs = []
    proposal.approved_payload_json = None
    proposal.approved_action_type = proposal.approved_action_type  # safe: a closed enum label
    proposal.rejection_reason = None


def minimise_execution(execution: ActionExecution) -> None:
    """Strip content from a retained execution tombstone (§8). Keeps outcome,
    mode, timestamps, ids and a safe error code; clears the executed payload."""
    execution.executed_payload_json = {}
    execution.result_json = {}


# --- imported-data preview (counts only, no mutation) -----------------------


@dataclass
class ImportedDataPlan:
    preview_counts: Counts  # what will be deleted, per category
    preserved_counts: Counts  # what will be preserved (with disposition reasons)
    warnings: list[str]


async def count_imported_data_plan(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    source_account_id: uuid.UUID,
    snapshot_cutoff: datetime,
) -> ImportedDataPlan:
    """Owner-scoped, mutation-free preview. Uses the exact scoping queries the
    worker uses, so preview counts equal what actually happens."""
    removed = await _external_ids_in_scope(
        session, user_id, source_account_id=source_account_id, cutoff=snapshot_cutoff
    )
    surviving = await _surviving_external_ids(
        session,
        user_id,
        removed=removed,
        source_account_id=source_account_id,
        cutoff=snapshot_cutoff,
    )
    preview = Counts()
    preserved = Counts()

    preview.add(CAT_SOURCE_ITEMS, len(removed))

    signal_deletes, signal_recompute = await classify_signals(
        session, user_id, removed=removed, surviving=surviving
    )
    preview.add(CAT_SIGNALS, len(signal_deletes))
    preserved.add(DISPOSITION_RECOMPUTED_SIGNALS, len(signal_recompute))

    disposition = await classify_proposals(session, user_id, removed=removed, surviving=surviving)
    preview.add(CAT_PROPOSALS, len(disposition.delete_ids))
    preserved.add(DISPOSITION_MINIMISED_HISTORY, len(disposition.minimise_ids))
    preserved.add(DISPOSITION_PRESERVED_PENDING_UNCERTAIN, len(disposition.preserve_uncertain_ids))
    preserved.add(DISPOSITION_SOURCE_REFERENCE_REMOVED, len(disposition.recompute_ids))

    warnings = [
        "This deletes only LifeFlow's imported copy — your Gmail and Google "
        "Calendar content is never touched.",
        "Actions you already approved or that ran are kept as content-free "
        "history; unresolved or pending outcomes are always preserved.",
    ]
    return ImportedDataPlan(preview_counts=preview, preserved_counts=preserved, warnings=warnings)


# --- imported-data execution (bounded, resumable, idempotent) ---------------

PHASE_DERIVED = "derived"
PHASE_SOURCES = "sources"
PHASE_DONE = "done"


async def run_derived_cleanup(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    source_account_id: uuid.UUID,
    snapshot_cutoff: datetime,
    deleted: Counts,
) -> None:
    """Apply every derived-data decision once, before any source item is
    deleted (so the removed/surviving sets are stable across a crash-resume).
    Idempotent: deleting an already-deleted signal is a no-op, and
    re-minimising an already-minimised proposal yields the identical tombstone
    (no duplication — §10)."""
    removed = await _external_ids_in_scope(
        session, user_id, source_account_id=source_account_id, cutoff=snapshot_cutoff
    )
    surviving = await _surviving_external_ids(
        session,
        user_id,
        removed=removed,
        source_account_id=source_account_id,
        cutoff=snapshot_cutoff,
    )

    await apply_derived_decisions(
        session, user_id, removed=removed, surviving=surviving, deleted=deleted
    )


async def apply_derived_decisions(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    removed: set[str],
    surviving: set[str],
    deleted: Counts,
) -> None:
    """Classify and apply every signal/proposal/execution decision for a
    `removed`/`surviving` evidence split. Shared verbatim by imported-data
    deletion (account-scoped removed set) and retention enforcement
    (age-scoped removed set), so the two can never diverge (§8, test #47).
    Idempotent: re-running re-minimises to the identical tombstone and skips
    already-deleted rows."""
    signal_deletes, signal_recompute = await classify_signals(
        session, user_id, removed=removed, surviving=surviving
    )
    for signal_id, remaining in signal_recompute:
        signal = await session.get(Signal, signal_id)
        if signal is not None:
            signal.evidence_refs = remaining
            deleted.add(DISPOSITION_SOURCE_REFERENCE_REMOVED)
    if signal_deletes:
        await session.execute(
            delete(Signal).where(Signal.user_id == user_id, Signal.id.in_(signal_deletes))
        )
        deleted.add(CAT_SIGNALS, len(signal_deletes))

    disposition = await classify_proposals(session, user_id, removed=removed, surviving=surviving)
    for proposal_id in disposition.minimise_ids + disposition.preserve_uncertain_ids:
        proposal = await session.get(ActionProposal, proposal_id)
        if proposal is None:
            continue
        minimise_proposal(proposal)
        execution = (
            await session.execute(
                select(ActionExecution).where(ActionExecution.proposal_id == proposal_id)
            )
        ).scalar_one_or_none()
        if execution is not None:
            minimise_execution(execution)
        if proposal_id in disposition.preserve_uncertain_ids:
            deleted.add(DISPOSITION_PRESERVED_PENDING_UNCERTAIN)
        else:
            deleted.add(DISPOSITION_MINIMISED_HISTORY)
    for proposal_id in disposition.recompute_ids:
        proposal = await session.get(ActionProposal, proposal_id)
        if proposal is not None:
            proposal.source_refs = [r for r in proposal.source_refs if r in surviving]
            deleted.add(DISPOSITION_SOURCE_REFERENCE_REMOVED)
    if disposition.delete_ids:
        # MemoryEvidence.source_proposal_id is ON DELETE SET NULL, so the safe
        # derived token survives with a nulled reference (never a dangling FK).
        await session.execute(
            delete(ActionProposal).where(
                ActionProposal.user_id == user_id,
                ActionProposal.id.in_(disposition.delete_ids),
            )
        )
        deleted.add(CAT_PROPOSALS, len(disposition.delete_ids))


async def delete_source_items_batch(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    source_account_id: uuid.UUID,
    snapshot_cutoff: datetime,
    limit: int,
) -> int:
    """Delete up to `limit` in-scope SourceItems. Returns how many were
    deleted; 0 means the phase is complete. Bounded so no single transaction
    is unbounded (§9)."""
    ids = (
        (
            await session.execute(
                select(SourceItem.id)
                .where(
                    SourceItem.user_id == user_id,
                    SourceItem.source_account_id == source_account_id,
                    SourceItem.created_at <= snapshot_cutoff,
                )
                .order_by(SourceItem.id)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not ids:
        return 0
    await session.execute(delete(SourceItem).where(SourceItem.id.in_(ids)))
    return len(ids)


async def count_source_items_remaining(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    source_account_id: uuid.UUID,
    snapshot_cutoff: datetime,
) -> int:
    return await _count(
        session,
        source_items_in_scope_stmt(
            user_id, source_account_id=source_account_id, snapshot_cutoff=snapshot_cutoff
        ),
    )


def hash_lines(lines: list[str]) -> str:
    """sha256 of newline-joined canonical lines. The output is a digest, so a
    fingerprint never exposes its inputs; inputs here are only our own record
    ids and disposition labels (never content or provider identifiers)."""
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


async def imported_data_disposition_lines(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    source_account_id: uuid.UUID,
    snapshot_cutoff: datetime,
) -> list[str]:
    """The canonical, content-free (id + disposition) lines that define the
    imported-data plan, for the confirmation-binding fingerprint. Uses the same
    classification the preview/worker use, so a material disposition change
    (proposed→approved, execution created, mixed→unsupported, dependency
    added/removed) changes the fingerprint, while a later out-of-snapshot
    SourceItem that alters no listed disposition does not."""
    removed = await _external_ids_in_scope(
        session, user_id, source_account_id=source_account_id, cutoff=snapshot_cutoff
    )
    surviving = await _surviving_external_ids(
        session,
        user_id,
        removed=removed,
        source_account_id=source_account_id,
        cutoff=snapshot_cutoff,
    )
    src_rows = await session.execute(
        select(SourceItem.id).where(
            SourceItem.user_id == user_id,
            SourceItem.source_account_id == source_account_id,
            SourceItem.created_at <= snapshot_cutoff,
        )
    )
    lines = [f"src:{sid}:delete" for sid in sorted(str(r[0]) for r in src_rows.all())]

    signal_deletes, signal_recompute = await classify_signals(
        session, user_id, removed=removed, surviving=surviving
    )
    lines += [f"sig:{sid}:delete" for sid in sorted(str(s) for s in signal_deletes)]
    for signal_id, remaining in sorted((str(s), r) for s, r in signal_recompute):
        # The remaining refs are provider ids: fed only into a nested digest,
        # never persisted or emitted raw.
        lines.append(f"sig:{signal_id}:recompute:{hash_lines(sorted(remaining))}")

    disposition = await classify_proposals(session, user_id, removed=removed, surviving=surviving)
    lines += [f"prop:{pid}:delete" for pid in sorted(str(p) for p in disposition.delete_ids)]
    lines += [f"prop:{pid}:minimise" for pid in sorted(str(p) for p in disposition.minimise_ids)]
    lines += [
        f"prop:{pid}:preserve" for pid in sorted(str(p) for p in disposition.preserve_uncertain_ids)
    ]
    lines += [f"prop:{pid}:recompute" for pid in sorted(str(p) for p in disposition.recompute_ids)]
    return lines


def unsupported_memory_evidence_stmt(user_id: uuid.UUID) -> Select[tuple[uuid.UUID]]:
    """MemoryEvidence rows whose source proposal was deleted (ref is now NULL).
    Their safe derived token is retained; recompute decides the parent item's
    fate (never deletes a confirmed explicit preference)."""
    return select(MemoryEvidence.id).where(
        MemoryEvidence.user_id == user_id, MemoryEvidence.source_proposal_id.is_(None)
    )


__all__ = [
    "CAT_EXECUTIONS",
    "CAT_MEMORY_EVIDENCE",
    "CAT_PROPOSALS",
    "CAT_SIGNALS",
    "CAT_SOURCE_ITEMS",
    "DISPOSITION_MINIMISED_HISTORY",
    "DISPOSITION_PRESERVED_PENDING_UNCERTAIN",
    "DISPOSITION_RECOMPUTED_SIGNALS",
    "DISPOSITION_SOURCE_REFERENCE_REMOVED",
    "PHASE_DERIVED",
    "PHASE_DONE",
    "PHASE_SOURCES",
    "Counts",
    "ImportedDataPlan",
    "ProposalDisposition",
    "apply_derived_decisions",
    "classify_proposals",
    "classify_signals",
    "count_imported_data_plan",
    "count_source_items_remaining",
    "delete_source_items_batch",
    "hash_lines",
    "imported_data_disposition_lines",
    "minimise_execution",
    "minimise_proposal",
    "run_derived_cleanup",
    "source_items_in_scope_stmt",
]
