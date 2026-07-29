"""Account deletion — anonymise-and-minimise (Stage 9 Delivery Phase 2,
ADR 0005 D61).

Deleting a LifeFlow account keeps a terminal, anonymised `User` row (so the
content-free audit/execution tombstones `AuditEvent.user_id` references under
ON DELETE CASCADE survive), erases every direct identity field, assigns a
random non-reversible `deletion_subject_id`, revokes provider access
best-effort while always clearing local credentials, deletes personal product
data, and minimises the retained proposal/execution/audit tombstones needed for
uncertain-outcome reconciliation. Gmail and Calendar provider content is never
touched.

A bounded phase machine driven by `resume_cursor_json["phase"]`, uniform with
the imported-data driver so the worker loop treats every operation type the
same way. Idempotent across a crash: each phase re-runs safely and an
already-anonymised account short-circuits to done.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.deletion_planner import (
    CAT_EXECUTIONS,
    CAT_MEMORY_EVIDENCE,
    CAT_PROPOSALS,
    CAT_SIGNALS,
    CAT_SOURCE_ITEMS,
    Counts,
    minimise_execution,
    minimise_proposal,
)
from lifeflow_api.models import (
    ActionExecution,
    ActionProposal,
    AuditEvent,
    Brief,
    ConnectedAccount,
    DataDeletionOperation,
    MemoryEvidence,
    MemoryItem,
    Preference,
    ScheduledBriefRun,
    Signal,
    SourceItem,
    User,
    UserAccountState,
)

# Best-effort provider revoke: given the connected account, revoke remote
# access (the callable decrypts and calls the provider). None in demo/test (no
# real Google); a failure never blocks local erasure, and no token, provider
# response, or raw exception ever crosses this boundary into logs/audits/state.
ProviderRevoker = Callable[["ConnectedAccount"], Awaitable[None]]
CAT_PROVIDER_REVOCATIONS = "provider_revocations"

CAT_CONNECTED_ACCOUNTS = "connected_accounts"
CAT_BRIEFS = "briefs"
CAT_SCHEDULED_RUNS = "scheduled_brief_runs"
CAT_PREFERENCES = "preferences"
CAT_MEMORY_ITEMS = "memory_items"
CAT_AUDIT_TOMBSTONES = "audit_events"

DISPOSITION_MINIMISED_PROPOSALS = "minimised_proposal_tombstones"
DISPOSITION_RETAINED_EXECUTIONS = "retained_execution_tombstones"
DISPOSITION_RETAINED_AUDIT = "retained_audit_tombstones"

_PHASE_CREDENTIALS = "credentials"
_PHASE_PRODUCT = "product"
_PHASE_MINIMISE = "minimise"
_PHASE_FINALISE = "finalise"
_PHASE_DONE = "done"


async def _count_owned(session: AsyncSession, model: Any, user_id: uuid.UUID) -> int:
    return int(
        (
            await session.execute(
                select(func.count()).select_from(model).where(model.user_id == user_id)
            )
        ).scalar_one()
    )


async def _count_executions(session: AsyncSession, user_id: uuid.UUID) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(ActionExecution)
                .join(ActionProposal, ActionProposal.id == ActionExecution.proposal_id)
                .where(ActionProposal.user_id == user_id)
            )
        ).scalar_one()
    )


@dataclass
class AccountDeletionPlan:
    preview_counts: Counts  # records deleted
    preserved_counts: Counts  # records minimised and retained as tombstones
    warnings: list[str]


async def count_account_deletion_plan(
    session: AsyncSession, user_id: uuid.UUID
) -> AccountDeletionPlan:
    """Mutation-free, owner-scoped preview. Proposals with an execution are
    minimised and retained (reconciliation history); proposals with none are
    deleted. Executions and audit events are always retained as content-free
    tombstones."""
    proposals_with_exec = int(
        (
            await session.execute(
                select(func.count(func.distinct(ActionProposal.id)))
                .select_from(ActionProposal)
                .join(ActionExecution, ActionExecution.proposal_id == ActionProposal.id)
                .where(ActionProposal.user_id == user_id)
            )
        ).scalar_one()
    )
    total_proposals = await _count_owned(session, ActionProposal, user_id)
    proposals_deleted = total_proposals - proposals_with_exec

    preview = Counts()
    preview.add(CAT_SOURCE_ITEMS, await _count_owned(session, SourceItem, user_id))
    preview.add(CAT_SIGNALS, await _count_owned(session, Signal, user_id))
    preview.add(CAT_BRIEFS, await _count_owned(session, Brief, user_id))
    preview.add(CAT_SCHEDULED_RUNS, await _count_owned(session, ScheduledBriefRun, user_id))
    preview.add(CAT_PREFERENCES, await _count_owned(session, Preference, user_id))
    preview.add(CAT_MEMORY_ITEMS, await _count_owned(session, MemoryItem, user_id))
    preview.add(CAT_MEMORY_EVIDENCE, await _count_owned(session, MemoryEvidence, user_id))
    preview.add(CAT_CONNECTED_ACCOUNTS, await _count_owned(session, ConnectedAccount, user_id))
    preview.add(CAT_PROPOSALS, proposals_deleted)

    preserved = Counts()
    preserved.add(DISPOSITION_MINIMISED_PROPOSALS, proposals_with_exec)
    preserved.add(DISPOSITION_RETAINED_EXECUTIONS, await _count_executions(session, user_id))
    preserved.add(DISPOSITION_RETAINED_AUDIT, await _count_owned(session, AuditEvent, user_id))

    warnings = [
        "Your LifeFlow sign-in will stop working and this cannot be undone.",
        "Your Gmail and Google Calendar content is never deleted.",
        "Content-free trust records may remain for integrity and to reconcile "
        "any unresolved external action.",
    ]
    return AccountDeletionPlan(
        preview_counts=preview, preserved_counts=preserved, warnings=warnings
    )


async def account_disposition_lines(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Canonical, content-free (id + disposition) lines for the account-deletion
    plan's confirmation fingerprint. Captures the retention-sensitive
    dispositions: each proposal is `minimise` (has an execution → retained
    tombstone) or `delete`, and each execution is a retained tombstone — so a
    pending/uncertain execution created after preview changes the fingerprint."""
    proposal_rows = await session.execute(
        select(ActionProposal.id).where(ActionProposal.user_id == user_id)
    )
    lines: list[str] = []
    for (proposal_id,) in sorted(proposal_rows.all(), key=lambda row: str(row[0])):
        has_exec = (
            await session.execute(
                select(ActionExecution.id).where(ActionExecution.proposal_id == proposal_id)
            )
        ).first() is not None
        lines.append(f"prop:{proposal_id}:{'minimise' if has_exec else 'delete'}")
    exec_rows = await session.execute(
        select(ActionExecution.id)
        .join(ActionProposal, ActionProposal.id == ActionExecution.proposal_id)
        .where(ActionProposal.user_id == user_id)
    )
    lines += [f"exec:{eid}:minimise" for eid in sorted(str(r[0]) for r in exec_rows.all())]
    return lines


