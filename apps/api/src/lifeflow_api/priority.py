"""PriorityScorer — the explainable hybrid priority model (skill §8).

    priority_score =
        0.30 x urgency
      + 0.25 x importance
      + 0.20 x explicit_request_strength
      + 0.15 x deadline_proximity
      + 0.10 x relationship_or_context_weight

Every component is normalised to [0, 1] and every contribution is visible as
a reason code. No opaque model output participates in ranking: LLM-extracted
signals are scored by exactly the same deterministic formula.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from lifeflow_api.detectors import DetectedSignal
from lifeflow_api.models import SignalType, SourceItem

WEIGHTS = {
    "urgency": 0.30,
    "importance": 0.25,
    "explicit_request_strength": 0.20,
    "deadline_proximity": 0.15,
    "relationship": 0.10,
}
HIGH_BAND_THRESHOLD = 0.55
MEDIUM_BAND_THRESHOLD = 0.35
FREQUENT_CONTACT_MIN_ITEMS = 3


@dataclass(frozen=True)
class ScoredSignal:
    signal: DetectedSignal
    score: float
    band: str  # high | medium | low
    reason_codes: tuple[str, ...]


def _deadline_proximity(due_at: datetime | None, reference: datetime) -> tuple[float, str | None]:
    if due_at is None:
        return 0.0, None
    remaining = due_at - reference
    if remaining <= timedelta(0):
        return 1.0, "overdue"
    if remaining <= timedelta(hours=24):
        return 1.0, "due_within_24h"
    if remaining <= timedelta(hours=72):
        return 0.7, "due_within_72h"
    if remaining <= timedelta(days=7):
        return 0.4, "due_this_week"
    return 0.15, None


def _request_strength(signal: DetectedSignal) -> float:
    if signal.signal_type == SignalType.request:
        return 0.9 if "explicit_request" in signal.reason_codes else 0.4
    if signal.signal_type == SignalType.commitment:
        return 0.6  # a promise you made carries request-like weight
    return 0.0


def _importance(signal: DetectedSignal) -> float:
    """Type-based importance; sender familiarity is the relationship component."""
    return {
        SignalType.conflict: 0.8,
        SignalType.deadline: 0.7,
        SignalType.request: 0.6,
        SignalType.commitment: 0.6,
        SignalType.follow_up: 0.5,
        SignalType.meeting: 0.4,
    }.get(SignalType(signal.signal_type), 0.5)


def _relationship(
    signal: DetectedSignal,
    items_by_external: dict[str, SourceItem],
    sender_frequency: dict[str, int],
) -> tuple[float, str | None]:
    senders = {
        items_by_external[ref].sender_or_organiser
        for ref in signal.evidence_refs
        if ref in items_by_external
    }
    if any(
        sender_frequency.get(sender or "", 0) >= FREQUENT_CONTACT_MIN_ITEMS for sender in senders
    ):
        return 0.7, "frequent_contact"
    return 0.3, None


def build_sender_frequency(items: list[SourceItem]) -> dict[str, int]:
    frequency: dict[str, int] = {}
    for item in items:
        sender = item.sender_or_organiser or ""
        frequency[sender] = frequency.get(sender, 0) + 1
    return frequency


def score_signal(
    signal: DetectedSignal,
    *,
    reference: datetime,
    items_by_external: dict[str, SourceItem],
    sender_frequency: dict[str, int],
) -> ScoredSignal:
    reasons = list(signal.reason_codes)

    proximity, proximity_reason = _deadline_proximity(signal.due_at, reference)
    if proximity_reason:
        reasons.append(proximity_reason)

    importance = _importance(signal)

    relationship, relationship_reason = _relationship(signal, items_by_external, sender_frequency)
    if relationship_reason:
        reasons.append(relationship_reason)

    score = (
        WEIGHTS["urgency"] * signal.urgency
        + WEIGHTS["importance"] * importance
        + WEIGHTS["explicit_request_strength"] * _request_strength(signal)
        + WEIGHTS["deadline_proximity"] * proximity
        + WEIGHTS["relationship"] * relationship
    )
    band = (
        "high"
        if score >= HIGH_BAND_THRESHOLD
        else "medium"
        if score >= MEDIUM_BAND_THRESHOLD
        else "low"
    )
    # De-duplicate reason codes, preserving first-seen order.
    ordered_reasons = tuple(dict.fromkeys(reasons))
    return ScoredSignal(
        signal=signal, score=round(score, 4), band=band, reason_codes=ordered_reasons
    )
