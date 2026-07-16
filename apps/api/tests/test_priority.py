"""Priority engine: formula, reason codes, bands, ranking stability."""

from datetime import timedelta

from tests.helpers import REFERENCE, TIMEZONE, demo_source_items

from lifeflow_api.detectors import DetectedSignal, run_deterministic_detectors
from lifeflow_api.models import SignalType
from lifeflow_api.priority import build_sender_frequency, score_signal


async def scored_signals():
    items = await demo_source_items()
    detected = run_deterministic_detectors(items, reference=REFERENCE, timezone=TIMEZONE)
    items_by_external = {i.external_id: i for i in items}
    freq = build_sender_frequency(items)
    return [
        score_signal(
            s, reference=REFERENCE, items_by_external=items_by_external, sender_frequency=freq
        )
        for s in detected
    ]


async def test_scores_are_normalised_and_banded() -> None:
    for scored in await scored_signals():
        assert 0.0 <= scored.score <= 1.0
        assert scored.band in {"high", "medium", "low"}
        assert scored.reason_codes


async def test_urgent_request_with_deadline_ranks_high() -> None:
    scored = await scored_signals()
    dana = next(s for s in scored if "em-001" in s.signal.evidence_refs)
    assert dana.band == "high"
    assert "explicit_request" in dana.reason_codes
    assert "overdue" in dana.reason_codes or "due_within_24h" in dana.reason_codes


async def test_conflict_ranks_high_with_reason() -> None:
    scored = await scored_signals()
    conflict = next(s for s in scored if s.signal.signal_type == SignalType.conflict)
    assert conflict.band == "high"
    assert "calendar_conflict" in conflict.reason_codes


async def test_weak_ambiguous_signal_ranks_below_explicit_requests() -> None:
    scored = await scored_signals()
    ambiguous = next(s for s in scored if "em-005" in s.signal.evidence_refs)
    dana = next(s for s in scored if "em-001" in s.signal.evidence_refs)
    assert ambiguous.score < dana.score
    assert "weak_request_cue" in ambiguous.reason_codes


async def test_ranking_is_stable_across_runs() -> None:
    first = [(s.signal.evidence_refs, s.score) for s in await scored_signals()]
    second = [(s.signal.evidence_refs, s.score) for s in await scored_signals()]
    assert first == second


def test_deadline_proximity_bands() -> None:
    base = DetectedSignal(
        signal_type=SignalType.request,
        title="t",
        summary="s",
        evidence_refs=("x",),
        confidence=0.8,
        urgency=0.5,
        reason_codes=("explicit_request",),
    )

    def score_with_due(delta: timedelta | None):
        signal = DetectedSignal(
            **{**base.__dict__, "due_at": (REFERENCE + delta) if delta else None}
        )
        return score_signal(signal, reference=REFERENCE, items_by_external={}, sender_frequency={})

    overdue = score_with_due(timedelta(hours=-2))
    soon = score_with_due(timedelta(hours=12))
    this_week = score_with_due(timedelta(days=5))
    never = score_with_due(None)

    assert "overdue" in overdue.reason_codes
    assert "due_within_24h" in soon.reason_codes
    assert "due_this_week" in this_week.reason_codes
    assert overdue.score >= soon.score > this_week.score > never.score