@dataclass
class AccountDeletionStep:
    done: bool
    progressed: bool
    provider_revoke_failed: bool = False


async def run_account_deletion_step(
    session: AsyncSession,
    operation: DataDeletionOperation,
    *,
    now: datetime,
    batch_size: int,
    revoker: ProviderRevoker | None = None,
) -> AccountDeletionStep:
    """One bounded phase step. The worker calls this repeatedly (committing
    between calls) until `done`. `deleted_counts_json` accumulates progress."""
    user = await session.get(User, operation.user_id)
    if user is None or user.account_state == UserAccountState.deleted:
        return AccountDeletionStep(done=True, progressed=False)

    cursor = dict(operation.resume_cursor_json or {})
    phase = cursor.get("phase", _PHASE_CREDENTIALS)
    deleted = Counts(dict(operation.deleted_counts_json or {}))
    revoke_failed = bool(cursor.get("provider_revoke_failed", False))

    if phase == _PHASE_CREDENTIALS:
        accounts = (
            (
                await session.execute(
                    select(ConnectedAccount).where(ConnectedAccount.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )
        for account in accounts:
            if revoker is not None and account.encrypted_refresh_token is not None:
                try:
                    await revoker(account)
                    deleted.add(CAT_PROVIDER_REVOCATIONS)
                except Exception:
                    # Never let a provider failure block local erasure (§12); the
                    # exception is swallowed (not logged) so no provider response
                    # or raw error text leaks.
                    revoke_failed = True
            account.encrypted_access_token = None
            account.encrypted_refresh_token = None
            account.sync_cursors = {}
        await session.execute(delete(ConnectedAccount).where(ConnectedAccount.user_id == user.id))
        deleted.add(CAT_CONNECTED_ACCOUNTS, len(accounts))
        cursor = {"phase": _PHASE_PRODUCT, "provider_revoke_failed": revoke_failed}
        operation.resume_cursor_json = cursor
        operation.deleted_counts_json = deleted.to_json()
        return AccountDeletionStep(
            done=False, progressed=True, provider_revoke_failed=revoke_failed
        )

    if phase == _PHASE_PRODUCT:
        # High-volume source items in bounded batches; the rest (per-user
        # modest) cleared once the source items are gone.
        ids = (
            (
                await session.execute(
                    select(SourceItem.id)
                    .where(SourceItem.user_id == user.id)
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
            return AccountDeletionStep(
                done=False, progressed=True, provider_revoke_failed=revoke_failed
            )
        # Source items exhausted — clear the remaining personal product data.
        for model, key in (
            (Signal, CAT_SIGNALS),
            (Brief, CAT_BRIEFS),
            (ScheduledBriefRun, CAT_SCHEDULED_RUNS),
            (Preference, CAT_PREFERENCES),
            (MemoryEvidence, CAT_MEMORY_EVIDENCE),
            (MemoryItem, CAT_MEMORY_ITEMS),
        ):
            n = await _count_owned(session, model, user.id)
            if n:
                await session.execute(delete(model).where(model.user_id == user.id))
                deleted.add(key, n)
        cursor = {"phase": _PHASE_MINIMISE, "provider_revoke_failed": revoke_failed}
        operation.resume_cursor_json = cursor
        operation.deleted_counts_json = deleted.to_json()
        return AccountDeletionStep(
            done=False, progressed=True, provider_revoke_failed=revoke_failed
        )

    if phase == _PHASE_MINIMISE:
        # Minimise proposals that have an execution (retain the tombstone);
        # delete proposals with no execution. Executions are always retained,
        # minimised — never delete a pending/uncertain outcome (§8/§12).
        proposals = (
            (await session.execute(select(ActionProposal).where(ActionProposal.user_id == user.id)))
            .scalars()
            .all()
        )
        delete_ids: list[uuid.UUID] = []
        for proposal in proposals:
            execution = (
                await session.execute(
                    select(ActionExecution).where(ActionExecution.proposal_id == proposal.id)
                )
            ).scalar_one_or_none()
            if execution is None:
                delete_ids.append(proposal.id)
            else:
                minimise_proposal(proposal)
                minimise_execution(execution)
                deleted.add(DISPOSITION_MINIMISED_PROPOSALS)
                deleted.add(CAT_EXECUTIONS)
        if delete_ids:
            await session.execute(delete(ActionProposal).where(ActionProposal.id.in_(delete_ids)))
            deleted.add(CAT_PROPOSALS, len(delete_ids))
        cursor = {"phase": _PHASE_FINALISE, "provider_revoke_failed": revoke_failed}
        operation.resume_cursor_json = cursor
        operation.deleted_counts_json = deleted.to_json()
        return AccountDeletionStep(
            done=False, progressed=True, provider_revoke_failed=revoke_failed
        )

    if phase == _PHASE_FINALISE:
        # Anonymise the terminal user row. Idempotent: assign the random
        # subject id only once, never regenerate it on a resume.
        if user.deletion_subject_id is None:
            user.deletion_subject_id = uuid.uuid4()
        user.email = f"deleted+{user.deletion_subject_id}@deleted.invalid"
        user.display_name = "Deleted account"
        user.google_subject = None
        user.timezone = "UTC"
        user.locale = "en-GB"
        user.account_state = UserAccountState.deleted
        user.deleted_at = now
        cursor = {"phase": _PHASE_DONE, "provider_revoke_failed": revoke_failed}
        operation.resume_cursor_json = cursor
        operation.deleted_counts_json = deleted.to_json()
        return AccountDeletionStep(done=True, progressed=True, provider_revoke_failed=revoke_failed)

    return AccountDeletionStep(done=True, progressed=False, provider_revoke_failed=revoke_failed)


__all__ = [
    "CAT_AUDIT_TOMBSTONES",
    "CAT_BRIEFS",
    "CAT_CONNECTED_ACCOUNTS",
    "CAT_MEMORY_ITEMS",
    "CAT_PREFERENCES",
    "CAT_SCHEDULED_RUNS",
    "DISPOSITION_MINIMISED_PROPOSALS",
    "DISPOSITION_RETAINED_AUDIT",
    "DISPOSITION_RETAINED_EXECUTIONS",
    "AccountDeletionPlan",
    "AccountDeletionStep",
    "ProviderRevoker",
    "account_disposition_lines",
    "count_account_deletion_plan",
    "run_account_deletion_step",
]
