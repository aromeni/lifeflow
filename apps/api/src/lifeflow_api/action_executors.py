"""Executors: Stage 6 simulated ones (unchanged) and Stage 7's real Google
ones. `ActionExecutor.execute()` returns `ExecutorOutcome` — `succeeded` or
`uncertain` — or raises `FinalExecutionError` for a clear, final rejection;
`action_proposal_service.execute()` classifies these into
`ActionExecution.outcome` (ADR 0003 D16). Google executors never expose a
generic HTTP method — they only ever call the narrow, allow-listed
`GmailDraftClient.create_draft` / `CalendarEventClient.insert_event`
(threat model T22/T23).
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from lifeflow_api.accounts import GoogleTokenService, ReauthorisationRequiredError
from lifeflow_api.action_payloads import (
    CalendarEventCreatePayload,
    GmailDraftCreatePayload,
    TypedActionPayload,
    action_payload_hash,
)
from lifeflow_api.execution_context import (
    ApprovedExecutionAuthorization,
    ApprovedExecutionContextChangedError,
)
from lifeflow_api.failure_taxonomy import classify_exception
from lifeflow_api.google.calendar_client import CalendarEventClient
from lifeflow_api.google.errors import (
    GoogleApiError,
    GoogleAuthError,
    GoogleClientError,
    GoogleTransientError,
)
from lifeflow_api.google.gmail_client import GmailDraftClient
from lifeflow_api.models import ActionType
from lifeflow_api.retry import retry_read


def _is_retryable(exc: BaseException) -> bool:
    return classify_exception(exc).retryable


class FinalExecutionError(RuntimeError):
    """A clear, final failure; the service must not retry automatically."""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


@dataclass(frozen=True)
class ExecutorOutcome:
    status: Literal["succeeded", "uncertain"]
    result: dict[str, str]


class ActionExecutor(Protocol):
    async def execute(
        self,
        *,
        proposal_id: uuid.UUID,
        payload: TypedActionPayload,
        approved_authorization: ApprovedExecutionAuthorization | None,
    ) -> ExecutorOutcome: ...


class ExecutorRegistry(Protocol):
    """Either SimulatedExecutorRegistry or GoogleExecutorRegistry — whatever
    `action_proposal_service.py` is constructed with, it only ever depends
    on this shape.

    `approved_authorization` (Stage 7 focused remediation) is the exact
    approval-time account/revision/scope snapshot, built only from
    `ActionProposal.approved_*` columns — `None` for a simulated proposal.
    Simulated executors and `create_task` ignore it; real Google executors
    require it and pass it straight through to `GoogleTokenService`, which
    re-verifies it atomically under the account row lock, closing the
    post-commit TOCTOU window a pre-commit-only check left open."""

    async def execute(
        self,
        action_type: ActionType,
        *,
        proposal_id: uuid.UUID,
        payload: TypedActionPayload,
        approved_authorization: ApprovedExecutionAuthorization | None,
    ) -> ExecutorOutcome: ...


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
        self,
        *,
        proposal_id: uuid.UUID,
        payload: TypedActionPayload,
        approved_authorization: ApprovedExecutionAuthorization | None,
    ) -> ExecutorOutcome:
        # Never reads `approved_authorization` — simulated/internal
        # executors have no Google credentials to use, and never will.
        del approved_authorization
        return ExecutorOutcome(
            status="succeeded",
            result={
                "status": "simulated",
                "simulated_id": _simulated_id("task", ActionType.create_task, proposal_id, payload),
                "message": "Internal task creation was simulated.",
            },
        )


class SimulatedGmailDraftExecutor:
    async def execute(
        self,
        *,
        proposal_id: uuid.UUID,
        payload: TypedActionPayload,
        approved_authorization: ApprovedExecutionAuthorization | None,
    ) -> ExecutorOutcome:
        del approved_authorization
        return ExecutorOutcome(
            status="succeeded",
            result={
                "status": "simulated",
                "simulated_id": _simulated_id(
                    "draft", ActionType.create_gmail_draft, proposal_id, payload
                ),
                "message": "Gmail draft creation was simulated; no email was sent.",
            },
        )


class SimulatedCalendarEventExecutor:
    async def execute(
        self,
        *,
        proposal_id: uuid.UUID,
        payload: TypedActionPayload,
        approved_authorization: ApprovedExecutionAuthorization | None,
    ) -> ExecutorOutcome:
        del approved_authorization
        return ExecutorOutcome(
            status="succeeded",
            result={
                "status": "simulated",
                "simulated_id": _simulated_id(
                    "event", ActionType.create_calendar_event, proposal_id, payload
                ),
                "message": "Calendar event creation was simulated; no calendar was changed.",
            },
        )


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
        approved_authorization: ApprovedExecutionAuthorization | None,
    ) -> ExecutorOutcome:
        executor = self._executors.get(action_type)
        if executor is None:
            raise FinalExecutionError("executor_not_registered")
        return await executor.execute(
            proposal_id=proposal_id,
            payload=payload,
            approved_authorization=approved_authorization,
        )


class GoogleGmailDraftExecutor:
    """Approved Gmail-draft proposals only. Calls exactly
    `GmailDraftClient.create_draft` — never `.../send` (T22) — then
    `get_draft` to independently verify what Gmail actually stored (D17,
    Stage 7 focused remediation: a real sandbox account showed
    `create_draft`'s own response frequently omits a parsed `payload`,
    producing a false-negative `uncertain` outcome for a draft Gmail had, in
    fact, created correctly)."""

    def __init__(self, client: GmailDraftClient, tokens: GoogleTokenService) -> None:
        self._client = client
        self._tokens = tokens

    async def execute(
        self,
        *,
        proposal_id: uuid.UUID,
        payload: TypedActionPayload,
        approved_authorization: ApprovedExecutionAuthorization | None,
    ) -> ExecutorOutcome:
        if not isinstance(payload, GmailDraftCreatePayload):
            raise FinalExecutionError("payload_type_mismatch")
        if approved_authorization is None:  # pragma: no cover — wiring guarantees this is set
            # whenever `execute()` selected a real Google registry (Stage 7
            # focused remediation): defensive, never reachable in practice.
            raise FinalExecutionError("approved_authorization_missing")
        try:
            # Exact-account, exact-revision, exact-scope re-check, atomic
            # with token acquisition (Stage 7 focused remediation) — never a
            # `(user, provider)` lookup that could resolve to whatever
            # happens to be connected now.
            access_token = await self._tokens.get_valid_access_token_for_execution(
                user_id=self._tokens.user_id,
                connected_account_id=approved_authorization.connected_account_id,
                expected_provider=approved_authorization.provider,
                expected_authorisation_revision=approved_authorization.authorisation_revision,
                required_scope=approved_authorization.required_scope,
            )
            created = await self._client.create_draft(
                access_token=access_token,
                to=list(payload.to),
                subject=payload.subject,
                body=payload.body,
                thread_id=payload.thread_id,
            )
        except ApprovedExecutionContextChangedError as exc:
            # The approved account/revision/scope no longer matches live
            # state — refused strictly before any Gmail call was made.
            raise FinalExecutionError("approval_context_changed") from exc
        except ReauthorisationRequiredError as exc:
            raise FinalExecutionError("google_reauthorisation_required") from exc
        except GoogleAuthError as exc:
            raise FinalExecutionError("google_auth_rejected") from exc
        except GoogleClientError as exc:
            raise FinalExecutionError(f"google_client_error_{exc.status_code}") from exc
        except GoogleTransientError:
            return ExecutorOutcome(
                status="uncertain",
                result={"message": "Gmail did not confirm draft creation before the call ended."},
            )

        # Verify the ACTUAL stored draft, not `create_draft`'s own response
        # (D17): by this point the draft has genuinely been created — any
        # failure below means the write happened but could not be
        # independently confirmed, which is `uncertain`, never `failed`.
        try:
            content = await retry_read(
                lambda: self._client.get_draft(
                    access_token=access_token, draft_id=created.draft_id
                ),
                is_retryable=_is_retryable,
                max_attempts=2,
            )
        except GoogleApiError:
            return ExecutorOutcome(
                status="uncertain",
                result={"message": "Gmail did not confirm the created draft's content in time."},
            )

        approved_to = {address.strip().lower() for address in payload.to}
        approved_subject = payload.subject.strip()
        approved_body = payload.body.replace("\r\n", "\n").strip()
        if (
            set(content.to) != approved_to
            or content.subject != approved_subject
            or content.body != approved_body
        ):
            return ExecutorOutcome(
                status="uncertain",
                result={
                    "message": (
                        "Gmail's stored draft could not be confirmed to match the approved content."
                    )
                },
            )
        # Gmail's `threadId` reflects its own threading decision — a
        # requested reply threadId is only honoured when Subject/References
        # make it a valid continuation of that thread, otherwise Gmail
        # silently starts a new one. Never compared against what was
        # requested; only the actual, authoritative value is recorded.
        return ExecutorOutcome(
            status="succeeded",
            result={
                "status": "created",
                "draft_id": content.draft_id,
                "message_id": content.message_id,
                "thread_id": content.thread_id,
                "message": "Gmail draft created; no email was sent.",
            },
        )


def _aware_instant(value: str) -> datetime | None:
    """Parse a Google RFC 3339 date-time into a UTC instant. Google returns
    times normalised to the calendar's offset (e.g. `+01:00` for a
    Europe/London summer event) — comparison is by instant, never by
    spelling. A missing, malformed, or naive value (an all-day `date`, which
    a timed create must never come back as) returns None."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else None


