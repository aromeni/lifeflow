"""Deterministic detector baseline (det-v1) against the demo dataset."""

import pytest
from tests.helpers import REFERENCE, TIMEZONE, demo_source_items

from lifeflow_api.detectors import INVALID_ATTENDEES_METADATA, run_deterministic_detectors
from lifeflow_api.models import SignalType


@pytest.fixture
async def signals():
    items = await demo_source_items()
    return run_deterministic_detectors(items, reference=REFERENCE, timezone=TIMEZONE).signals


def by_type(signals, signal_type):
    return [s for s in signals if s.signal_type == signal_type]


def evidence(signals):
    return {ref for s in signals for ref in s.evidence_refs}


async def test_explicit_requests_are_detected(signals) -> None:
    refs = evidence(by_type(signals, SignalType.request))
    # Manifest scenario "explicit_request" — em-014 is request-phrased too.
    for expected in ("em-001", "em-006", "em-008", "em-010", "em-017", "em-023"):
        assert expected in refs, f"missed explicit request {expected}"


async def test_request_deadlines_are_extracted(signals) -> None:
    dana = next(s for s in by_type(signals, SignalType.request) if "em-001" in s.evidence_refs)
    assert dana.due_at is not None
    assert dana.due_at.strftime("%Y-%m-%d") == "2026-07-15"  # "by Wednesday", sent Tuesday


async def test_ambiguous_email_gets_low_confidence(signals) -> None:
    ambiguous = [s for s in signals if "em-005" in s.evidence_refs]
    assert ambiguous, "em-005 should surface as a weak signal"
    assert all(s.confidence < 0.5 for s in ambiguous)


async def test_newsletters_and_bulk_mail_yield_no_signals(signals) -> None:
    refs = evidence(signals)
    for bulk in ("em-003", "em-013", "em-020", "em-012", "em-004"):
        assert bulk not in refs, f"bulk/newsletter {bulk} must not produce signals"


async def test_commitments_from_sent_mail(signals) -> None:
    refs = evidence(by_type(signals, SignalType.commitment))
    assert "em-015" in refs  # "I'll ... confirm the terms by Wednesday"


async def test_overdue_follow_ups(signals) -> None:
    follow_ups = by_type(signals, SignalType.follow_up)
    refs = evidence(follow_ups)
    assert "em-002" in refs  # 6 days without reply
    assert "em-024" in refs  # 13 days without reply
    assert "em-015" not in refs  # only 1 day old — not stale


async def test_calendar_conflict_detected_exactly_once(signals) -> None:
    conflicts = by_type(signals, SignalType.conflict)
    assert len(conflicts) == 1
    assert set(conflicts[0].evidence_refs) == {"ev-002", "ev-003"}


async def test_deadline_from_all_day_due_event(signals) -> None:
    deadlines = by_type(signals, SignalType.deadline)
    assert "ev-004" in evidence(deadlines)  # "Northgate proposal due"


async def test_upcoming_meetings_only(signals) -> None:
    refs = evidence(by_type(signals, SignalType.meeting))
    assert {"ev-001", "ev-002", "ev-007", "ev-011"} <= refs
    assert "ev-006" not in refs  # yesterday's 1:1 is in the past


async def test_detection_is_deterministic() -> None:
    items = await demo_source_items()
    first = run_deterministic_detectors(items, reference=REFERENCE, timezone=TIMEZONE)
    second = run_deterministic_detectors(items, reference=REFERENCE, timezone=TIMEZONE)
    assert first == second


async def test_every_signal_carries_evidence_and_reasons(signals) -> None:
    assert signals, "baseline must detect signals"
    for signal in signals:
        assert signal.evidence_refs, f"{signal.title} lacks evidence"
        assert signal.reason_codes, f"{signal.title} lacks reason codes"
        assert 0.0 <= signal.confidence <= 1.0


async def test_malformed_metadata_never_aborts_detection() -> None:
    """Untrusted-metadata boundary: a malformed SourceItem degrades only its
    own detection — never a TypeError/KeyError that aborts the whole run."""
    items = await demo_source_items()
    by_id = {item.external_id: item for item in items}
    # Timezone-naive end on one side of the known ev-002/ev-003 conflict pair:
    # the conflict calculation is skipped, never computed against a guessed zone.
    by_id["ev-002"].metadata_json = {
        **by_id["ev-002"].metadata_json,
        "ends_at": "2026-07-16T11:00:00",
    }
    # Attendees that cannot establish a count suppress that meeting only.
    by_id["ev-007"].metadata_json = {**by_id["ev-007"].metadata_json, "attendees": 7}
    # Non-list recipients on a sent email must not break commitment detection.
    by_id["em-015"].metadata_json = {
        **by_id["em-015"].metadata_json,
        "recipients": {"to": "someone@example.com"},
    }

    result = run_deterministic_detectors(items, reference=REFERENCE, timezone=TIMEZONE)
    detected = result.signals

    assert not by_type(detected, SignalType.conflict)  # skipped, not guessed
    meetings = evidence(by_type(detected, SignalType.meeting))
    assert "ev-007" not in meetings
    assert {"ev-001", "ev-002", "ev-011"} <= meetings  # other meetings survive
    assert "em-015" in evidence(by_type(detected, SignalType.commitment))
    assert "em-001" in evidence(by_type(detected, SignalType.request))

    # Whole-value malformed attendees (ev-007) is reported as a safe
    # diagnostic — a fixed code and the source item's own id only, never the
    # malformed value itself.
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.code == INVALID_ATTENDEES_METADATA
    assert diagnostic.severity == "warning"
    assert diagnostic.source_item_id == "ev-007"
