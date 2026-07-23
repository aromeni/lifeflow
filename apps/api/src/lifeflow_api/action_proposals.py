"""Owner-scoped Stage 6 action proposal and approval API."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from lifeflow_api.action_payloads import (
    CalendarEventCreatePayload,
    GmailDraftCreatePayload,
    TaskCreatePayload,
    TypedActionPayload,
    parse_action_payload,
)
from lifeflow_api.action_proposal_service import (
    ActionProposalService,
    ProposalConflictError,
    effective_execution_status,
)
from lifeflow_api.deps import ActiveUser, CurrentUser, DbSession
from lifeflow_api.errors import error_response
from lifeflow_api.execution_context import (
    ExecutionContext,
    execution_context_hash,
    resolve_execution_context,
)
from lifeflow_api.google_wiring import build_google_executor_registry
from lifeflow_api.memory_inference import enqueue_recompute
from lifeflow_api.models import (
    ActionExecution,
    ActionProposal,
    ActionType,
    ConnectedAccount,
    ExecutionMode,
    ProposalStatus,
    RiskLevel,
    SourceItem,
    SourceType,
)
from lifeflow_api.preferences import memory_inference_enabled
from lifeflow_api.repositories import (
    ActionExecutionRepository,
    ActionProposalRepository,
    AuditEventRepository,
    ConnectedAccountRepository,
    SourceItemRepository,
)

router = APIRouter(prefix="/action-proposals")


class ProposalEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_item_id: str
    source_ref: str
    source_type: str
    title: str
    sender_or_organiser: str | None
    occurred_at: datetime
    excerpt: str


class ProposalAuditEvent(BaseModel):
    event_type: str
    actor: str
    timestamp: datetime
    safe_metadata: dict[str, Any]


class ExecutionContextView(BaseModel):
    """A safe, minimal projection of `ExecutionContext` for the frontend —
    deliberately omits `connected_account_id`/`source_account_id` and any
    revision counter (raw internal identifiers, independent-review blocker
    #1 §7)."""

    mode: ExecutionMode
    provider: str
    required_scope: str | None


def _execution_context_view(context: ExecutionContext) -> ExecutionContextView:
    return ExecutionContextView(
        mode=context.mode, provider=context.provider, required_scope=context.required_scope
    )


class ApprovalPreview(BaseModel):
    action_type: ActionType
    proposal_version: int
    payload: TypedActionPayload
    payload_hash: str
    binding_hash: str
    approved_at: datetime
    execution_context: ExecutionContextView


class ActionExecutionResponse(BaseModel):
    id: str
    idempotency_key: str
    outcome: str
    # Derived, not just copied: a `pending` outcome older than the staleness
    # threshold reads as `uncertain` here even before anything has
    # persisted that transition (ADR 0003 D16).
    effective_status: str
    # Persisted at creation, never recomputed — a historical record stays
    # truthful even if the user's connected accounts change afterwards
    # (independent-review blocker #3).
    execution_mode: ExecutionMode
    simulation_only: bool
    started_at: datetime
    completed_at: datetime | None
    action_type: ActionType
    proposal_version: int
    executed_payload: TypedActionPayload
    executed_payload_hash: str
    approval_binding_hash: str
    result: dict[str, Any]
    error_code: str | None


class ActionProposalResponse(BaseModel):
    id: str
    origin_fingerprint: str
    action_type: ActionType
    rationale: str
    source_refs: list[str]
    evidence: list[ProposalEvidence]
    payload: TypedActionPayload
    payload_hash: str
    version: int
    risk_level: RiskLevel
    confidence: float
    status: ProposalStatus
    expires_at: datetime
    approval: ApprovalPreview | None
    execution: ActionExecutionResponse | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime
    audit_events: list[ProposalAuditEvent]
    # What executing this proposal right now would actually do — recomputed
    # live from the proposal's evidence provenance and the user's current
    # connected accounts on every read, so it reflects reality even if
    # nothing has executed yet (independent-review blocker #1). Never
    # widened by "any Google account is connected" — bound to the exact
    # source account. `simulation_only` is kept only for API compatibility
    # and is always derived from `execution_mode`, never set independently.
    execution_mode: ExecutionMode
    simulation_only: bool
    execution_context: ExecutionContextView
    execution_context_hash: str
    # Non-null only once approved; lets the frontend compare "what was
    # approved" against `execution_context` above and show a banner instead
    # of silently allowing execution when they differ (blocker #1 §7).
    approved_execution_context: ExecutionContextView | None
    execution_context_changed: bool


class ActionProposalListResponse(BaseModel):
    proposals: list[ActionProposalResponse]
    count: int


class ProposalEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    action_type: ActionType
    payload: TaskCreatePayload | GmailDraftCreatePayload | CalendarEventCreatePayload

    @model_validator(mode="after")
    def payload_matches_action_type(self) -> "ProposalEditRequest":
        parse_action_payload(self.action_type, self.payload)
        return self


class ProposalApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    action_type: ActionType
    displayed_payload_hash: str = Field(min_length=64, max_length=64)
    # The execution-context hash the frontend actually displayed to the
    # user before they clicked approve (Stage 7 remediation blocker #1 §5) —
    # a preview fetched a while ago, or from a stale tab, is rejected with a
    # controlled 409 rather than silently approved against whatever the
    # context happens to be now.
    displayed_execution_context_hash: str = Field(min_length=64, max_length=64)


class ProposalRejectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1_000)