class GoogleCalendarEventExecutor:
    """Approved new-calendar-event proposals only. Calls exactly
    `CalendarEventClient.insert_event`, which hard-codes
    `sendUpdates=none` — never `update`/`patch`/`delete` (T23) — then
    `get_event` to independently verify what Calendar actually stored
    (D40, the Calendar analogue of Gmail's D17 re-fetch): title, start and
    end instants, attendees, and that the event is not cancelled, all
    checked against the approved payload."""

    def __init__(self, client: CalendarEventClient, tokens: GoogleTokenService) -> None:
        self._client = client
        self._tokens = tokens

    async def execute(
        self,
        *,
        proposal_id: uuid.UUID,
        payload: TypedActionPayload,
        approved_authorization: ApprovedExecutionAuthorization | None,
    ) -> ExecutorOutcome:
        if not isinstance(payload, CalendarEventCreatePayload):
            raise FinalExecutionError("payload_type_mismatch")
        if approved_authorization is None:  # pragma: no cover — wiring guarantees this is set
            raise FinalExecutionError("approved_authorization_missing")
        try:
            access_token = await self._tokens.get_valid_access_token_for_execution(
                user_id=self._tokens.user_id,
                connected_account_id=approved_authorization.connected_account_id,
                expected_provider=approved_authorization.provider,
                expected_authorisation_revision=approved_authorization.authorisation_revision,
                required_scope=approved_authorization.required_scope,
            )
            result = await self._client.insert_event(
                access_token=access_token,
                summary=payload.title,
                description=payload.description,
                location=payload.location,
                starts_at=payload.starts_at,
                ends_at=payload.ends_at,
                timezone=payload.timezone,
                attendees=list(payload.attendees),
            )
        except ApprovedExecutionContextChangedError as exc:
            raise FinalExecutionError("approval_context_changed") from exc
        except ReauthorisationRequiredError as exc:
            raise FinalExecutionError("google_reauthorisation_required") from exc
        except GoogleAuthError as exc:
            raise FinalExecutionError("google_auth_rejected") from exc
        except GoogleClientError as exc:
            raise FinalExecutionError(f"google_client_error_{exc.status_code}") from exc
        except GoogleTransientError:
            message = "Calendar did not confirm event creation before the call ended."
            return ExecutorOutcome(status="uncertain", result={"message": message})

        # Verify the ACTUAL stored event, not `insert_event`'s own response
        # (D40): by this point the event has genuinely been created — any
        # failure below means the write happened but could not be
        # independently confirmed, which is `uncertain`, never `failed`,
        # and is never retried automatically.
        try:
            record = await retry_read(
                lambda: self._client.get_event(access_token=access_token, event_id=result.event_id),
                is_retryable=_is_retryable,
                max_attempts=2,
            )
        except GoogleApiError:
            message = "Calendar did not confirm the created event's content in time."
            return ExecutorOutcome(status="uncertain", result={"message": message})

        approved_attendees = {address.strip().lower() for address in payload.attendees}
        actual_attendees = {address.strip().lower() for address in record.attendees}
        # Calendar may add the calendar owner as an attendee on its own;
        # any other unapproved attendee is a mismatch.
        organiser = (record.organiser_email or "").strip().lower()
        extra_attendees = (
            actual_attendees - approved_attendees - ({organiser} if organiser else set())
        )
        if (
            record.status == "cancelled"
            or record.summary != payload.title
            or _aware_instant(record.start) != payload.starts_at.astimezone(UTC)
            or _aware_instant(record.end) != payload.ends_at.astimezone(UTC)
            or not approved_attendees <= actual_attendees
            or extra_attendees
        ):
            message = "Calendar's stored event could not be confirmed to match the approval."
            return ExecutorOutcome(status="uncertain", result={"message": message})
        return ExecutorOutcome(
            status="succeeded",
            result={
                "status": "created",
                "event_id": record.event_id,
                "guest_notifications": "off",
                "message": "Calendar event created; guests were not notified.",
            },
        )


