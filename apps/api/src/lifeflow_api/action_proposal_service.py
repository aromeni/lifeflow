"""Stage 6 proposal lifecycle: generation, approval, and simulated execution."""

import hashlib
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.action_executors import (
    ExecutorRegistry,
    FinalExecutionError,
    SimulatedExecutorRegistry,
    UnavailableGoogleExecutorRegistry,
)
from lifeflow_api.action_payloads import (
    TypedActionPayload,
    action_payload_hash,
    approval_binding_hash,
    canonical_payload,
    parse_action_payload,
)
from lifeflow_api.action_policy import (
    ActionPolicyEngine,
    PolicyViolationError,
)
from lifeflow_api.audit import record_audit_event
from lifeflow_api.execution_context import (
    GOOGLE_PROVIDER,
    approved_execution_authorization,
    execution_context_hash,
)
from lifeflow_api.models import (
    ActionExecution,
    ActionProposal,
    ActionType,
    Brief,
    ExecutionMode,
    ExecutionOutcome,
    ProposalStatus,
    Signal,
    SourceItem,
)
from lifeflow_api.proposal_composition import (
    PROPOSAL_COMPOSER_VERSION,
    ProposalCandidate,
    candidate_payload_json,
    compose_proposal_candidates,
)
from lifeflow_api.repositories import (
    ActionExecutionRepository,
    ActionProposalRepository,
    ConnectedAccountRepository,
    SourceItemRepository,
)

NowFactory = Callable[[], datetime]
PostCommitHook = Callable[[], Coroutine[Any, Any, None]]

# A `pending` execution attempt older than this with no `completed_at` is
# treated as `uncertain` on next read (ADR 0003 D16) — comfortably above the
# bounded HTTP timeout any real executor call uses, so this only fires when
# something genuinely lost track of the attempt (crash, killed worker).
STALE_PENDING_AGE = timedelta(seconds=120)

# Statuses in which a proposal still occupies the one active slot allowed
# per action type per generation pass (Stage 7 sandbox finding). Anything
# else — rejected, executed, failed, expired, or a dead-ended `executing`
# whose execution outcome is uncertain — is terminal for generation
# purposes: it stays immutable, but a fresh, distinct signal of the same
# action type must still be able to produce its own new proposal.
_ACTIVE_PROPOSAL_STATUSES = frozenset(
    {ProposalStatus.proposed, ProposalStatus.edited, ProposalStatus.approved}
)


async def _default_post_commit_hook() -> None:
    """No-op in production. Overridable only via the `post_commit_hook`
    constructor argument (Stage 7 focused remediation) so tests can build a
    deterministic barrier around the exact post-durability-commit,
    pre-token-acquisition window the TOCTOU fix closes — no production code
    path ever sets this to anything else."""
    return None


class ProposalConflictError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ProposalGenerationSummary:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    preserved: int = 0
    skipped: int = 0


def effective_execution_status(execution: ActionExecution, *, now: datetime) -> str:
    """The user-facing status: the persisted outcome, except a `pending`
    attempt older than STALE_PENDING_AGE reads as `uncertain` even before
    anything has written that back (ADR 0003 D16)."""
    if (
        execution.outcome == ExecutionOutcome.pending
        and now - execution.started_at > STALE_PENDING_AGE
    ):
        return ExecutionOutcome.uncertain
    return execution.outcome