def _evidence(item: SourceItem) -> ProposalEvidence:
    if item.source_type == SourceType.email:
        excerpt = str(item.metadata_json.get("body_preview") or "")
    else:
        excerpt = str(item.metadata_json.get("description") or "")
    return ProposalEvidence(
        source_item_id=str(item.id),
        source_ref=item.external_id,
        source_type=item.source_type,
        title=item.title,
        sender_or_organiser=item.sender_or_organiser,
        occurred_at=item.occurred_at,
        excerpt=excerpt,
    )


def _execution_response(execution: ActionExecution) -> ActionExecutionResponse:
    now = datetime.now(UTC)
    execution_mode = ExecutionMode(execution.execution_mode)
    return ActionExecutionResponse(
        id=str(execution.id),
        idempotency_key=execution.idempotency_key,
        outcome=execution.outcome,
        effective_status=effective_execution_status(execution, now=now),
        execution_mode=execution_mode,
        simulation_only=execution_mode is not ExecutionMode.real,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        action_type=ActionType(execution.approved_action_type),
        proposal_version=execution.approved_proposal_version,
        executed_payload=parse_action_payload(
            ActionType(execution.approved_action_type), execution.executed_payload_json
        ),
        executed_payload_hash=execution.executed_payload_hash,
        approval_binding_hash=execution.approval_binding_hash,
        result=execution.result_json,
        error_code=execution.error_code,
    )


