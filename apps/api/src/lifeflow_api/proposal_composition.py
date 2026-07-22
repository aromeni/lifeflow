"""Deterministic, evidence-backed Stage 6 action proposal composition.

Resilience rule: a signal whose source metadata cannot be turned into a valid
typed payload is SKIPPED, never fatal — composition tries the next matching
signal and brief generation always completes. Skips are reported as safe
(action type, reason code) pairs only; source content never leaves this
module through the skip path.
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from lifeflow_api.action_payloads import (
    CalendarEventCreatePayload,
    GmailDraftCreatePayload,
    TaskCreatePayload,
    TypedActionPayload,
    effective_payload_deadline,
)
from lifeflow_api.detectors import parse_aware_datetime
from lifeflow_api.models import ActionType, RiskLevel, Signal, SignalType, SourceItem, SourceType
from lifeflow_api.scheduling_phrases import parse_scheduling_request

logger = logging.getLogger(__name__)

PROPOSAL_COMPOSER_VERSION = "proposal-det-v1"
# Frozen independently of the composer implementation version. Changing
# composition rules must update an existing origin, never mint a duplicate.
PROPOSAL_ORIGIN_NAMESPACE = "action-origin-v1"
PROPOSAL_TTL = timedelta(days=7)


@dataclass(frozen=True)
class ProposalCandidate:
    action_type: ActionType
    rationale: str
    source_refs: tuple[str, ...]
    payload: TypedActionPayload
    risk_level: RiskLevel
    confidence: float
    origin_fingerprint: str
    expires_at: datetime


@dataclass(frozen=True)
class SkippedCandidate:
    """A safe record of a candidate that could not be composed.

    Carries only the closed action type and a fixed reason code — never
    titles, bodies, attendees, or any other source content (threat model
    §logging rules).
    """

    action_type: ActionType
    reason_code: str


@dataclass(frozen=True)
class ComposedProposals:
    candidates: tuple[ProposalCandidate, ...]
    skipped: tuple[SkippedCandidate, ...]


INVALID_SOURCE_DATA = "invalid_source_data"
# A requested event already exists on the user's own synced calendar with
# the same title and start; composing it again would prepare a duplicate.
EXISTING_EVENT_DUPLICATE = "existing_event_duplicate"


def _origin_fingerprint(action_type: ActionType, signal: Signal) -> str:
    material = f"{PROPOSAL_ORIGIN_NAMESPACE}|{action_type}|{signal.dedupe_key}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _expiry(payload: TypedActionPayload, reference: datetime) -> datetime | None:
    deadline = effective_payload_deadline(payload)
    expires_at = min(reference + PROPOSAL_TTL, deadline) if deadline else reference + PROPOSAL_TTL
    return expires_at.astimezone(UTC) if expires_at > reference else None


def _signal_order(signal: Signal) -> tuple[float, datetime, str]:
    return (
        -(signal.priority_score or 0.0),
        signal.due_at or datetime.max.replace(tzinfo=UTC),
        signal.dedupe_key,
    )


def _record_skip(
    skipped: list[SkippedCandidate],
    action_type: ActionType,
    reason_code: str = INVALID_SOURCE_DATA,
) -> None:
    # Reason code only — deliberately no signal id, title, or source content.
    skipped.append(SkippedCandidate(action_type=action_type, reason_code=reason_code))
    logger.warning("proposal.candidate_skipped action_type=%s reason=%s", action_type, reason_code)


def _sources_for(signal: Signal, sources: dict[str, SourceItem]) -> list[SourceItem] | None:
    resolved = [sources.get(ref) for ref in signal.evidence_refs]
    if not resolved or any(item is None for item in resolved):
        return None
    return [item for item in resolved if item is not None]


def _task_candidates(
    signals: list[Signal],
    sources: dict[str, SourceItem],
    reference: datetime,
    skipped: list[SkippedCandidate],
) -> list[ProposalCandidate]:
    candidates: list[ProposalCandidate] = []
    for signal in signals:
        if signal.signal_type not in {SignalType.deadline, SignalType.commitment}:
            continue
        if signal.confidence < 0.5 or not _sources_for(signal, sources):
            continue
        try:
            payload = TaskCreatePayload(
                title=signal.title[:200],
                notes=signal.summary[:2_000],
                due_at=signal.due_at,
            )
        except (ValidationError, ValueError, TypeError):
            _record_skip(skipped, ActionType.create_task)
            continue
        expires_at = _expiry(payload, reference)
        if expires_at is None:
            continue
        candidates.append(
            ProposalCandidate(
                action_type=ActionType.create_task,
                rationale="Create an internal task for this evidenced commitment or deadline.",
                source_refs=tuple(sorted(signal.evidence_refs)),
                payload=payload,
                risk_level=RiskLevel.low,
                confidence=signal.confidence,
                origin_fingerprint=_origin_fingerprint(ActionType.create_task, signal),
                expires_at=expires_at,
            )
        )
    return candidates


def _draft_candidates(
    signals: list[Signal],
    sources: dict[str, SourceItem],
    reference: datetime,
    skipped: list[SkippedCandidate],
) -> list[ProposalCandidate]:
    candidates: list[ProposalCandidate] = []
    for signal in signals:
        if signal.signal_type not in {SignalType.request, SignalType.follow_up}:
            continue
        if signal.confidence < 0.5:
            continue
        resolved = _sources_for(signal, sources)
        if not resolved:
            continue
        source = next(
            (
                item
                for item in resolved
                if item.source_type == SourceType.email
                and item.metadata_json.get("folder") == "inbox"
                and item.sender_or_organiser
            ),
            None,
        )
        if source is None:
            continue
        recipient = source.sender_or_organiser
        if not recipient:
            continue
        try:
            sender_name = str(source.metadata_json.get("sender_name") or "there").split()[0]
            payload = GmailDraftCreatePayload(
                to=[recipient],
                subject=(
                    source.title
                    if source.title.lower().startswith("re:")
                    else f"Re: {source.title}"
                ),
                body=(
                    f"Hi {sender_name},\n\n"
                    f'Thanks for your message about "{source.title}". '
                    "I'm reviewing it and will follow up.\n\nBest"
                ),
                thread_id=source.metadata_json.get("thread_id"),
            )
        except (ValidationError, ValueError, TypeError, IndexError):
            _record_skip(skipped, ActionType.create_gmail_draft)
            continue
        expires_at = _expiry(payload, reference)
        if expires_at is None:
            continue
        candidates.append(
            ProposalCandidate(
                action_type=ActionType.create_gmail_draft,
                rationale=(
                    "Prepare a draft reply to an evidence-backed request; this never sends email."
                ),
                source_refs=tuple(sorted(signal.evidence_refs)),
                payload=payload,
                risk_level=RiskLevel.medium,
                confidence=signal.confidence,
                origin_fingerprint=_origin_fingerprint(ActionType.create_gmail_draft, signal),
                expires_at=expires_at,
            )
        )
    return candidates


def _existing_event_duplicate(
    sources: dict[str, SourceItem], title: str, starts_at: datetime
) -> bool:
    """True when the user's own synced calendar already holds an event with
    this title at this instant — approving the candidate would create a
    duplicate, so it is never composed."""
    wanted = (title.casefold(), starts_at.astimezone(UTC))
    return any(
        item.source_type == SourceType.calendar_event
        and (item.title.casefold(), item.occurred_at.astimezone(UTC)) == wanted
        for item in sources.values()
    )


def _scheduled_event_candidate(
    signal: Signal,
    resolved: list[SourceItem],
    sources: dict[str, SourceItem],
    reference: datetime,
    timezone: str,
    skipped: list[SkippedCandidate],
) -> ProposalCandidate | None:
    """A `create_calendar_event` candidate from an explicit email scheduling
    request (ADR 0003 D39) — Model A: inbound Gmail request → new event
    proposal. The email text is re-parsed here with the same deterministic
    extractor the detector used; only a complete, future extraction ever
    becomes a payload, and every field the user will approve comes straight
    from the evidence text (or the profile timezone, disclosed by reason
    code) — nothing is guessed."""
    source = next(
        (
            item
            for item in resolved
            if item.source_type == SourceType.email and item.metadata_json.get("folder") == "inbox"
        ),
        None,
    )
    if source is None:
        return None
    extraction = parse_scheduling_request(
        f"{source.title}\n{source.metadata_json.get('body_preview', '')}",
        subject=source.title,
        sender=source.sender_or_organiser,
        timezone=timezone,
    )
    if not extraction.executable(reference=reference):
        return None
    assert extraction.title is not None  # noqa: S101 — implied by executable()
    assert extraction.starts_at is not None  # noqa: S101
    assert extraction.ends_at is not None  # noqa: S101
    assert extraction.timezone is not None  # noqa: S101
    if _existing_event_duplicate(sources, extraction.title, extraction.starts_at):
        _record_skip(skipped, ActionType.create_calendar_event, EXISTING_EVENT_DUPLICATE)
        return None
    try:
        payload = CalendarEventCreatePayload(
            title=extraction.title[:250],
            starts_at=extraction.starts_at,
            ends_at=extraction.ends_at,
            timezone=extraction.timezone,
            location=None,
            description=f'Prepared by LifeFlow from the email "{source.title}".'[:5_000],
            attendees=list(extraction.attendees),
        )
    except (ValidationError, ValueError, TypeError):
        _record_skip(skipped, ActionType.create_calendar_event)
        return None
    expires_at = _expiry(payload, reference)
    if expires_at is None:
        return None
    return ProposalCandidate(
        action_type=ActionType.create_calendar_event,
        rationale=(
            "Prepare the calendar event exactly as requested by email; "
            "nothing is created until you approve it."
        ),
        source_refs=tuple(sorted(signal.evidence_refs)),
        payload=payload,
        risk_level=RiskLevel.medium,
        confidence=signal.confidence,
        origin_fingerprint=_origin_fingerprint(ActionType.create_calendar_event, signal),
        expires_at=expires_at,
    )


def _proposed_placeholder_candidate(
    signal: Signal,
    resolved: list[SourceItem],
    reference: datetime,
    timezone: str,
    google_account_ids: frozenset[uuid.UUID],
    skipped: list[SkippedCandidate],
) -> ProposalCandidate | None:
    """The demo-dataset convention: a synthetic calendar entry titled with
    "(proposed)" stands in for a tentative meeting, and the candidate is the
    real version of it. Restricted to non-Google evidence (ADR 0003 D41):
    on a real synced calendar this pattern would create a near-duplicate
    sibling of the placeholder, so a Google-sourced event never composes
    one."""
    source = next(
        (
            item
            for item in resolved
            if item.source_type == SourceType.calendar_event
            and "proposed" in item.title.lower()
            and item.source_account_id not in google_account_ids
        ),
        None,
    )
    if source is None:
        return None
    try:
        # Missing, malformed, or timezone-naive end times are invalid
        # source metadata — a timezone is never guessed for the user.
        ends_at = parse_aware_datetime(source.metadata_json.get("ends_at"))
        if ends_at is None:
            raise ValueError("Calendar source has no usable timezone-aware end time.")
        raw_attendees = source.metadata_json.get("attendees")
        if not isinstance(raw_attendees, list) or not all(
            isinstance(attendee, str) for attendee in raw_attendees
        ):
            raise ValueError("Calendar source attendees are not a list of addresses.")
        if not raw_attendees:
            return None
        payload = CalendarEventCreatePayload(
            title=source.title.replace(" (proposed)", "")[:250],
            starts_at=source.occurred_at,
            ends_at=ends_at,
            timezone=timezone,
            location=source.metadata_json.get("location"),
            description=str(source.metadata_json.get("description") or ""),
            attendees=list(raw_attendees),
        )
    except (ValidationError, ValueError, TypeError):
        _record_skip(skipped, ActionType.create_calendar_event)
        return None
    expires_at = _expiry(payload, reference)
    if expires_at is None:
        return None
    return ProposalCandidate(
        action_type=ActionType.create_calendar_event,
        rationale="Prepare the proposed meeting as a calendar event for review.",
        source_refs=tuple(sorted(signal.evidence_refs)),
        payload=payload,
        risk_level=RiskLevel.medium,
        confidence=signal.confidence,
        origin_fingerprint=_origin_fingerprint(ActionType.create_calendar_event, signal),
        expires_at=expires_at,
    )


def _calendar_candidates(
    signals: list[Signal],
    sources: dict[str, SourceItem],
    reference: datetime,
    timezone: str,
    google_account_ids: frozenset[uuid.UUID],
    skipped: list[SkippedCandidate],
) -> list[ProposalCandidate]:
    candidates: list[ProposalCandidate] = []
    for signal in signals:
        if signal.confidence < 0.5:
            continue
        resolved = _sources_for(signal, sources)
        if not resolved:
            continue
        candidate: ProposalCandidate | None = None
        if signal.signal_type == SignalType.schedule_request:
            candidate = _scheduled_event_candidate(
                signal, resolved, sources, reference, timezone, skipped
            )
        elif signal.signal_type == SignalType.meeting:
            candidate = _proposed_placeholder_candidate(
                signal, resolved, reference, timezone, google_account_ids, skipped
            )
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def compose_proposal_candidates(
    signals: list[Signal],
    source_items: list[SourceItem],
    *,
    reference: datetime,
    timezone: str,
    google_account_ids: frozenset[uuid.UUID] = frozenset(),
) -> ComposedProposals:
    """Return every grounded proposal candidate for each closed action type,
    ranked most-preferred first within each type (by ``_signal_order``).

    A single generation pass may compose more than one candidate of the same
    action type: `ActionProposalService.generate_from_brief` only ever turns
    the top-ranked one into an *active* proposal (matching the product's one
    active proposal per action type policy), but it needs the rest so that a
    genuinely new, distinct signal is never permanently blocked just because
    an older signal of the same type already has a terminal (rejected,
    executed, failed, expired) or dead-ended (`executing`, never auto-
    retried) proposal — that proposal is left immutable, and the service
    moves on to the next-ranked candidate here instead.

    Each candidate is validated independently: malformed source metadata
    skips that candidate (recorded safely in ``skipped``) and composition
    continues — it never raises for bad source data.
    """

    if reference.tzinfo is None:
        raise ValueError("Proposal composition reference must be timezone-aware.")
    ordered = sorted(signals, key=_signal_order)
    sources = {item.external_id: item for item in source_items}
    skipped: list[SkippedCandidate] = []
    candidates = [
        *_task_candidates(ordered, sources, reference, skipped),
        *_draft_candidates(ordered, sources, reference, skipped),
        *_calendar_candidates(ordered, sources, reference, timezone, google_account_ids, skipped),
    ]
    return ComposedProposals(
        candidates=tuple(candidates),
        skipped=tuple(skipped),
    )


def candidate_payload_json(candidate: ProposalCandidate) -> dict[str, Any]:
    return candidate.payload.model_dump(mode="json")


__all__ = [
    "EXISTING_EVENT_DUPLICATE",
    "INVALID_SOURCE_DATA",
    "PROPOSAL_COMPOSER_VERSION",
    "PROPOSAL_ORIGIN_NAMESPACE",
    "ComposedProposals",
    "ProposalCandidate",
    "SkippedCandidate",
    "candidate_payload_json",
    "compose_proposal_candidates",
]
