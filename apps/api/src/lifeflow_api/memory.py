"""Owner-scoped Stage 8 Phase 3 inferred-memory API (ADR 0004 D55/D58).

A narrow surface over `memory_items`: list what LifeFlow has learned, and let
the user confirm, edit-and-confirm, dismiss, delete one, or delete all. The
whole feature is subordinate to explicit preferences and can never approve or
execute anything:

- **confirm** / **edit** write the explicit `preferred_email_signoff`
  preference (the only channel through which inferred memory affects a draft,
  D57) and mark the item `confirmed`;
- **dismiss** is sticky by evidence fingerprint (D55);
- **delete** erases the derived item and its evidence (a privacy control) but
  never touches the source proposals — the Settings copy says so.

Every response exposes only safe fields: the short sign-off token, confidence
(number + band), evidence count, timestamps, and a plain-language explanation —
never a draft body, recipient, token, or provider secret.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from lifeflow_api.audit import record_audit_event
from lifeflow_api.deps import CurrentUser, DbSession
from lifeflow_api.errors import error_response
from lifeflow_api.memory_inference import expire_stale_candidates
from lifeflow_api.memory_registry import (
    MEMORY_REGISTRY,
    confidence_band,
    effective_confidence,
    evidence_fingerprint,
)
from lifeflow_api.models import MemoryEvidence, MemoryItem, MemoryStatus, Preference, Provenance
from lifeflow_api.preferences import (
    PREFERRED_EMAIL_SIGNOFF_KEY,
    PreferredEmailSignoffValue,
    explicit_signoff,
    memory_inference_enabled,
    validate_preference_value,
)
from lifeflow_api.repositories import (
    MemoryEvidenceRepository,
    MemoryItemRepository,
    PreferenceRepository,
)

router = APIRouter(prefix="/memories")

# Statuses from which a user may still act on a candidate. `confirmed` is
# terminal for confirm; `expired` requires fresh evidence to reconsider.
_CONFIRMABLE = frozenset({MemoryStatus.candidate, MemoryStatus.superseded})
_DISMISSIBLE = frozenset({MemoryStatus.candidate, MemoryStatus.superseded})


class MemoryEvidenceView(BaseModel):
    """A safe evidence summary — the normalised token and a reason code only,
    never a draft body (D53)."""

    evidence_type: str
    derived_value: str
    reason_code: str
    observed_at: datetime
    source_proposal_id: str | None


class MemoryItemView(BaseModel):
    id: str
    memory_key: str
    value: dict[str, object]
    status: MemoryStatus
    confidence: float
    confidence_band: str
    evidence_count: int
    first_observed_at: datetime | None
    last_observed_at: datetime | None
    last_evaluated_at: datetime | None
    expires_at: datetime | None
    application_mode: str
    corresponding_preference_key: str | None
    # True only when this is a confirmed memory whose value equals the current
    # explicit preference — i.e. it is what a new draft would actually use.
    applied: bool
    overridden_by_explicit: bool
    explanation: str
    version: int
    updated_at: datetime
    evidence: list[MemoryEvidenceView]


class MemoryListResponse(BaseModel):
    memories: list[MemoryItemView]
    count: int
    # Whether inference is currently paused (default off) — the Settings
    # toggle reads this rather than digging through the preference list.
    inference_enabled: bool


class MemoryVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class MemoryEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    value: str = Field(min_length=1, max_length=60)


class MemoryConflictError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _conflict_response(exc: MemoryConflictError) -> JSONResponse:
    status_code = 404 if exc.code == "not_found" else 409
    return error_response(status_code, exc.code, exc.message)


def _current_fingerprint(item: MemoryItem, evidence: list[MemoryEvidence]) -> str:
    """The evidence fingerprint for the item's current dominant value —
    recomputed from stored evidence so it matches what `evaluate_observations`
    produces (dismissal stickiness compares against it, D55)."""
    value = str(item.value_json.get("value", ""))
    agreeing = [ev.source_proposal_id for ev in evidence if ev.derived_value == value]
    return evidence_fingerprint(value, agreeing)


def _to_view(
    item: MemoryItem,
    evidence: list[MemoryEvidence],
    *,
    explicit_value: str | None,
    now: datetime,
) -> MemoryItemView:
    value = str(item.value_json.get("value", ""))
    spec = MEMORY_REGISTRY.get(item.memory_key)
    explanation = (
        spec.explanation(value, item.evidence_count)
        if spec is not None
        else "LifeFlow inferred this from your recent activity."
    )
    applied = (
        item.status == MemoryStatus.confirmed
        and explicit_value is not None
        and explicit_value == value
    )
    # A candidate keeps decaying with time alone, so the confidence the API and
    # UI show is the *effective* value as of now — not the frozen last-recompute
    # value (ADR 0004 D54). Non-candidate states (confirmed/expired/…) show
    # their stored value, which does not decay.
    display_confidence = (
        effective_confidence(item.confidence, item.last_evaluated_at, now)
        if item.status == MemoryStatus.candidate
        else item.confidence
    )
    return MemoryItemView(
        id=str(item.id),
        memory_key=item.memory_key,
        value=dict(item.value_json),
        status=MemoryStatus(item.status),
        confidence=display_confidence,
        confidence_band=confidence_band(display_confidence),
        evidence_count=item.evidence_count,
        first_observed_at=item.first_observed_at,
        last_observed_at=item.last_observed_at,
        last_evaluated_at=item.last_evaluated_at,
        expires_at=item.expires_at,
        application_mode=item.application_mode,
        corresponding_preference_key=item.corresponding_preference_key,
        applied=applied,
        overridden_by_explicit=item.overridden_by_explicit,
        explanation=explanation,
        version=item.version,
        updated_at=item.updated_at,
        evidence=[
            MemoryEvidenceView(
                evidence_type=ev.evidence_type,
                derived_value=ev.derived_value,
                reason_code=ev.reason_code,
                observed_at=ev.observed_at,
                source_proposal_id=(
                    str(ev.source_proposal_id) if ev.source_proposal_id is not None else None
                ),
            )
            for ev in evidence
        ],
    )


class MemoryService:
    def __init__(self, session: DbSession, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id
        self._items = MemoryItemRepository(session, user_id)
        self._evidence = MemoryEvidenceRepository(session, user_id)

    def _audit(self, item: MemoryItem, event_type: str, *, actor: str, include_value: bool) -> None:
        metadata: dict[str, object] = {
            "memory_key": item.memory_key,
            "status": str(item.status),
            "evidence_count": item.evidence_count,
            "confidence_band": confidence_band(item.confidence),
        }
        if include_value:
            metadata["value"] = str(item.value_json.get("value", ""))
        record_audit_event(
            self._session,
            user_id=self._user_id,
            actor=actor,
            event_type=event_type,
            entity_type="memory_item",
            entity_id=str(item.id),
            metadata=metadata,
        )

    async def _write_explicit_signoff(self, value: str) -> None:
        """Promote a confirmed sign-off to an explicit preference with normal
        explicit authority (D55) — the one place inferred memory becomes
        applicable, and it does so through the ordinary preference registry,
        not a second competing system."""
        canonical = validate_preference_value(PREFERRED_EMAIL_SIGNOFF_KEY, {"value": value})
        repo = PreferenceRepository(self._session, self._user_id)
        existing = await repo.get(PREFERRED_EMAIL_SIGNOFF_KEY)
        if existing is None:
            repo.add(
                Preference(
                    user_id=self._user_id,
                    key=PREFERRED_EMAIL_SIGNOFF_KEY,
                    value_json=canonical,
                    provenance=Provenance.explicit,
                    confidence=None,
                )
            )
        else:
            existing.value_json = canonical
            existing.provenance = Provenance.explicit
            existing.confidence = None
        record_audit_event(
            self._session,
            user_id=self._user_id,
            actor=f"user:{self._user_id}",
            event_type="preference.updated",
            entity_type="preference",
            entity_id=PREFERRED_EMAIL_SIGNOFF_KEY,
            metadata={
                "key": PREFERRED_EMAIL_SIGNOFF_KEY,
                "provenance": str(Provenance.explicit),
                "value": canonical,
            },
        )

    async def _load(self, item_id: uuid.UUID, *, expected_version: int) -> MemoryItem:
        item = await self._items.get(item_id, for_update=True)
        if item is None:
            raise MemoryConflictError("not_found", "Memory not found.")
        if item.version != expected_version:
            raise MemoryConflictError(
                "stale_version", "The memory changed; reload the current version."
            )
        return item

    async def confirm(
        self, item_id: uuid.UUID, *, expected_version: int, value: str | None = None
    ) -> MemoryItem:
        item = await self._load(item_id, expected_version=expected_version)
        if MemoryStatus(item.status) not in _CONFIRMABLE:
            raise MemoryConflictError("invalid_transition", "This memory cannot be confirmed.")
        edited = value is not None
        confirmed_value = value if edited else str(item.value_json.get("value", ""))
        # Validate (also normalises) — the same rule whether the user accepts
        # the inferred value or edits it, so a confirmed memory can never write
        # an unsafe sign-off.
        canonical = PreferredEmailSignoffValue.model_validate({"value": confirmed_value})
        confirmed_value = canonical.value
        item.value_json = {"value": confirmed_value}
        await self._write_explicit_signoff(confirmed_value)
        item.status = MemoryStatus.confirmed
        item.overridden_by_explicit = False
        item.version += 1
        self._audit(
            item,
            "memory.edited" if edited else "memory.confirmed",
            actor=f"user:{self._user_id}",
            include_value=True,
        )
        await self._session.flush()
        return item

    async def dismiss(
        self, item_id: uuid.UUID, *, expected_version: int, now: datetime
    ) -> MemoryItem:
        item = await self._load(item_id, expected_version=expected_version)
        if MemoryStatus(item.status) not in _DISMISSIBLE:
            raise MemoryConflictError("invalid_transition", "This memory cannot be dismissed.")
        evidence = await self._evidence.list_for_item(item.id)
        item.status = MemoryStatus.dismissed
        item.dismissed_at = now
        item.dismissed_fingerprint = _current_fingerprint(item, evidence)
        item.version += 1
        self._audit(item, "memory.dismissed", actor=f"user:{self._user_id}", include_value=False)
        await self._session.flush()
        return item

    async def delete(self, item_id: uuid.UUID) -> None:
        item = await self._items.get(item_id, for_update=True)
        if item is None:
            raise MemoryConflictError("not_found", "Memory not found.")
        # Record the fact and key only — never the deleted value (D58).
        self._audit(item, "memory.deleted", actor=f"user:{self._user_id}", include_value=False)
        await self._items.delete(item)
        await self._session.flush()

    async def delete_all(self) -> int:
        items = await self._items.list()
        for item in items:
            self._audit(item, "memory.deleted", actor=f"user:{self._user_id}", include_value=False)
        count = await self._items.delete_all()
        await self._session.flush()
        return count


@router.get("", response_model=MemoryListResponse)
async def list_memories(user: CurrentUser, session: DbSession) -> MemoryListResponse:
    now = datetime.now(UTC)
    # Expire decayed candidates on read (like the proposals list expires due
    # proposals) so the API/UI never present a stale candidate as active — a
    # safe, idempotent, audited-once transition (ADR 0004 D54).
    await expire_stale_candidates(session, user.id, now=now)
    items = await MemoryItemRepository(session, user.id).list()
    explicit_value = await explicit_signoff(session, user.id)
    evidence_repo = MemoryEvidenceRepository(session, user.id)
    views: list[MemoryItemView] = []
    for item in items:
        evidence = await evidence_repo.list_for_item(item.id)
        views.append(_to_view(item, evidence, explicit_value=explicit_value, now=now))
    return MemoryListResponse(
        memories=views,
        count=len(views),
        inference_enabled=await memory_inference_enabled(session, user.id),
    )


async def _item_response(
    session: DbSession, user_id: uuid.UUID, item: MemoryItem
) -> MemoryItemView:
    # Load server-defaulted/onupdate columns eagerly within the async context —
    # a just-mutated item's `updated_at` is otherwise expired and would
    # lazy-load (MissingGreenlet) during synchronous serialization.
    await session.refresh(item)
    evidence = await MemoryEvidenceRepository(session, user_id).list_for_item(item.id)
    explicit_value = await explicit_signoff(session, user_id)
    return _to_view(item, evidence, explicit_value=explicit_value, now=datetime.now(UTC))


@router.get("/{memory_id}", response_model=MemoryItemView)
async def get_memory(
    memory_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> MemoryItemView | JSONResponse:
    await expire_stale_candidates(session, user.id, now=datetime.now(UTC))
    item = await MemoryItemRepository(session, user.id).get(memory_id)
    if item is None:
        return error_response(404, "not_found", "Memory not found.")
    return await _item_response(session, user.id, item)


@router.post("/{memory_id}/confirm", response_model=MemoryItemView)
async def confirm_memory(
    memory_id: uuid.UUID, body: MemoryVersionRequest, user: CurrentUser, session: DbSession
) -> MemoryItemView | JSONResponse:
    try:
        item = await MemoryService(session, user.id).confirm(
            memory_id, expected_version=body.expected_version
        )
    except MemoryConflictError as exc:
        return _conflict_response(exc)
    return await _item_response(session, user.id, item)


@router.put("/{memory_id}", response_model=MemoryItemView)
async def edit_memory(
    memory_id: uuid.UUID, body: MemoryEditRequest, user: CurrentUser, session: DbSession
) -> MemoryItemView | JSONResponse:
    try:
        item = await MemoryService(session, user.id).confirm(
            memory_id, expected_version=body.expected_version, value=body.value
        )
    except MemoryConflictError as exc:
        return _conflict_response(exc)
    except ValueError as exc:
        return error_response(422, "validation_error", str(exc))
    return await _item_response(session, user.id, item)


@router.post("/{memory_id}/dismiss", response_model=MemoryItemView)
async def dismiss_memory(
    memory_id: uuid.UUID, body: MemoryVersionRequest, user: CurrentUser, session: DbSession
) -> MemoryItemView | JSONResponse:
    try:
        item = await MemoryService(session, user.id).dismiss(
            memory_id, expected_version=body.expected_version, now=datetime.now(UTC)
        )
    except MemoryConflictError as exc:
        return _conflict_response(exc)
    return await _item_response(session, user.id, item)


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> JSONResponse:
    try:
        await MemoryService(session, user.id).delete(memory_id)
    except MemoryConflictError as exc:
        return _conflict_response(exc)
    return JSONResponse(status_code=200, content={"deleted": 1})


@router.delete("")
async def delete_all_memories(user: CurrentUser, session: DbSession) -> JSONResponse:
    count = await MemoryService(session, user.id).delete_all()
    return JSONResponse(status_code=200, content={"deleted": count})


__all__ = [
    "MemoryConflictError",
    "MemoryItemView",
    "MemoryListResponse",
    "MemoryService",
    "router",
]