async def _to_response(
    session: DbSession,
    user_id: uuid.UUID,
    proposal: ActionProposal,
    sources: dict[str, SourceItem],
    accounts: list[ConnectedAccount],
) -> ActionProposalResponse:
    await session.refresh(proposal)
    execution = await ActionExecutionRepository(session, user_id).get_by_proposal(proposal.id)
    events = await AuditEventRepository(session, user_id).list_for_entity(
        entity_type="action_proposal", entity_id=str(proposal.id)
    )
    evidence_sources = [sources[ref] for ref in proposal.source_refs if ref in sources]
    current_context = resolve_execution_context(
        ActionType(proposal.action_type), accounts=accounts, evidence_sources=evidence_sources
    )
    execution_mode = current_context.mode
    approval = None
    approved_context_view = None
    context_changed = False
    if (
        proposal.approved_action_type is not None
        and proposal.approved_payload_json is not None
        and proposal.approved_payload_hash is not None
        and proposal.approved_binding_hash is not None
        and proposal.approved_version is not None
        and proposal.approved_at is not None
        and proposal.approved_execution_mode is not None
        and proposal.approved_provider is not None
        and proposal.approved_execution_context_hash is not None
    ):
        approved_type = ActionType(proposal.approved_action_type)
        approved_context_view = ExecutionContextView(
            mode=ExecutionMode(proposal.approved_execution_mode),
            provider=proposal.approved_provider,
            required_scope=proposal.approved_required_scope,
        )
        context_changed = (
            proposal.status == ProposalStatus.approved
            and execution_context_hash(current_context) != proposal.approved_execution_context_hash
        )
        approval = ApprovalPreview(
            action_type=approved_type,
            proposal_version=proposal.approved_version,
            payload=parse_action_payload(approved_type, proposal.approved_payload_json),
            payload_hash=proposal.approved_payload_hash,
            binding_hash=proposal.approved_binding_hash,
            approved_at=proposal.approved_at,
            execution_context=approved_context_view,
        )
    return ActionProposalResponse(
        id=str(proposal.id),
        origin_fingerprint=proposal.origin_fingerprint,
        action_type=ActionType(proposal.action_type),
        rationale=proposal.rationale,
        source_refs=proposal.source_refs,
        evidence=[_evidence(sources[ref]) for ref in proposal.source_refs if ref in sources],
        payload=parse_action_payload(ActionType(proposal.action_type), proposal.payload_json),
        payload_hash=proposal.payload_hash,
        version=proposal.version,
        risk_level=RiskLevel(proposal.risk_level),
        confidence=proposal.confidence,
        status=ProposalStatus(proposal.status),
        expires_at=proposal.expires_at,
        approval=approval,
        execution=_execution_response(execution) if execution else None,
        rejection_reason=proposal.rejection_reason,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        audit_events=[
            ProposalAuditEvent(
                event_type=event.event_type,
                actor=event.actor,
                timestamp=event.timestamp,
                safe_metadata=event.safe_metadata_json,
            )
            for event in events
        ],
        execution_mode=execution_mode,
        simulation_only=execution_mode is not ExecutionMode.real,
        execution_context=_execution_context_view(current_context),
        execution_context_hash=execution_context_hash(current_context),
        approved_execution_context=approved_context_view,
        execution_context_changed=context_changed,
    )


async def _source_map(session: DbSession, user_id: uuid.UUID) -> dict[str, SourceItem]:
    sources = await SourceItemRepository(session, user_id).list(limit=1_000)
    return {source.external_id: source for source in sources}


async def _accounts(session: DbSession, user_id: uuid.UUID) -> list[ConnectedAccount]:
    return await ConnectedAccountRepository(session, user_id).list()


def _conflict_response(exc: ProposalConflictError) -> JSONResponse:
    status_code = 404 if exc.code == "not_found" else 409
    return error_response(status_code, exc.code, exc.message)


@router.get("", response_model=ActionProposalListResponse)
async def list_action_proposals(
    user: CurrentUser,
    session: DbSession,
    status: Annotated[list[ProposalStatus] | None, Query()] = None,
) -> ActionProposalListResponse:
    await ActionProposalService(session, user.id).expire_due()
    proposals = await ActionProposalRepository(session, user.id).list(statuses=status)
    sources = await _source_map(session, user.id)
    accounts = await _accounts(session, user.id)
    responses = [
        await _to_response(session, user.id, proposal, sources, accounts) for proposal in proposals
    ]
    return ActionProposalListResponse(proposals=responses, count=len(responses))


