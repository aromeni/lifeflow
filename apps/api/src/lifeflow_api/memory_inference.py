"""Stage 8 Phase 3: the inferred-memory recompute lifecycle (ADR 0004 D53-D58).

Everything that decides *what LifeFlow has learned* lives here as plain,
pytest-covered functions — never in the thin arq glue in `worker_app.py`.
`recompute_user_memory` is pure database logic (no Redis), takes an explicit
`now`, and is fully testable with a controllable clock and deterministic
evidence fixtures.

Safety by construction:
- evidence is only the user's own edited-then-approved Gmail-draft proposals
  (`gather_signoff_observations`) — inbound `SourceItem` content is never read,
  so a phrase in a received email can never become a preference (skill §11.1);
- the derived value is composed from the closed sign-off vocabulary
  (`extract_signoff`), never from arbitrary text; only the short token is
  stored, never the draft body (D53);
- confidence is arithmetic over evidence rows (`evaluate_observations`), never
  a model score;
- inferred memory is suggest-only: it is never read by the composer. It can
  affect an outgoing draft only after the user *confirms* it, which writes the
  explicit `preferred_email_signoff` preference (D55/D57 — see `memory.py`).
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from arq.connections import RedisSettings, create_pool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.audit import record_audit_event
from lifeflow_api.memory_registry import (
    CONFIDENCE_EXPIRY_FLOOR,
    EVIDENCE_TYPE_SIGNOFF,
    PREFERRED_EMAIL_SIGNOFF_KEY,
    REASON_APPROVED_EDITED_DRAFT,
    Observation,
    confidence_band,
    effective_confidence,
    evaluate_observations,
    extract_signoff,
    require_spec,
)
from lifeflow_api.models import (
    ActionType,
    MemoryEvidence,
    MemoryItem,
    MemoryStatus,
    ProposalStatus,
)
from lifeflow_api.preferences import (
    explicit_signoff,
    memory_inference_enabled,
)
from lifeflow_api.repositories import (
    ActionProposalRepository,
    MemoryEvidenceRepository,
    MemoryItemRepository,
)
from lifeflow_api.scheduled_briefs import job_deserializer, job_serializer

logger = logging.getLogger(__name__)

# The arq function name the API enqueues and the worker registers (D56). An
# internal identifier only — the payload is a user id, never draft content.
JOB_FUNCTION_NAME = "recompute_user_memory"

# The proposal statuses that count as "the user approved this edited draft"
# (D53). A rejected or still-proposed draft is not evidence of a preference;
# only a draft the user deliberately edited AND then approved is.
_EVIDENCE_PROPOSAL_STATUSES: list[ProposalStatus] = [
    ProposalStatus.approved,
    ProposalStatus.executing,
    ProposalStatus.executed,
]

# How many recent eligible proposals a recompute rescans. Bounded so the job
# is cheap; the rescan (rather than trusting a single enqueue event) is what
# makes a missed enqueue self-heal on the next recompute (D56).
_RESCAN_LIMIT = 100


@dataclass(frozen=True)
class RecomputeResult:
    """The outcome of one recompute — safe to log (no draft content)."""

    paused: bool = False
    observations: int = 0
    status: str | None = None
    created: bool = False
    updated: bool = False
    evidence_added: int = 0


async def gather_signoff_observations(
    session: AsyncSession, user_id: uuid.UUID
) -> list[Observation]:
    """The user's own edited-then-approved Gmail drafts, reduced to recognised
    sign-off observations (D53). Reads only each proposal's own payload body —
    never a `SourceItem`, so inbound email can never contribute."""
    proposals = await ActionProposalRepository(session, user_id).list_user_edited_by_type(
        action_type=str(ActionType.create_gmail_draft),
        statuses=_EVIDENCE_PROPOSAL_STATUSES,
        limit=_RESCAN_LIMIT,
    )
    observations: list[Observation] = []
    for proposal in proposals:
        # The edited draft the user approved is the authoritative payload.
        body = str(proposal.payload_json.get("body", ""))
        signoff = extract_signoff(body)
        if signoff is None:
            continue
        observed_at = proposal.user_edited_at or proposal.updated_at
        observations.append(
            Observation(
                source_proposal_id=proposal.id,
                value=signoff,
                observed_at=observed_at,
            )
        )
    return observations


def _audit_memory(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    event_type: str,
    item: MemoryItem,
    include_value: bool = True,
) -> None:
    metadata: dict[str, object] = {
        "memory_key": item.memory_key,
        "status": str(item.status),
        "evidence_count": item.evidence_count,
        "confidence_band": confidence_band(item.confidence),
    }
    if include_value:
        # The short normalised sign-off token — configuration-like and safe,
        # exactly as preference values are audited whole (D58).
        metadata["value"] = str(item.value_json.get("value", ""))
    record_audit_event(
        session,
        user_id=user_id,
        actor="system:memory",
        event_type=event_type,
        entity_type="memory_item",
        entity_id=str(item.id),
        metadata=metadata,
    )


async def _record_evidence(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    item: MemoryItem,
    observations: list[Observation],
) -> int:
    """Insert one evidence row per contributing proposal not already recorded
    — idempotent by the `(memory_item_id, source_proposal_id)` unique
    constraint (D56). Stores only the normalised token and a reason code."""
    evidence_repo = MemoryEvidenceRepository(session, user_id)
    already = await evidence_repo.existing_proposal_ids(item.id)
    added = 0
    for observation in observations:
        if observation.source_proposal_id is None or observation.source_proposal_id in already:
            continue
        evidence = MemoryEvidence(
            memory_item_id=item.id,
            user_id=user_id,
            evidence_type=EVIDENCE_TYPE_SIGNOFF,
            source_proposal_id=observation.source_proposal_id,
            observed_at=observation.observed_at,
            derived_value=observation.value,
            reason_code=REASON_APPROVED_EDITED_DRAFT,
        )
        try:
            async with session.begin_nested():
                evidence_repo.add(evidence)
                await session.flush()
        except IntegrityError:
            # A concurrent recompute already recorded this proposal — the
            # unique constraint is the final guard; skip it (test: concurrent
            # inference creates one evidence set).
            continue
        already.add(observation.source_proposal_id)
        added += 1
    return added


async def recompute_user_memory(
    session: AsyncSession, user_id: uuid.UUID, *, now: datetime
) -> RecomputeResult:
    """Idempotently reconcile the user's inferred memory with their current
    evidence (ADR 0004 D53-D58). Best-effort and recoverable: a missed enqueue
    self-heals here because this rescans recent proposals rather than trusting
    a single event. Never approves or executes anything.

    Skipped entirely when inference is paused (`memory_inference_enabled` off).
    """
    if not await memory_inference_enabled(session, user_id):
        return RecomputeResult(paused=True)

    spec = require_spec(PREFERRED_EMAIL_SIGNOFF_KEY)
    observations = await gather_signoff_observations(session, user_id)
    repo = MemoryItemRepository(session, user_id)
    existing = await repo.get_by_key(PREFERRED_EMAIL_SIGNOFF_KEY, for_update=True)

    result = evaluate_observations(observations, now=now)
    if result is None:
        # No qualifying evidence at all. A confirmed item keeps its explicit
        # preference regardless; a bare candidate with no basis is left as-is
        # (it will expire by confidence floor once evidence is present again).
        return RecomputeResult(
            observations=0, status=str(existing.status) if existing is not None else None
        )

    # An explicit preference for the same fact always wins (D55). `None` means
    # the user has never set one (only the system default is in force).
    explicit_value = await explicit_signoff(session, user_id)

    created = False
    if existing is None:
        item = MemoryItem(
            user_id=user_id,
            memory_key=PREFERRED_EMAIL_SIGNOFF_KEY,
            value_json={"value": result.value},
            status=MemoryStatus.candidate,
            confidence=result.confidence,
            evidence_count=result.evidence_count,
            first_observed_at=result.first_observed_at,
            last_observed_at=result.last_observed_at,
            last_evaluated_at=now,
            application_mode=spec.application_mode,
            corresponding_preference_key=spec.corresponding_preference_key,
            overridden_by_explicit=False,
            version=1,
        )
        try:
            async with session.begin_nested():
                repo.add(item)
                await session.flush()
        except IntegrityError:
            # A concurrent recompute created it first — the `(user_id,
            # memory_key)` unique constraint is the final guard. Fall through
            # to the update path against the winner.
            existing = await repo.get_by_key(PREFERRED_EMAIL_SIGNOFF_KEY, for_update=True)
            assert existing is not None  # noqa: S101 — constraint implies a winner
        else:
            created = True
            _audit_memory(
                session, user_id=user_id, event_type="memory.candidate_created", item=item
            )
            existing = item

    assert existing is not None  # noqa: S101 — created or loaded above
    evidence_added = await _record_evidence(
        session, user_id=user_id, item=existing, observations=observations
    )

    updated = await _apply_lifecycle(
        session,
        user_id=user_id,
        item=existing,
        new_value=result.value,
        new_confidence=result.confidence,
        new_evidence_count=result.evidence_count,
        new_fingerprint=result.fingerprint,
        first_observed_at=result.first_observed_at,
        last_observed_at=result.last_observed_at,
        explicit_value=explicit_value,
        now=now,
        just_created=created,
    )
    if updated and not created:
        # What LifeFlow learned changed under the user's feet — bump the
        # optimistic-concurrency version so a stale confirm/dismiss is a 409,
        # never a silent overwrite of a newer inference.
        existing.version += 1

    await session.flush()
    return RecomputeResult(
        observations=result.total_observations,
        status=str(existing.status),
        created=created,
        updated=updated,
        evidence_added=evidence_added,
    )


def _expire_if_decayed(item: MemoryItem, *, now: datetime) -> bool:
    """Transition one candidate to `expired` if its confidence has decayed
    below the floor as of `now` (ADR 0004 D54). Idempotent: only a `candidate`
    is ever touched, and the effective (decayed) confidence is persisted as a
    truthful snapshot at the moment of expiry. Returns whether it changed."""
    if MemoryStatus(item.status) != MemoryStatus.candidate:
        return False
    effective = effective_confidence(item.confidence, item.last_evaluated_at, now)
    if effective >= CONFIDENCE_EXPIRY_FLOOR:
        return False
    item.confidence = effective
    item.status = MemoryStatus.expired
    item.expires_at = now
    return True


async def expire_stale_candidates(
    session: AsyncSession, user_id: uuid.UUID, *, now: datetime
) -> int:
    """Expire this user's candidates whose confidence has decayed below the
    floor with the passage of time alone (ADR 0004 D54). Called on every
    authenticated read of the memory API (like `ActionProposalService.expire_due`
    on the proposals list) so the API and UI never present a decayed candidate
    as active, and by the daily maintenance cron so expiry never depends on the
    user taking any action. `memory.expired` is audited exactly once — the
    transition only fires for a `candidate`, and an already-`expired` item is
    skipped on every later evaluation."""
    repo = MemoryItemRepository(session, user_id)
    expired = 0
    for item in await repo.list(statuses=[MemoryStatus.candidate]):
        if _expire_if_decayed(item, now=now):
            _audit_memory(session, user_id=user_id, event_type="memory.expired", item=item)
            expired += 1
    if expired:
        await session.flush()
    return expired


async def expire_all_stale_memory(session: AsyncSession, *, now: datetime) -> int:
    """Cross-user daily maintenance (ADR 0004 D54/D56): expire every decayed
    candidate for every user, so a stale candidate is never represented as
    active even if its owner never opens Settings again. Cross-user by
    necessity (like `scheduled_briefs.list_enabled_schedules`); every write is
    still keyed to the row's own `user_id`. Idempotent and safe to run
    repeatedly — confirmed explicit preferences are not candidates and are
    never touched."""
    result = await session.execute(
        select(MemoryItem).where(MemoryItem.status == MemoryStatus.candidate)
    )
    expired = 0
    for item in result.scalars():
        if _expire_if_decayed(item, now=now):
            _audit_memory(session, user_id=item.user_id, event_type="memory.expired", item=item)
            expired += 1
    if expired:
        await session.commit()
    return expired


async def _apply_lifecycle(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    item: MemoryItem,
    new_value: str,
    new_confidence: float,
    new_evidence_count: int,
    new_fingerprint: str,
    first_observed_at: datetime,
    last_observed_at: datetime,
    explicit_value: str | None,
    now: datetime,
    just_created: bool,
) -> bool:
    """Reconcile one memory item's status with fresh evidence and the current
    explicit preference (D55). Returns whether anything material changed."""
    previous_status = str(item.status)
    previous_value = str(item.value_json.get("value", ""))

    # Refresh the inspectable stats every time (freshness, evidence count).
    item.confidence = new_confidence
    item.evidence_count = new_evidence_count
    item.first_observed_at = first_observed_at
    item.last_observed_at = last_observed_at
    item.last_evaluated_at = now
    item.overridden_by_explicit = explicit_value is not None and explicit_value != new_value

    status = MemoryStatus(item.status)

    # Sticky dismissal (D55): stay dismissed until the evidence set genuinely
    # changes (fingerprint differs), then reconsider as a fresh candidate.
    if status == MemoryStatus.dismissed:
        if item.dismissed_fingerprint == new_fingerprint:
            return _finalise(item, previous_status, previous_value, just_created)
        status = MemoryStatus.candidate
        item.dismissed_at = None
        item.dismissed_fingerprint = None
        item.value_json = {"value": new_value}
        item.status = status
        _audit_memory(session, user_id=user_id, event_type="memory.candidate_updated", item=item)
        return True

    # A confirmed item wrote the explicit preference and carries its authority.
    if status == MemoryStatus.confirmed:
        if explicit_value is None:
            # The explicit preference was removed — fall back to the system
            # default, and let the inference re-surface for fresh confirmation
            # (D55). Never silently re-apply the old inferred value.
            item.status = MemoryStatus.candidate
            item.value_json = {"value": new_value}
            _audit_memory(
                session, user_id=user_id, event_type="memory.candidate_updated", item=item
            )
            return True
        if explicit_value != previous_value:
            # The user set a different explicit value — this confirmation is
            # overridden and no longer applied, but stays visible (D55).
            item.status = MemoryStatus.superseded
            _audit_memory(session, user_id=user_id, event_type="memory.superseded", item=item)
            return True
        # Still the applied value: only its display stats were refreshed.
        return _finalise(item, previous_status, previous_value, just_created)

    # Candidate / superseded path.
    if explicit_value is not None:
        # An explicit preference exists, so this inferred value is not applied
        # — visible but inactive (D55, skill §3.1 precedence).
        if status != MemoryStatus.superseded:
            item.value_json = {"value": new_value}
            item.status = MemoryStatus.superseded
            _audit_memory(session, user_id=user_id, event_type="memory.superseded", item=item)
            return True
        item.value_json = {"value": new_value}
        return _finalise(item, previous_status, previous_value, just_created)

    # No explicit preference: an ordinary candidate.
    if new_confidence < CONFIDENCE_EXPIRY_FLOOR:
        # Evidence decayed past the freshness floor with no confirmation (D54).
        item.value_json = {"value": new_value}
        item.status = MemoryStatus.expired
        item.expires_at = now
        _audit_memory(session, user_id=user_id, event_type="memory.expired", item=item)
        return True

    item.status = MemoryStatus.candidate
    item.expires_at = None
    if item.value_json.get("value") != new_value:
        # The dominant sign-off changed (contradictory evidence overtook the
        # old value) — update it visibly (skill §8 contradiction handling).
        item.value_json = {"value": new_value}
        if not just_created:
            _audit_memory(
                session, user_id=user_id, event_type="memory.candidate_updated", item=item
            )
        return True
    return _finalise(item, previous_status, previous_value, just_created)


def _finalise(
    item: MemoryItem, previous_status: str, previous_value: str, just_created: bool
) -> bool:
    """A quiet refresh: report whether status/value actually changed (audit
    events are emitted at the change sites; this only reports materiality)."""
    if just_created:
        return True
    return str(item.status) != previous_status or str(item.value_json.get("value", "")) != (
        previous_value
    )


async def enqueue_recompute(redis_url: str, user_id: uuid.UUID) -> bool:
    """Best-effort enqueue of a recompute for this user (D56). Carries only
    the user id — never draft content. Never raises: if Redis is unavailable
    the approval that triggered it still succeeds, and the missed job
    self-heals on the next recompute (the worker rescans authoritative state).
    Returns whether a job was enqueued."""
    pool = None
    try:
        settings = RedisSettings.from_dsn(redis_url)
        settings.conn_timeout = 1
        pool = await create_pool(
            settings, job_serializer=job_serializer, job_deserializer=job_deserializer
        )
        await pool.enqueue_job(JOB_FUNCTION_NAME, str(user_id))
        return True
    except Exception:
        logger.info("memory.enqueue_skipped user_id=%s (queue unavailable)", user_id)
        return False
    finally:
        if pool is not None:
            with contextlib.suppress(Exception):
                await pool.aclose()


__all__ = [
    "JOB_FUNCTION_NAME",
    "RecomputeResult",
    "enqueue_recompute",
    "expire_all_stale_memory",
    "expire_stale_candidates",
    "gather_signoff_observations",
    "recompute_user_memory",
]