class ActionProposalService:
    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        policy: ActionPolicyEngine | None = None,
        executors: ExecutorRegistry | None = None,
        google_executors: ExecutorRegistry | None = None,
        now_factory: NowFactory | None = None,
        post_commit_hook: PostCommitHook | None = None,
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._proposals = ActionProposalRepository(session, user_id)
        self._executions = ActionExecutionRepository(session, user_id)
        self._accounts = ConnectedAccountRepository(session, user_id)
        self._sources = SourceItemRepository(session, user_id)
        self._policy = policy or ActionPolicyEngine()
        self._executors = executors or SimulatedExecutorRegistry()
        # None unless the caller wired real Google integration for this
        # request (independent-review blocker #1/#2) — `execute()` only ever
        # reaches for this when `resolve_execution_mode` says `real`, and
        # raises a controlled error rather than silently simulating if this
        # is still None at that point.
        self._google_executors = google_executors
        self._now = now_factory or (lambda: datetime.now(UTC))
        # Test-only seam (Stage 7 focused remediation): fires exactly once,
        # immediately after the durable pending-attempt commit and before
        # any executor is invoked. Always a no-op in production — nothing
        # outside the race-test suite ever passes a real hook.
        self._post_commit_hook = post_commit_hook or _default_post_commit_hook

    def _audit(
        self,
        proposal: ActionProposal,
        event_type: str,
        *,
        actor: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        record_audit_event(
            self._session,
            user_id=self._user_id,
            actor=actor,
            event_type=event_type,
            entity_type="action_proposal",
            entity_id=str(proposal.id),
            metadata=metadata,
        )

    async def _evidence_sources(self, proposal: ActionProposal) -> list[SourceItem]:
        return await self._sources.list_by_external_ids(list(proposal.source_refs))

    def _mark_expired(self, proposal: ActionProposal, *, actor: str) -> None:
        proposal.status = ProposalStatus.expired
        self._audit(
            proposal,
            "proposal.expired",
            actor=actor,
            metadata={
                "action_type": proposal.action_type,
                "version": proposal.version,
            },
        )

    def _expire_if_due(self, proposal: ActionProposal, *, now: datetime, actor: str) -> bool:
        if (
            proposal.status
            in {
                ProposalStatus.proposed,
                ProposalStatus.edited,
                ProposalStatus.approved,
            }
            and proposal.expires_at <= now
        ):
            self._mark_expired(proposal, actor=actor)
            return True
        return False

    async def expire_due(self) -> int:
        now = self._now()
        due = await self._proposals.list_due_for_expiry(now)
        for proposal in due:
            self._mark_expired(proposal, actor="system:proposal")
        if due:
            await self._session.flush()
        return len(due)

    async def generate_from_brief(
        self,
        *,
        brief: Brief,
        signals: list[Signal],
        sources: list[SourceItem],
        timezone: str,
        reference: datetime,
        preferred_signoff: str | None = None,
    ) -> ProposalGenerationSummary:
        """Change-aware proposal generation with stable origin uniqueness.

        At most one *active* proposal (`proposed`, `edited`, or `approved`)
        is created or reused per action type per pass — matching the
        product's one-active-proposal-per-type policy. A candidate whose
        origin already maps to a proposal in a terminal (`rejected`,
        `executed`, `failed`, `expired`) or dead-ended (`executing`, which is
        never auto-retried once an execution outcome is uncertain) state
        never blocks generation: that proposal is left untouched and
        immutable, and this walks to the next-ranked eligible candidate of
        the same action type — a genuinely new, distinct signal must be able
        to produce a fresh proposal even while an older, unrelated one of
        the same type sits in one of those states (Stage 7 sandbox finding:
        a second real email produced no proposal because an older, terminal
        Gmail-draft proposal's signal always outranked it and no candidate
        was ever composed for the newer signal — fixed by no longer
        stopping at the first ranked candidate)."""

        accounts = await self._accounts.list()
        composed = compose_proposal_candidates(
            signals,
            sources,
            reference=reference,
            timezone=timezone,
            # The demo "(proposed)" placeholder convention must never fire
            # for a real synced Google event (ADR 0003 D41) — composition
            # needs to know which accounts are Google to enforce that.
            google_account_ids=frozenset(
                account.id for account in accounts if account.provider == GOOGLE_PROVIDER
            ),
            # The user's confirmed explicit sign-off, if any (ADR 0004 D57).
            # Composition-only: never read by the policy engine or executors.
            preferred_signoff=preferred_signoff,
        )
        if composed.skipped:
            # Safe by construction: SkippedCandidate carries only the closed
            # action type and a fixed reason code — no source content.
            record_audit_event(
                self._session,
                user_id=self._user_id,
                actor="system:proposal",
                event_type="proposal.candidates_skipped",
                entity_type="action_proposal",
                entity_id="-",
                metadata={
                    "skipped": len(composed.skipped),
                    "action_types": sorted({str(s.action_type) for s in composed.skipped}),
                    "reason_codes": sorted({s.reason_code for s in composed.skipped}),
                },
            )
        created = updated = unchanged = preserved = 0
        ranked_by_type: dict[ActionType, list[ProposalCandidate]] = {}
        for candidate in composed.candidates:
            ranked_by_type.setdefault(candidate.action_type, []).append(candidate)

        for ranked_candidates in ranked_by_type.values():
            for candidate in ranked_candidates:
                existing = await self._proposals.get_by_origin(
                    candidate.origin_fingerprint, for_update=True
                )
                payload_json = candidate_payload_json(candidate)
                payload_hash = action_payload_hash(candidate.action_type, payload_json)
                if existing is None:
                    proposal = ActionProposal(
                        user_id=self._user_id,
                        origin_brief_id=brief.id,
                        origin_fingerprint=candidate.origin_fingerprint,
                        action_type=candidate.action_type,
                        rationale=candidate.rationale,
                        source_refs=list(candidate.source_refs),
                        payload_json=payload_json,
                        payload_hash=payload_hash,
                        version=1,
                        risk_level=candidate.risk_level,
                        confidence=candidate.confidence,
                        status=ProposalStatus.proposed,
                        expires_at=candidate.expires_at,
                    )
                    try:
                        # Savepoint: a concurrent request may have inserted
                        # this origin after our locked read returned nothing.
                        # The unique constraint stays authoritative; the
                        # loser falls through to the change-aware path
                        # against the winner.
                        async with self._session.begin_nested():
                            self._proposals.add(proposal)
                            await self._session.flush()
                    except IntegrityError:
                        existing = await self._proposals.get_by_origin(
                            candidate.origin_fingerprint, for_update=True
                        )
                        if existing is None:  # pragma: no cover — constraint implies a winner
                            raise
                    else:
                        self._audit(
                            proposal,
                            "proposal.created",
                            actor="system:proposal",
                            metadata={
                                "action_type": str(candidate.action_type),
                                "risk_level": str(candidate.risk_level),
                                "version": 1,
                                "composer_version": PROPOSAL_COMPOSER_VERSION,
                                "source_count": len(candidate.source_refs),
                            },
                        )
                        created += 1
                        # The one active slot for this action type is now
                        # filled by a brand-new proposal — stop scanning
                        # further ranked candidates of the same type.
                        break

                assert existing is not None  # noqa: S101 — set above or by IntegrityError recovery

                if self._expire_if_due(existing, now=reference, actor="system:proposal"):
                    # Just became terminal: frees the slot for this type.
                    preserved += 1
                    continue
                if existing.status not in _ACTIVE_PROPOSAL_STATUSES:
                    # Rejected, executed, failed, or a dead-ended `executing`
                    # (uncertain execution outcome, never auto-retried):
                    # immutable, and does not occupy the active slot — try
                    # the next-ranked candidate of the same action type.
                    preserved += 1
                    continue
                if (
                    existing.status != ProposalStatus.proposed
                    or existing.user_edited_at is not None
                ):
                    # Edited or approved by the user: preserve as-is, but
                    # this still occupies the one active slot for this type.
                    preserved += 1
                    break

                changed = any(
                    (
                        existing.action_type != candidate.action_type,
                        existing.rationale != candidate.rationale,
                        existing.source_refs != list(candidate.source_refs),
                        existing.payload_json != payload_json,
                        existing.payload_hash != payload_hash,
                        existing.risk_level != candidate.risk_level,
                        existing.confidence != candidate.confidence,
                    )
                )
                if not changed:
                    unchanged += 1
                    break

                existing.action_type = candidate.action_type
                existing.rationale = candidate.rationale
                existing.source_refs = list(candidate.source_refs)
                existing.payload_json = payload_json
                existing.payload_hash = payload_hash
                existing.risk_level = candidate.risk_level
                existing.confidence = candidate.confidence
                existing.expires_at = min(existing.expires_at, candidate.expires_at)
                existing.version += 1
                self._audit(
                    existing,
                    "proposal.updated",
                    actor="system:proposal",
                    metadata={
                        "action_type": existing.action_type,
                        "version": existing.version,
                        "composer_version": PROPOSAL_COMPOSER_VERSION,
                    },
                )
                updated += 1
                break

        await self._session.flush()
        return ProposalGenerationSummary(
            created=created,
            updated=updated,
            unchanged=unchanged,
            preserved=preserved,
            skipped=len(composed.skipped),
        )

    @staticmethod
    def _require_version_and_type(
        proposal: ActionProposal,
        *,
        expected_version: int,
        action_type: ActionType,
    ) -> None:
        if proposal.version != expected_version:
            raise ProposalConflictError(
                "stale_version", "The proposal changed; reload the current version."
            )
        if ActionType(proposal.action_type) != action_type:
            raise ProposalConflictError(
                "stale_action_type", "The proposal action type changed; reload it."
            )

    @staticmethod
    def _clear_approval(proposal: ActionProposal) -> None:
        proposal.approved_action_type = None
        proposal.approved_payload_json = None
        proposal.approved_payload_hash = None
        proposal.approved_binding_hash = None
        proposal.approved_version = None
        proposal.approved_at = None
        proposal.approved_execution_mode = None
        proposal.approved_provider = None
        proposal.approved_connected_account_id = None
        proposal.approved_authorisation_revision = None
        proposal.approved_required_scope = None
        proposal.approved_source_account_id = None
        proposal.approved_execution_context_hash = None

    async def edit(
        self,
        proposal_id: uuid.UUID,
        *,
        expected_version: int,
        action_type: ActionType,
        payload: dict[str, Any] | TypedActionPayload,
    ) -> ActionProposal:
        proposal = await self._proposals.get(proposal_id, for_update=True)
        if proposal is None:
            raise ProposalConflictError("not_found", "Action proposal not found.")
        self._require_version_and_type(
            proposal, expected_version=expected_version, action_type=action_type
        )
        if proposal.status not in {
            ProposalStatus.proposed,
            ProposalStatus.edited,
            ProposalStatus.approved,
        }:
            raise ProposalConflictError("invalid_transition", "This proposal cannot be edited.")
        now = self._now()
        if self._expire_if_due(proposal, now=now, actor=f"user:{self._user_id}"):
            await self._session.flush()
            raise ProposalConflictError("proposal_expired", "The proposal has expired.")

        typed_payload = parse_action_payload(action_type, payload)
        payload_json = canonical_payload(action_type, typed_payload)
        was_approved = proposal.status == ProposalStatus.approved
        if was_approved:
            self._audit(
                proposal,
                "approval.invalidated",
                actor=f"user:{self._user_id}",
                metadata={
                    "action_type": proposal.action_type,
                    "invalidated_version": proposal.approved_version,
                },
            )
        self._clear_approval(proposal)
        proposal.payload_json = payload_json
        proposal.payload_hash = action_payload_hash(action_type, typed_payload)
        proposal.version += 1
        proposal.status = ProposalStatus.edited
        proposal.user_edited_at = now
        self._audit(
            proposal,
            "proposal.edited",
            actor=f"user:{self._user_id}",
            metadata={
                "action_type": proposal.action_type,
                "version": proposal.version,
                "approval_invalidated": was_approved,
            },
        )
        await self._session.flush()
        return proposal

    async def approve(
        self,
        proposal_id: uuid.UUID,
        *,
        expected_version: int,
        action_type: ActionType,
        displayed_payload_hash: str,
        displayed_execution_context_hash: str,
    ) -> ActionProposal:
        proposal = await self._proposals.get(proposal_id, for_update=True)
        if proposal is None:
            raise ProposalConflictError("not_found", "Action proposal not found.")
        now = self._now()
        if self._expire_if_due(proposal, now=now, actor=f"user:{self._user_id}"):
            self._audit(
                proposal,
                "approval.denied",
                actor=f"user:{self._user_id}",
                metadata={
                    "action_type": proposal.action_type,
                    "reason_code": "proposal_expired",
                    "version": proposal.version,
                },
            )
            await self._session.flush()
            raise ProposalConflictError("proposal_expired", "The proposal has expired.")
        accounts = await self._accounts.list()
        evidence_sources = await self._evidence_sources(proposal)
        try:
            context = self._policy.validate_approval(
                proposal,
                user_id=self._user_id,
                accounts=accounts,
                evidence_sources=evidence_sources,
                now=now,
                displayed_action_type=action_type,
                displayed_payload_hash=displayed_payload_hash,
                displayed_version=expected_version,
                displayed_execution_context_hash=displayed_execution_context_hash,
            )
        except PolicyViolationError as exc:
            self._audit(
                proposal,
                "approval.denied",
                actor=f"user:{self._user_id}",
                metadata={
                    "action_type": proposal.action_type,
                    "reason_code": exc.code,
                    "version": proposal.version,
                },
            )
            await self._session.flush()
            raise ProposalConflictError(exc.code, exc.message) from exc

        payload = parse_action_payload(action_type, proposal.payload_json)
        context_hash = execution_context_hash(context)
        proposal.approved_action_type = action_type
        proposal.approved_payload_json = canonical_payload(action_type, payload)
        proposal.approved_payload_hash = proposal.payload_hash
        proposal.approved_execution_mode = context.mode
        proposal.approved_provider = context.provider
        proposal.approved_connected_account_id = context.connected_account_id
        proposal.approved_authorisation_revision = context.account_authorisation_revision
        proposal.approved_required_scope = context.required_scope
        proposal.approved_source_account_id = context.source_account_id
        proposal.approved_execution_context_hash = context_hash
        proposal.approved_binding_hash = approval_binding_hash(
            action_type, payload, proposal.version, context_hash
        )
        proposal.approved_version = proposal.version
        proposal.approved_at = now
        proposal.status = ProposalStatus.approved
        self._audit(
            proposal,
            "proposal.approved",
            actor=f"user:{self._user_id}",
            metadata={
                "action_type": proposal.action_type,
                "version": proposal.version,
                "payload_hash": proposal.payload_hash,
                "execution_mode": context.mode,
                "provider": context.provider,
                "execution_context_hash": context_hash,
            },
        )
        await self._session.flush()
        return proposal

    async def reject(
        self,
        proposal_id: uuid.UUID,
        *,
        expected_version: int,
        reason: str | None,
    ) -> ActionProposal:
        proposal = await self._proposals.get(proposal_id, for_update=True)
        if proposal is None:
            raise ProposalConflictError("not_found", "Action proposal not found.")
        if proposal.version != expected_version:
            raise ProposalConflictError(
                "stale_version", "The proposal changed; reload the current version."
            )
        if proposal.status not in {
            ProposalStatus.proposed,
            ProposalStatus.edited,
            ProposalStatus.approved,
        }:
            raise ProposalConflictError("invalid_transition", "This proposal cannot be rejected.")
        now = self._now()
        if self._expire_if_due(proposal, now=now, actor=f"user:{self._user_id}"):
            await self._session.flush()
            raise ProposalConflictError("proposal_expired", "The proposal has expired.")
        if proposal.status == ProposalStatus.approved:
            self._audit(
                proposal,
                "approval.invalidated",
                actor=f"user:{self._user_id}",
                metadata={
                    "action_type": proposal.action_type,
                    "invalidated_version": proposal.approved_version,
                },
            )
            self._clear_approval(proposal)
        proposal.status = ProposalStatus.rejected
        proposal.rejected_at = now
        proposal.rejection_reason = reason.strip() if reason else None
        self._audit(
            proposal,
            "proposal.rejected",
            actor=f"user:{self._user_id}",
            metadata={
                "action_type": proposal.action_type,
                "version": proposal.version,
                "reason_recorded": bool(proposal.rejection_reason),
            },
        )
        await self._session.flush()
        return proposal

    async def execute(self, proposal_id: uuid.UUID) -> tuple[ActionProposal, ActionExecution]:
        proposal = await self._proposals.get(proposal_id, for_update=True)
        if proposal is None:
            raise ProposalConflictError("not_found", "Action proposal not found.")
        existing = await self._executions.get_by_proposal(proposal.id)
        if existing is not None:
            now = self._now()
            if (
                existing.outcome == ExecutionOutcome.pending
                and now - existing.started_at > STALE_PENDING_AGE
            ):
                existing.outcome = ExecutionOutcome.uncertain
                self._audit(
                    proposal,
                    "execution.uncertain",
                    actor="system:executor",
                    metadata={
                        "action_type": proposal.action_type,
                        "execution_id": str(existing.id),
                        "reason_code": "stale_pending_attempt",
                    },
                )
            self._audit(
                proposal,
                "execution.replayed",
                actor=f"user:{self._user_id}",
                metadata={
                    "action_type": proposal.action_type,
                    "execution_id": str(existing.id),
                },
            )
            await self._session.flush()
            return proposal, existing

        now = self._now()
        if self._expire_if_due(proposal, now=now, actor=f"user:{self._user_id}"):
            self._audit(
                proposal,
                "execution.denied",
                actor=f"user:{self._user_id}",
                metadata={
                    "action_type": proposal.action_type,
                    "reason_code": "proposal_expired",
                    "version": proposal.version,
                },
            )
            await self._session.flush()
            raise ProposalConflictError("proposal_expired", "The proposal has expired.")
        accounts = await self._accounts.list()
        evidence_sources = await self._evidence_sources(proposal)
        try:
            context = self._policy.validate_execution(
                proposal,
                user_id=self._user_id,
                accounts=accounts,
                evidence_sources=evidence_sources,
                now=now,
            )
        except PolicyViolationError as exc:
            if exc.code == "approval_context_changed":
                # Atomically invalidate the stale approval (Stage 7
                # remediation blocker #1 §6) rather than merely denying this
                # one attempt — a later `execute()` call must not be able to
                # retry against the same stale snapshot; the user must
                # review and approve again.
                self._clear_approval(proposal)
                proposal.status = ProposalStatus.edited
            self._audit(
                proposal,
                "execution.denied",
                actor=f"user:{self._user_id}",
                metadata={
                    "action_type": proposal.action_type,
                    "reason_code": exc.code,
                    "version": proposal.version,
                },
            )
            await self._session.flush()
            raise ProposalConflictError(exc.code, exc.message) from exc

        assert proposal.approved_action_type is not None  # noqa: S101 — policy-validated above
        assert proposal.approved_payload_json is not None  # noqa: S101
        assert proposal.approved_payload_hash is not None  # noqa: S101
        assert proposal.approved_binding_hash is not None  # noqa: S101
        assert proposal.approved_version is not None  # noqa: S101
        action_type = ActionType(proposal.approved_action_type)
        payload = parse_action_payload(action_type, proposal.approved_payload_json)

        # `context` is the CURRENT execution context, already verified by
        # `validate_execution` to match the exact snapshot approval
        # captured — never chosen reactively after a real call fails, and
        # never silently downgraded to simulation or upgraded to real
        # (independent-review blocker #1).
        mode = context.mode
        assert mode is not ExecutionMode.unavailable  # noqa: S101 — policy-validated above
        registry: ExecutorRegistry
        if mode is ExecutionMode.real:
            registry = self._google_executors or UnavailableGoogleExecutorRegistry()
        else:
            registry = self._executors

        # Built ONLY from the immutable `approved_*` snapshot — never from a
        # fresh account read — and passed straight through to the executor,
        # which re-verifies it atomically with token acquisition (Stage 7
        # focused remediation: closes the post-commit TOCTOU window a
        # pre-commit-only check left open).
        approved_authorization = approved_execution_authorization(proposal)

        idempotency_material = (
            f"stage7-exec-v1|{proposal.id}|{action_type}|"
            f"{proposal.approved_version}|{proposal.approved_payload_hash}"
        )
        idempotency_key = hashlib.sha256(idempotency_material.encode("ascii")).hexdigest()
        execution = ActionExecution(
            proposal_id=proposal.id,
            idempotency_key=idempotency_key,
            approved_action_type=action_type,
            approved_proposal_version=proposal.approved_version,
            executed_payload_json=canonical_payload(action_type, payload),
            executed_payload_hash=proposal.approved_payload_hash,
            approval_binding_hash=proposal.approved_binding_hash,
            execution_mode=mode,
            outcome=ExecutionOutcome.pending,
            result_json={},
        )
        self._executions.add(execution, proposal=proposal)
        proposal.status = ProposalStatus.executing
        self._audit(
            proposal,
            "proposal.executing",
            actor=f"user:{self._user_id}",
            metadata={"action_type": proposal.action_type, "version": proposal.version},
        )
        self._audit(
            proposal,
            "execution.started",
            actor="system:executor",
            metadata={"action_type": proposal.action_type, "idempotency_key": idempotency_key},
        )
        # Durability checkpoint (ADR 0003 D16): commit the pending attempt
        # BEFORE calling any real executor. A crash or network failure during
        # the call below can then never erase the fact that it was attempted
        # — the next read finds this `pending` row and, once stale, recovers
        # it to `uncertain` rather than leaving it ambiguous forever.
        await self._session.commit()
        await self._session.refresh(execution)
        # Test-only barrier (no-op in production): lets the race-test suite
        # deterministically interleave a concurrent account mutation exactly
        # here — after the durable commit, before token acquisition.
        await self._post_commit_hook()

        try:
            outcome = await registry.execute(
                action_type,
                proposal_id=proposal.id,
                payload=payload,
                approved_authorization=approved_authorization,
            )
        except FinalExecutionError as exc:
            execution.completed_at = self._now()
            execution.outcome = ExecutionOutcome.failed
            execution.error_code = exc.error_code
            if exc.error_code == "approval_context_changed":
                # The approved account/authorisation/scope was re-verified
                # atomically at token acquisition and no longer matched live
                # state — refused before any provider call was made. This is
                # a known, disclosed refusal, never an "uncertain" outcome:
                # LifeFlow knows it did not attempt the external action.
                execution.result_json = {
                    "status": "failed",
                    "message": (
                        "The approved account, authorisation, or scope changed before "
                        "execution. No external action was attempted. Review your "
                        "connected account and check for a fresh proposal."
                    ),
                }
            else:
                execution.result_json = {
                    "status": "failed",
                    "message": "The execution failed and was not retried.",
                }
            proposal.status = ProposalStatus.failed
            self._audit(
                proposal,
                "execution.failed",
                actor="system:executor",
                metadata={
                    "action_type": proposal.action_type,
                    "error_code": exc.error_code,
                    "final": True,
                },
            )
            self._audit(
                proposal,
                "proposal.failed",
                actor="system:executor",
                metadata={"action_type": proposal.action_type, "version": proposal.version},
            )
        else:
            if outcome.status == "uncertain":
                # proposal.status deliberately stays `executing`: we do not
                # know whether the external action happened. Never retried
                # automatically (extends assumption A20).
                execution.outcome = ExecutionOutcome.uncertain
                execution.result_json = outcome.result
                self._audit(
                    proposal,
                    "execution.uncertain",
                    actor="system:executor",
                    metadata={
                        "action_type": proposal.action_type,
                        "execution_id": str(execution.id),
                    },
                )
            else:
                execution.completed_at = self._now()
                execution.outcome = ExecutionOutcome.succeeded
                execution.result_json = outcome.result
                proposal.status = ProposalStatus.executed
                self._audit(
                    proposal,
                    "execution.succeeded",
                    actor="system:executor",
                    metadata={
                        "action_type": proposal.action_type,
                        "execution_id": str(execution.id),
                    },
                )
                self._audit(
                    proposal,
                    "proposal.executed",
                    actor="system:executor",
                    metadata={"action_type": proposal.action_type, "version": proposal.version},
                )
        await self._session.commit()
        return proposal, execution


async def recover_stale_pending_executions(session: AsyncSession, *, now: datetime) -> int:
    """Stage 9 Delivery Phase 5 (§10): proactively sweep every user's stale
    `pending` `ActionExecution` rows, not just the one a caller happens to
    re-`execute()` or read next.

    Before this, a `pending` row older than `STALE_PENDING_AGE` was only
    ever durably flipped to `uncertain` lazily — inside `execute()`'s own
    re-entry guard (above), which only runs if *that specific* proposal is
    acted on again — or displayed as `uncertain` without being persisted
    (`effective_execution_status`, read-time only). A worker that crashed
    right after committing the pending row (the durability checkpoint in
    `execute()`, before the real executor call) and whose proposal nobody
    ever revisits would leave that row `pending` in the database forever:
    always correctly *reported* as uncertain on read, but never actually
    resolved, and invisible to any operational sweep — unlike the durable
    deletion engine's `recover_stale_operations` and the scheduled brief's
    `recover_stale_running`, which both already have exactly this pattern.

    Cross-user by necessity, like those two. Never touches `succeeded`,
    `failed`, or already-`uncertain` rows, and never retries the underlying
    write — flipping the stored outcome to `uncertain` is the same terminal
    (for now), non-retryable state `execute()`'s own re-entry guard already
    assigns; this only makes sure it happens even if nothing ever revisits
    the proposal."""
    cutoff = now - STALE_PENDING_AGE
    stale = (
        (
            await session.execute(
                select(ActionExecution, ActionProposal)
                .join(ActionProposal, ActionExecution.proposal_id == ActionProposal.id)
                .where(
                    ActionExecution.outcome == ExecutionOutcome.pending,
                    ActionExecution.started_at < cutoff,
                )
            )
        )
        .tuples()
        .all()
    )
    for execution, proposal in stale:
        execution.outcome = ExecutionOutcome.uncertain
        record_audit_event(
            session,
            user_id=proposal.user_id,
            actor="system:executor",
            event_type="execution.uncertain",
            entity_type="action_proposal",
            entity_id=str(proposal.id),
            metadata={
                "action_type": proposal.action_type,
                "execution_id": str(execution.id),
                "reason_code": "stale_pending_attempt",
            },
        )
    await session.commit()
    return len(stale)


__all__ = [
    "ActionProposalService",
    "PostCommitHook",
    "ProposalConflictError",
    "ProposalGenerationSummary",
    "recover_stale_pending_executions",
]
