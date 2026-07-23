"""Privacy deletion API — imported-data deletion, account deletion, and the
durable-operation status surface (Stage 9 Delivery Phase 2, ADR 0005).

Owner-scoped throughout. A confirmed operation is persisted as `pending`; the
worker's per-minute cron drains pending operations and runs them — so the API
has no Redis dependency and a queue outage never blocks preview/confirm (the
operation truthfully reports `pending` until it is drained).

Responses are content-free: operation id, type, a safe scope label, state,
version, preview expiry, count summaries, warnings, safe error code, and
timestamps — never the resume cursor, raw scope JSON, queue ids, stack traces,
or any personal/provider content.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from lifeflow_api.config import Settings
from lifeflow_api.correlation import get_correlation_id
from lifeflow_api.deletion import (
    cancel_operation,
    confirm_operation,
    create_account_deletion_preview,
    create_imported_data_preview,
)
from lifeflow_api.deletion_ops import (
    CONFIRM_ACCOUNT,
    CONFIRM_IMPORTED_DATA,
    DataDeletionOperationRepository,
    DeletionOperationNotFoundError,
    InvalidConfirmationError,
    InvalidDeletionStateError,
    PreviewChangedError,
    PreviewExpiredError,
    StaleDeletionVersionError,
)
from lifeflow_api.deps import CurrentUser, DbSession
from lifeflow_api.errors import error_response
from lifeflow_api.models import (
    TERMINAL_DELETION_STATES,
    DataDeletionOperation,
    DeletionConfirmationKind,
    DeletionOperationState,
    DeletionOperationType,
)

router = APIRouter(prefix="/privacy")

_SCOPE_LABELS: dict[str, str] = {
    DeletionOperationType.account_deletion: "Your LifeFlow account",
    DeletionOperationType.retention: "Scheduled retention",
}
_WARNINGS: dict[str, list[str]] = {
    DeletionOperationType.imported_data: [
        "This deletes only LifeFlow's imported copy — your Gmail and Google "
        "Calendar content is never touched.",
        "Actions you already approved or that ran are kept as content-free "
        "history; unresolved or pending outcomes are always preserved.",
    ],
    DeletionOperationType.account_deletion: [
        "Your LifeFlow sign-in will stop working and this cannot be undone.",
        "Your Gmail and Google Calendar content is never deleted.",
        "Content-free trust records may remain for integrity and to reconcile "
        "any unresolved external action.",
    ],
    DeletionOperationType.retention: [],
}
_CONFIRMATION_PHRASE: dict[str, str] = {
    DeletionConfirmationKind.delete_imported_data: CONFIRM_IMPORTED_DATA,
    DeletionConfirmationKind.delete_account: CONFIRM_ACCOUNT,
}


class DeletionOperationView(BaseModel):
    operation_id: str
    operation_type: str
    scope_label: str
    state: str
    version: int
    requester_type: str
    confirmation_phrase: str | None  # the exact phrase the UI must require
    preview_expires_at: datetime | None
    preview_counts: dict[str, int]
    preserved_counts: dict[str, int]
    deleted_counts: dict[str, int]
    warnings: list[str]
    is_terminal: bool
    in_progress: bool
    safe_error_code: str | None
    created_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None


class ConfirmRequest(BaseModel):
    expected_version: int
    confirmation_phrase: str


class DeletionOperationsResponse(BaseModel):
    operations: list[DeletionOperationView]


def _scope_label(operation: DataDeletionOperation) -> str:
    if operation.operation_type == DeletionOperationType.imported_data:
        provider = (operation.scope_json or {}).get("provider", "provider")
        return f"Imported {provider} data"
    return _SCOPE_LABELS.get(operation.operation_type, "Deletion")


def _view(operation: DataDeletionOperation) -> DeletionOperationView:
    phrase = (
        _CONFIRMATION_PHRASE.get(operation.typed_confirmation_kind)
        if operation.typed_confirmation_kind
        else None
    )
    return DeletionOperationView(
        operation_id=str(operation.id),
        operation_type=operation.operation_type,
        scope_label=_scope_label(operation),
        state=operation.state,
        version=operation.version,
        requester_type=operation.requester_type,
        confirmation_phrase=phrase,
        preview_expires_at=operation.preview_expires_at,
        preview_counts=dict(operation.preview_counts_json or {}),
        preserved_counts=dict(operation.preserved_counts_json or {}),
        deleted_counts=dict(operation.deleted_counts_json or {}),
        warnings=_WARNINGS.get(operation.operation_type, []),
        is_terminal=operation.state in TERMINAL_DELETION_STATES,
        in_progress=operation.state
        in (DeletionOperationState.pending, DeletionOperationState.running),
        safe_error_code=operation.safe_error_code,
        created_at=operation.created_at,
        started_at=operation.started_at,
        completed_at=operation.completed_at,
    )


def _not_found() -> JSONResponse:
    # 404 without ownership leakage — identical whether the operation is
    # another user's or does not exist.
    return error_response(404, "not_found", "No such deletion operation.")


@router.post("/imported-data/{account_id}/preview", response_model=DeletionOperationView)
async def preview_imported_data_deletion(
    account_id: uuid.UUID, request: Request, user: CurrentUser, session: DbSession
) -> DeletionOperationView | JSONResponse:
    settings: Settings = request.app.state.settings
    now = datetime.now(UTC)
    try:
        operation = await create_imported_data_preview(
            session,
            user,
            source_account_id=account_id,
            now=now,
            ttl_minutes=settings.deletion_preview_ttl_minutes,
        )
    except DeletionOperationNotFoundError:
        return _not_found()
    return _view(operation)


@router.post("/account-deletion/preview", response_model=DeletionOperationView)
async def preview_account_deletion(
    request: Request, user: CurrentUser, session: DbSession
) -> DeletionOperationView:
    settings: Settings = request.app.state.settings
    now = datetime.now(UTC)
    operation = await create_account_deletion_preview(
        session, user, now=now, ttl_minutes=settings.deletion_preview_ttl_minutes
    )
    return _view(operation)


@router.post("/deletion-operations/{operation_id}/confirm", response_model=DeletionOperationView)
async def confirm_deletion_operation(
    operation_id: uuid.UUID,
    body: ConfirmRequest,
    request: Request,
    user: CurrentUser,
    session: DbSession,
) -> DeletionOperationView | JSONResponse:
    settings: Settings = request.app.state.settings
    now = datetime.now(UTC)
    try:
        operation = await confirm_operation(
            session,
            user,
            operation_id,
            expected_version=body.expected_version,
            phrase=body.confirmation_phrase,
            now=now,
            preview_ttl_minutes=settings.deletion_preview_ttl_minutes,
        )
    except DeletionOperationNotFoundError:
        return _not_found()
    except PreviewChangedError:
        # The plan changed since review — the preview has been refreshed. Return
        # the refreshed operation so the client can re-review and re-confirm.
        refreshed = await DataDeletionOperationRepository(session, user.id).get(operation_id)
        detail = (
            "What would be deleted changed since you reviewed it; review the refreshed preview."
        )
        if refreshed is None:  # pragma: no cover - just confirmed to exist
            return error_response(409, "preview_changed", detail)
        payload = _view(refreshed).model_dump(mode="json")
        payload["error"] = {
            "code": "preview_changed",
            "message": detail,
            "correlation_id": get_correlation_id(),
        }
        return JSONResponse(status_code=409, content=payload)
    except (InvalidDeletionStateError, PreviewExpiredError) as exc:
        return error_response(409, "invalid_operation_state", str(exc))
    except StaleDeletionVersionError as exc:
        return error_response(409, "stale_version", str(exc))
    except InvalidConfirmationError as exc:
        return error_response(422, "invalid_confirmation", str(exc))
    return _view(operation)


@router.post("/deletion-operations/{operation_id}/cancel", response_model=DeletionOperationView)
async def cancel_deletion_operation(
    operation_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> DeletionOperationView | JSONResponse:
    now = datetime.now(UTC)
    try:
        operation = await cancel_operation(session, user, operation_id, now=now)
    except DeletionOperationNotFoundError:
        return _not_found()
    except InvalidDeletionStateError as exc:
        return error_response(409, "invalid_operation_state", str(exc))
    return _view(operation)


@router.get("/deletion-operations", response_model=DeletionOperationsResponse)
async def list_deletion_operations(
    user: CurrentUser, session: DbSession
) -> DeletionOperationsResponse:
    operations = await DataDeletionOperationRepository(session, user.id).list()
    return DeletionOperationsResponse(operations=[_view(op) for op in operations])


@router.get("/deletion-operations/{operation_id}", response_model=DeletionOperationView)
async def get_deletion_operation(
    operation_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> DeletionOperationView | JSONResponse:
    operation = await DataDeletionOperationRepository(session, user.id).get(operation_id)
    if operation is None:
        return _not_found()
    return _view(operation)


__all__ = ["router"]
