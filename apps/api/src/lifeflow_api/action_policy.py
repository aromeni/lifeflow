"""Deterministic Stage 6 approval and pre-execution policy engine."""

import uuid
from datetime import datetime

from lifeflow_api.action_payloads import (
    CalendarEventCreatePayload,
    TaskCreatePayload,
    action_payload_hash,
    approval_binding_hash,
    parse_action_payload,
)
from lifeflow_api.models import (
    AccountStatus,
    ActionProposal,
    ActionType,
    ConnectedAccount,
    ProposalStatus,
    RiskLevel,
)

SIMULATED_PROVIDER = "synthetic"
SIMULATED_SCOPE = "demo"

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
        accounts: list[ConnectedAccount],
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
        if action_type in {
            ActionType.create_gmail_draft,
            ActionType.create_calendar_event,
        }:
            has_demo_scope = any(
                account.provider == SIMULATED_PROVIDER
                and account.status == AccountStatus.active
                and SIMULATED_SCOPE in account.granted_scopes
                for account in accounts
            )
            if not has_demo_scope:
                raise PolicyViolationError(
                    "simulated_scope_missing",
                    "This Stage 6 action requires the active synthetic demo capability.",
                )

    def validate_approval(
        self,
        proposal: ActionProposal,
        *,
        user_id: uuid.UUID,
        accounts: list[ConnectedAccount],
        now: datetime,
        displayed_action_type: ActionType,
        displayed_payload_hash: str,
        displayed_version: int,
    ) -> None:
        self._validate_common(proposal, user_id=user_id, accounts=accounts, now=now)
        if proposal.status not in {ProposalStatus.proposed, ProposalStatus.edited}:
            raise PolicyViolationError("invalid_transition", "This proposal cannot be approved.")
        if displayed_action_type != ActionType(proposal.action_type):
            raise PolicyViolationError("stale_preview", "The displayed action type is stale.")
        if displayed_payload_hash != proposal.payload_hash:
            raise PolicyViolationError("stale_preview", "The displayed payload is stale.")
        if displayed_version != proposal.version:
            raise PolicyViolationError("stale_version", "The displayed proposal version is stale.")

    def validate_execution(
        self,
        proposal: ActionProposal,
        *,
        user_id: uuid.UUID,
        accounts: list[ConnectedAccount],
        now: datetime,
    ) -> None:
        self._validate_common(proposal, user_id=user_id, accounts=accounts, now=now)
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
        expected_binding = approval_binding_hash(
            ActionType(proposal.action_type), approved_payload, proposal.version
        )
        if expected_binding != proposal.approved_binding_hash:
            raise PolicyViolationError("approval_mismatch", "The approval binding is invalid.")
        if proposal.user_edited_at and proposal.approved_at < proposal.user_edited_at:
            raise PolicyViolationError(
                "approval_stale", "Fresh approval is required after editing."
            )


__all__ = [
    "EXPECTED_RISK",
    "SIMULATED_PROVIDER",
    "SIMULATED_SCOPE",
    "ActionPolicyEngine",
    "PolicyViolationError",
]
