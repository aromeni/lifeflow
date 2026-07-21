"""Deterministic Stage 6 approval and pre-execution policy engine, extended
in Stage 7 remediation with approval-bound execution-context checks
(independent-review blocker #1)."""

import uuid
from datetime import datetime

from lifeflow_api.action_payloads import (
    CalendarEventCreatePayload,
    TaskCreatePayload,
    action_payload_hash,
    approval_binding_hash,
    parse_action_payload,
)
from lifeflow_api.execution_context import (
    GOOGLE_PROVIDER,
    SIMULATED_PROVIDER,
    SIMULATED_SCOPE,
    ExecutionContext,
    SourceMode,
    execution_context_hash,
    resolve_execution_context,
)
from lifeflow_api.models import (
    ActionProposal,
    ActionType,
    ConnectedAccount,
    ExecutionMode,
    ProposalStatus,
    RiskLevel,
    SourceItem,
)

EXPECTED_RISK = {
    ActionType.create_task: RiskLevel.low,
    ActionType.create_gmail_draft: RiskLevel.medium,
    ActionType.create_calendar_event: RiskLevel.medium,
}


class PolicyViolationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ActionPolicyEngine:
    def _validate_common(
        self,
        proposal: ActionProposal,
        *,
        user_id: uuid.UUID,
        now: datetime,
    ) -> None:
        if proposal.user_id != user_id:
            raise PolicyViolationError(
                "ownership_mismatch", "The proposal is not owned by this user."
            )
        action_type = ActionType(proposal.action_type)
        if RiskLevel(proposal.risk_level) != EXPECTED_RISK[action_type]:
            raise PolicyViolationError(
                "risk_mismatch", "The proposal risk does not match its action type."
            )
        if proposal.expires_at <= now:
            raise PolicyViolationError("proposal_expired", "The proposal has expired.")
        payload = parse_action_payload(action_type, proposal.payload_json)
        if action_payload_hash(action_type, payload) != proposal.payload_hash:
            raise PolicyViolationError("payload_hash_mismatch", "The proposal payload has changed.")
        if isinstance(payload, TaskCreatePayload) and payload.due_at and payload.due_at <= now:
            raise PolicyViolationError("invalid_due_at", "The task due time has passed.")
        if isinstance(payload, CalendarEventCreatePayload) and payload.starts_at <= now:
            raise PolicyViolationError(
                "invalid_event_time", "The calendar event start time has passed."
            )

    def validate_approval(
        self,
        proposal: ActionProposal,
        *,
        user_id: uuid.UUID,
        accounts: list[ConnectedAccount],
        evidence_sources: list[SourceItem],
        now: datetime,
        displayed_action_type: ActionType,
        displayed_payload_hash: str,
        displayed_version: int,
        displayed_execution_context_hash: str,
    ) -> ExecutionContext:
        self._validate_common(proposal, user_id=user_id, now=now)
        if proposal.status not in {ProposalStatus.proposed, ProposalStatus.edited}:
            raise PolicyViolationError("invalid_transition", "This proposal cannot be approved.")
        if displayed_action_type != ActionType(proposal.action_type):
            raise PolicyViolationError("stale_preview", "The displayed action type is stale.")
        if displayed_payload_hash != proposal.payload_hash:
            raise PolicyViolationError("stale_preview", "The displayed payload is stale.")
        if displayed_version != proposal.version:
            raise PolicyViolationError("stale_version", "The displayed proposal version is stale.")

        action_type = ActionType(proposal.action_type)
        context = resolve_execution_context(
            action_type, accounts=accounts, evidence_sources=evidence_sources
        )
        if context.mode is ExecutionMode.unavailable:
            raise PolicyViolationError(
                "simulated_scope_missing",
                "This action requires an active, correctly-scoped connected account.",
            )
        if execution_context_hash(context) != displayed_execution_context_hash:
            raise PolicyViolationError(
                "stale_execution_context",
                "The execution context changed since you last viewed this proposal; reload it.",
            )
        return context

    def validate_execution(
        self,
        proposal: ActionProposal,
        *,
        user_id: uuid.UUID,
        accounts: list[ConnectedAccount],
        evidence_sources: list[SourceItem],
        now: datetime,
    ) -> ExecutionContext:
        self._validate_common(proposal, user_id=user_id, now=now)
        if proposal.status != ProposalStatus.approved:
            raise PolicyViolationError(
                "invalid_transition", "Only an approved proposal can execute."
            )
        if (
            proposal.approved_action_type is None
            or proposal.approved_payload_json is None
            or proposal.approved_payload_hash is None
            or proposal.approved_binding_hash is None
            or proposal.approved_version is None
            or proposal.approved_at is None
            or proposal.approved_execution_mode is None
            or proposal.approved_provider is None
            or proposal.approved_execution_context_hash is None
        ):
            raise PolicyViolationError(
                "approval_missing", "The exact approval snapshot is incomplete."
            )
        if proposal.approved_action_type != proposal.action_type:
            raise PolicyViolationError("approval_mismatch", "The approved action type has changed.")
        if proposal.approved_version != proposal.version:
            raise PolicyViolationError("approval_mismatch", "The proposal changed after approval.")
        if proposal.approved_payload_hash != proposal.payload_hash:
            raise PolicyViolationError("approval_mismatch", "The payload changed after approval.")
        approved_payload = parse_action_payload(
            ActionType(proposal.approved_action_type), proposal.approved_payload_json
        )
        if approved_payload.model_dump(mode="json") != proposal.payload_json:
            raise PolicyViolationError("approval_mismatch", "The approved payload is not current.")

        approved_context = ExecutionContext(
            mode=ExecutionMode(proposal.approved_execution_mode),
            provider=proposal.approved_provider,
            connected_account_id=proposal.approved_connected_account_id,
            account_authorisation_revision=proposal.approved_authorisation_revision,
            required_scope=proposal.approved_required_scope,
            source_mode=SourceMode.google
            if proposal.approved_provider == GOOGLE_PROVIDER
            else SourceMode.synthetic,
            source_account_id=proposal.approved_source_account_id,
        )
        expected_binding = approval_binding_hash(
            ActionType(proposal.action_type),
            approved_payload,
            proposal.version,
            proposal.approved_execution_context_hash,
        )
        if expected_binding != proposal.approved_binding_hash:
            raise PolicyViolationError("approval_mismatch", "The approval binding is invalid.")
        if execution_context_hash(approved_context) != proposal.approved_execution_context_hash:
            raise PolicyViolationError(
                "approval_mismatch", "The approved execution-context snapshot is invalid."
            )
        if proposal.user_edited_at and proposal.approved_at < proposal.user_edited_at:
            raise PolicyViolationError(
                "approval_stale", "Fresh approval is required after editing."
            )

        # Revalidate before execution (Stage 7 remediation blocker #1): the
        # execution context is reconstructed from CURRENT source provenance
        # and account state and compared against the exact snapshot approval
        # captured. Any difference — mode flip, account swap, revoked scope,
        # disconnected account — refuses execution rather than silently
        # adjusting or falling back.
        action_type = ActionType(proposal.action_type)
        current_context = resolve_execution_context(
            action_type, accounts=accounts, evidence_sources=evidence_sources
        )
        if execution_context_hash(current_context) != proposal.approved_execution_context_hash:
            raise PolicyViolationError(
                "approval_context_changed",
                "The execution context changed since approval; review and approve again.",
            )
        return current_context


__all__ = [
    "EXPECTED_RISK",
    "GOOGLE_PROVIDER",
    "SIMULATED_PROVIDER",
    "SIMULATED_SCOPE",
    "ActionPolicyEngine",
    "PolicyViolationError",
]