@router.get("/{proposal_id}", response_model=ActionProposalResponse)
async def get_action_proposal(
    proposal_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> ActionProposalResponse | JSONResponse:
    await ActionProposalService(session, user.id).expire_due()
    proposal = await ActionProposalRepository(session, user.id).get(proposal_id)
    if proposal is None:
        return error_response(404, "not_found", "Action proposal not found.")
    return await _to_response(
        session,
        user.id,
        proposal,
        await _source_map(session, user.id),
        await _accounts(session, user.id),
    )


@router.patch("/{proposal_id}", response_model=ActionProposalResponse)
async def edit_action_proposal(
    proposal_id: uuid.UUID,
    body: ProposalEditRequest,
    user: ActiveUser,
    session: DbSession,
) -> ActionProposalResponse | JSONResponse:
    try:
        proposal = await ActionProposalService(session, user.id).edit(
            proposal_id,
            expected_version=body.expected_version,
            action_type=body.action_type,
            payload=body.payload,
        )
    except ProposalConflictError as exc:
        return _conflict_response(exc)
    return await _to_response(
        session,
        user.id,
        proposal,
        await _source_map(session, user.id),
        await _accounts(session, user.id),
    )


@router.post("/{proposal_id}/approve", response_model=ActionProposalResponse)
async def approve_action_proposal(
    request: Request,
    proposal_id: uuid.UUID,
    body: ProposalApprovalRequest,
    user: ActiveUser,
    session: DbSession,
) -> ActionProposalResponse | JSONResponse:
    try:
        proposal = await ActionProposalService(session, user.id).approve(
            proposal_id,
            expected_version=body.expected_version,
            action_type=body.action_type,
            displayed_payload_hash=body.displayed_payload_hash,
            displayed_execution_context_hash=body.displayed_execution_context_hash,
        )
    except ProposalConflictError as exc:
        return _conflict_response(exc)
    # Stage 8 Phase 3 (ADR 0004 D56): a user-edited Gmail draft the user just
    # approved is the one evidence source for inferred memory. Best-effort
    # enqueue a recompute — only when the user has opted in, and never in a
    # way that can fail this approval (Redis down → skipped, self-heals on the
    # next recompute). The worker reloads all state from PostgreSQL.
    if (
        ActionType(proposal.action_type) == ActionType.create_gmail_draft
        and proposal.user_edited_at is not None
        and await memory_inference_enabled(session, user.id)
    ):
        await enqueue_recompute(request.app.state.settings.redis_url, user.id)
    return await _to_response(
        session,
        user.id,
        proposal,
        await _source_map(session, user.id),
        await _accounts(session, user.id),
    )


@router.post("/{proposal_id}/reject", response_model=ActionProposalResponse)
async def reject_action_proposal(
    proposal_id: uuid.UUID,
    body: ProposalRejectionRequest,
    user: CurrentUser,
    session: DbSession,
) -> ActionProposalResponse | JSONResponse:
    try:
        proposal = await ActionProposalService(session, user.id).reject(
            proposal_id,
            expected_version=body.expected_version,
            reason=body.reason,
        )
    except ProposalConflictError as exc:
        return _conflict_response(exc)
    return await _to_response(
        session,
        user.id,
        proposal,
        await _source_map(session, user.id),
        await _accounts(session, user.id),
    )


@router.post("/{proposal_id}/execute", response_model=ActionProposalResponse)
async def execute_action_proposal(
    request: Request, proposal_id: uuid.UUID, user: ActiveUser, session: DbSession
) -> ActionProposalResponse | JSONResponse:
    google_executors = build_google_executor_registry(request, session, user.id)
    # Test-only seam (Stage 7 focused remediation): only ever set directly on
    # `app.state` by the race-test suite, never reachable via any request —
    # `getattr` defaults to `None`, which `ActionProposalService` treats as
    # "no hook" (a plain no-op), so production behaviour is unaffected.
    post_commit_hook = getattr(request.app.state, "action_execution_post_commit_hook", None)
    try:
        proposal, _ = await ActionProposalService(
            session,
            user.id,
            google_executors=google_executors,
            post_commit_hook=post_commit_hook,
        ).execute(proposal_id)
    except ProposalConflictError as exc:
        return _conflict_response(exc)
    return await _to_response(
        session,
        user.id,
        proposal,
        await _source_map(session, user.id),
        await _accounts(session, user.id),
    )


__all__ = [
    "ActionExecutionResponse",
    "ActionProposalListResponse",
    "ActionProposalResponse",
    "ApprovalPreview",
    "ExecutionContextView",
    "ProposalApprovalRequest",
    "ProposalAuditEvent",
    "ProposalEditRequest",
    "ProposalEvidence",
    "ProposalRejectionRequest",
    "router",
]
