"""Shared vocabulary and persistence for the durable deletion engine
(Stage 9 Delivery Phase 2, ADR 0005).

Kept dependency-light (models only) so every other engine module — planner,
previews, account-deletion, retention, the run dispatcher, and the worker glue
— can import the same constants, typed errors, scope-key rule, and repository
without an import cycle.
"""

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.models import (
    ACTIVE_DELETION_STATES,
    DataDeletionOperation,
    DeletionConfirmationKind,
    DeletionOperationType,
)

# --- typed confirmation phrases (exact match required; never stored) --------
CONFIRM_IMPORTED_DATA = "DELETE IMPORTED DATA"
CONFIRM_ACCOUNT = "DELETE MY LIFEFLOW ACCOUNT"

_PHRASE_FOR_KIND: dict[str, str] = {
    DeletionConfirmationKind.delete_imported_data: CONFIRM_IMPORTED_DATA,
    DeletionConfirmationKind.delete_account: CONFIRM_ACCOUNT,
}


def expected_phrase(confirmation_kind: str | None) -> str | None:
    if confirmation_kind is None:
        return None
    return _PHRASE_FOR_KIND.get(confirmation_kind)


# --- closed-vocabulary safe error codes (never a stack trace or content) ----
ERROR_WORKER_STALE_TIMEOUT = "worker_stale_timeout"
ERROR_MAX_ATTEMPTS = "max_attempts_exhausted"
ERROR_PROVIDER_REVOKE_FAILED = "provider_revoke_failed"
ERROR_DATABASE_UNAVAILABLE = "database_unavailable"
ERROR_INTERNAL = "internal_error"

# The arq job function name (see worker_app.py). The queue payload is only the
# operation id — never scope, counts, confirmation text, or personal data.
JOB_FUNCTION_NAME = "run_deletion_operation"


def job_serializer(data: Any) -> bytes:
    """JSON, never pickle (skill security requirement) — this queue never
    deserializes pickle regardless of what is placed on it."""
    return json.dumps(data, default=str).encode("utf-8")


def job_deserializer(data: bytes) -> Any:
    return json.loads(data.decode("utf-8"))


def scope_key_for(
    operation_type: str,
    *,
    source_account_id: uuid.UUID | None = None,
    retention_bucket: str | None = None,
) -> str:
    """The deterministic scope descriptor the partial unique index uses to
    guarantee at most one active operation per (user, type, scope)."""
    if operation_type == DeletionOperationType.imported_data:
        if source_account_id is None:
            raise ValueError("imported_data scope requires a source_account_id")
        return f"account:{source_account_id}"
    if operation_type == DeletionOperationType.account_deletion:
        return "account"
    if operation_type == DeletionOperationType.retention:
        if retention_bucket is None:
            raise ValueError("retention scope requires a retention_bucket")
        return f"retention:{retention_bucket}"
    raise ValueError(f"unknown operation_type {operation_type!r}")


# --- typed errors the API layer maps to HTTP statuses -----------------------
class DeletionOperationNotFoundError(Exception):
    """No such operation for this owner (mapped to 404 without leakage)."""


class InvalidDeletionStateError(Exception):
    """The operation is not in a state that permits this transition (409)."""


class StaleDeletionVersionError(Exception):
    """The confirmation carried a version the operation has moved past (409)."""


class PreviewExpiredError(Exception):
    """The preview's confirmation window has closed (409)."""


class PreviewChangedError(Exception):
    """The plan changed materially since the preview was reviewed; it has been
    refreshed and a new confirmation is required (409 preview_changed)."""


class InvalidConfirmationError(Exception):
    """The typed confirmation phrase did not match exactly (422)."""


class DataDeletionOperationRepository:
    """Owner-scoped access to durable deletion operations (threat model T2).
    Cross-user recovery (worker/cron) uses the unscoped module functions in
    `deletion.py`, never this repository."""

    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id

    def add(self, operation: DataDeletionOperation) -> None:
        if operation.user_id != self._user_id:
            raise ValueError("operation does not belong to this user")
        self._session.add(operation)

    async def get(self, operation_id: uuid.UUID) -> DataDeletionOperation | None:
        result = await self._session.execute(
            select(DataDeletionOperation).where(
                DataDeletionOperation.id == operation_id,
                DataDeletionOperation.user_id == self._user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active(self, operation_type: str, scope_key: str) -> DataDeletionOperation | None:
        result = await self._session.execute(
            select(DataDeletionOperation).where(
                DataDeletionOperation.user_id == self._user_id,
                DataDeletionOperation.operation_type == operation_type,
                DataDeletionOperation.scope_key == scope_key,
                DataDeletionOperation.state.in_(ACTIVE_DELETION_STATES),
            )
        )
        return result.scalar_one_or_none()

    async def list(self) -> list[DataDeletionOperation]:
        result = await self._session.execute(
            select(DataDeletionOperation)
            .where(DataDeletionOperation.user_id == self._user_id)
            .order_by(DataDeletionOperation.created_at.desc())
        )
        return list(result.scalars().all())


__all__ = [
    "CONFIRM_ACCOUNT",
    "CONFIRM_IMPORTED_DATA",
    "ERROR_DATABASE_UNAVAILABLE",
    "ERROR_INTERNAL",
    "ERROR_MAX_ATTEMPTS",
    "ERROR_PROVIDER_REVOKE_FAILED",
    "ERROR_WORKER_STALE_TIMEOUT",
    "JOB_FUNCTION_NAME",
    "DataDeletionOperationRepository",
    "DeletionOperationNotFoundError",
    "InvalidConfirmationError",
    "InvalidDeletionStateError",
    "PreviewChangedError",
    "PreviewExpiredError",
    "StaleDeletionVersionError",
    "expected_phrase",
    "job_deserializer",
    "job_serializer",
    "scope_key_for",
]