class GoogleExecutorRegistry:
    """Mirrors SimulatedExecutorRegistry's shape for real Google executors —
    kept as a distinct class (not a rename) so the name always tells the
    truth about what it dispatches to."""

    def __init__(self, executors: dict[ActionType, ActionExecutor]) -> None:
        self._executors = executors

    async def execute(
        self,
        action_type: ActionType,
        *,
        proposal_id: uuid.UUID,
        payload: TypedActionPayload,
        approved_authorization: ApprovedExecutionAuthorization | None,
    ) -> ExecutorOutcome:
        executor = self._executors.get(action_type)
        if executor is None:
            raise FinalExecutionError("executor_not_registered")
        return await executor.execute(
            proposal_id=proposal_id,
            payload=payload,
            approved_authorization=approved_authorization,
        )


class UnavailableGoogleExecutorRegistry:
    """`ActionProposalService.execute()` reaches for this only when
    `resolve_execution_context` decided `real` but this deployment/request never
    wired a real Google executor registry (a wiring bug, not a user error —
    the policy check already denies a genuinely unconnected/unscoped
    account before execution gets this far). Always a controlled, final
    failure — never a silent fallback to simulation (independent-review
    blocker #2)."""

    async def execute(
        self,
        action_type: ActionType,
        *,
        proposal_id: uuid.UUID,
        payload: TypedActionPayload,
        approved_authorization: ApprovedExecutionAuthorization | None,
    ) -> ExecutorOutcome:
        del approved_authorization
        raise FinalExecutionError("google_execution_unavailable")


