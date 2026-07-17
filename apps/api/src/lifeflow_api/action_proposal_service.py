"""Stage 6 proposal lifecycle: generation, approval, and simulated execution."""

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.action_executors import FinalExecutionError, SimulatedExecutorRegistry
from lifeflow_api.action_payloads import (
    TypedActionPayload,
    action_payload_hash,
    approval_binding_hash,
    canonical_payload,
    parse_action_payload,
)
from lifeflow_api.action_policy import ActionPolicyEngine, PolicyViolationError
from lifeflow_api.audit import record_audit_event
from lifeflow_api.models import (
    ActionExecution,
    ActionProposal,
    ActionType,
    Brief,
    ProposalStatus,
    Signal,
    SourceItem,
)
from lifeflow_api.proposal_composition import (
    PROPOSAL_COMPOSER_VERSION,
    candidate_payload_json,
    compose_proposal_candidates,
)
from lifeflow_api.repositories import (
    ActionExecutionRepository,
    ActionProposalRepository,
    ConnectedAccountRepository,
)

NowFactory = Callable[[], datetime]


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


class ActionProposalService:
    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        policy: ActionPolicyEngine | None = None,
        executors: SimulatedExecutorRegistry | None = None,
        now_factory: NowFactory | None = None,
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._proposals = ActionProposalRepository(session, user_id)
        self._executions = ActionExecutionRepository(session, user_id)
        self._accounts = ConnectedAccountRepository(session, user_id)
        self._policy = policy or ActionPolicyEngine()
        self._executors = executors or SimulatedExecutorRegistry()
        self._now = now_factory or (lambda: datetime.now(UTC))

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
    ) -> ProposalGenerationSummary:
        """Change-aware proposal generation with stable origin uniqueness."""

        composed = compose_proposal_candidates(
            signals,
            sources,
            reference=reference,
            timezone=timezone,
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
        for candidate in composed.candidates:
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
                    # Savepoint: a concurrent request may have inserted this
                    # origin after our locked read returned nothing. The
                    # unique constraint stays authoritative; the loser falls
                    # through to the change-aware path against the winner.
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
                    continue

            if self._expire_if_due(existing, now=reference, actor="system:proposal"):
                preserved += 1
                continue
            if existing.status != ProposalStatus.proposed or existing.user_edited_at is not None:
                preserved += 1
                continue

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
                continue

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
        try:
            self._policy.validate_approval(
                proposal,
                user_id=self._user_id,
                accounts=accounts,
                now=now,
                displayed_action_type=action_type,
                displayed_payload_hash=displayed_payload_hash,
                displayed_version=expected_version,
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
        proposal.approved_action_type = action_type
        proposal.approved_payload_json = canonical_payload(action_type, payload)
        proposal.approved_payload_hash = proposal.payload_hash
        proposal.approved_binding_hash = approval_binding_hash(
            action_type, payload, proposal.version
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
        try:
            self._policy.validate_execution(
                proposal,
                user_id=self._user_id,
                accounts=accounts,
                now=now,
            )
        except PolicyViolationError as exc:
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
        idempotency_material = (
            f"stage6-sim-v1|{proposal.id}|{action_type}|"
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
        await self._session.flush()
        await self._session.refresh(execution)

        try:
            result = await self._executors.execute(
                action_type,
                proposal_id=proposal.id,
                payload=payload,
            )
        except FinalExecutionError as exc:
            execution.completed_at = self._now()
            execution.error_code = exc.error_code
            execution.result_json = {
                "status": "failed",
                "message": "The simulated execution failed and was not retried.",
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
            execution.completed_at = self._now()
            execution.result_json = result
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
        await self._session.flush()
        return proposal, execution


__all__ = [
    "ActionProposalService",
    "ProposalConflictError",
    "ProposalGenerationSummary",
]
