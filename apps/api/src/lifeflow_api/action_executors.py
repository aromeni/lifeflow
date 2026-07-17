"""Stage 6 simulated executors. No external connector or Google code lives here."""

import hashlib
import uuid
from typing import Protocol

from lifeflow_api.action_payloads import TypedActionPayload, action_payload_hash
from lifeflow_api.models import ActionType


class FinalExecutionError(RuntimeError):
    """A final simulated failure; the service must not retry automatically."""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class ActionExecutor(Protocol):
    async def execute(
        self, *, proposal_id: uuid.UUID, payload: TypedActionPayload
    ) -> dict[str, str]: ...


def _simulated_id(
    prefix: str,
    action_type: ActionType,
    proposal_id: uuid.UUID,
    payload: TypedActionPayload,
) -> str:
    material = f"{proposal_id}|{action_payload_hash(action_type, payload)}"
    return f"{prefix}-{hashlib.sha256(material.encode('ascii')).hexdigest()[:16]}"


class SimulatedTaskExecutor:
    async def execute(
        self, *, proposal_id: uuid.UUID, payload: TypedActionPayload
    ) -> dict[str, str]:
        return {
            "status": "simulated",
            "simulated_id": _simulated_id("task", ActionType.create_task, proposal_id, payload),
            "message": "Internal task creation was simulated.",
        }


class SimulatedGmailDraftExecutor:
    async def execute(
        self, *, proposal_id: uuid.UUID, payload: TypedActionPayload
    ) -> dict[str, str]:
        return {
            "status": "simulated",
            "simulated_id": _simulated_id(
                "draft", ActionType.create_gmail_draft, proposal_id, payload
            ),
            "message": "Gmail draft creation was simulated; no email was sent.",
        }


class SimulatedCalendarEventExecutor:
    async def execute(
        self, *, proposal_id: uuid.UUID, payload: TypedActionPayload
    ) -> dict[str, str]:
        return {
            "status": "simulated",
            "simulated_id": _simulated_id(
                "event", ActionType.create_calendar_event, proposal_id, payload
            ),
            "message": "Calendar event creation was simulated; no calendar was changed.",
        }


class SimulatedExecutorRegistry:
    def __init__(self, executors: dict[ActionType, ActionExecutor] | None = None) -> None:
        self._executors = executors or {
            ActionType.create_task: SimulatedTaskExecutor(),
            ActionType.create_gmail_draft: SimulatedGmailDraftExecutor(),
            ActionType.create_calendar_event: SimulatedCalendarEventExecutor(),
        }

    async def execute(
        self,
        action_type: ActionType,
        *,
        proposal_id: uuid.UUID,
        payload: TypedActionPayload,
    ) -> dict[str, str]:
        executor = self._executors.get(action_type)
        if executor is None:
            raise FinalExecutionError("executor_not_registered")
        return await executor.execute(proposal_id=proposal_id, payload=payload)


__all__ = [
    "ActionExecutor",
    "FinalExecutionError",
    "SimulatedCalendarEventExecutor",
    "SimulatedExecutorRegistry",
    "SimulatedGmailDraftExecutor",
    "SimulatedTaskExecutor",
]