class ProviderWritesDisabledExecutorRegistry:
    """Stage 11A Phase 4D's hard write kill switch. `google_wiring.py`'s
    `build_google_executor_registry` returns this — instead of a real
    `GoogleExecutorRegistry` — whenever `Settings.google_provider_writes_enabled`
    is false, even when a real Google integration is otherwise fully wired
    and a real account is connected. Distinct from
    `UnavailableGoogleExecutorRegistry` (a wiring bug) so the two causes are
    never confused in an error code or audit trail: this one means writes
    are deliberately, administratively disabled, not that Google isn't
    configured. Raises before any Gmail/Calendar client method is called —
    no provider HTTP request is ever attempted."""

    async def execute(
        self,
        action_type: ActionType,
        *,
        proposal_id: uuid.UUID,
        payload: TypedActionPayload,
        approved_authorization: ApprovedExecutionAuthorization | None,
    ) -> ExecutorOutcome:
        del action_type, proposal_id, payload, approved_authorization
        raise FinalExecutionError("provider_writes_disabled")


__all__ = [
    "ActionExecutor",
    "ExecutorOutcome",
    "ExecutorRegistry",
    "FinalExecutionError",
    "GoogleCalendarEventExecutor",
    "GoogleExecutorRegistry",
    "GoogleGmailDraftExecutor",
    "ProviderWritesDisabledExecutorRegistry",
    "SimulatedCalendarEventExecutor",
    "SimulatedExecutorRegistry",
    "SimulatedGmailDraftExecutor",
    "SimulatedTaskExecutor",
    "UnavailableGoogleExecutorRegistry",
]
