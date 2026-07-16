"""Pure deterministic brief sectioning, ordering, grounding, and prose guards."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from lifeflow_api.brief_composition import (
    SECTION_ORDER,
    BriefCompositionOutput,
    BriefProseValidationError,
    BriefSectionKey,
    compose_sections,
    deterministic_summary,
    validate_optional_summary,
)
from lifeflow_api.models import Signal, SourceItem

REFERENCE = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")


def _source(ref: str, *, offset_hours: int = 0) -> SourceItem:
    return SourceItem(
        id=uuid.uuid5(USER_ID, f"source:{ref}"),
        user_id=USER_ID,
        source_type="email",
        external_id=ref,
        source_account_id=None,
        title=f"Source {ref}",
        sender_or_organiser="person@example.test",
        occurred_at=REFERENCE + timedelta(hours=offset_hours),
        metadata_json={"body_preview": f"Evidence for {ref}"},
        content_fingerprint="a" * 64,
    )


def _signal(
    ref: str,
    signal_type: str,
    *,
    priority: float,
    band: str = "medium",
    confidence: float = 0.9,
    due_hours: int | None = None,
) -> Signal:
    return Signal(
        id=uuid.uuid5(USER_ID, f"signal:{signal_type}:{ref}:{priority}"),
        user_id=USER_ID,
        signal_type=signal_type,
        title=f"{signal_type.title()} {ref}",
        summary=f"Supported summary for {ref}",
        evidence_refs=[ref],
        due_at=REFERENCE + timedelta(hours=due_hours) if due_hours is not None else None,
        confidence=confidence,
        urgency=0.5,
        importance=0.5,
        extraction_version="det-v1",
        priority_score=priority,
        priority_band=band,
        reason_codes=["explicit_request"],
        dedupe_key=uuid.uuid5(USER_ID, f"dedupe:{signal_type}:{ref}").hex,
    )


def test_section_assignment_ordering_and_evidence_are_deterministic() -> None:
    sources = [_source(f"em-{number:03d}", offset_hours=number) for number in range(1, 7)]
    signals = [
        _signal("em-001", "request", priority=0.7, band="high", due_hours=24),
        _signal("em-002", "conflict", priority=0.9, band="high", due_hours=12),
        _signal("em-003", "meeting", priority=0.3),
        _signal("em-004", "follow_up", priority=0.5),
        _signal("em-005", "deadline", priority=0.4),
        _signal("em-006", "request", priority=0.45, confidence=0.4),
    ]

    first = compose_sections(signals, sources)
    second = compose_sections(list(reversed(signals)), list(reversed(sources)))

    assert first.sections == second.sections
    assert [section.key for section in first.sections] == list(SECTION_ORDER)
    by_key = {section.key: section for section in first.sections}
    assert [item.signal_type for item in by_key[BriefSectionKey.needs_attention].items] == [
        "conflict",
        "request",
    ]
    assert by_key[BriefSectionKey.today_upcoming].items[0].signal_type == "meeting"
    assert by_key[BriefSectionKey.waiting_for].items[0].signal_type == "follow_up"
    assert by_key[BriefSectionKey.suggested_actions].items[0].signal_type == "deadline"
    low_item = by_key[BriefSectionKey.low_confidence_review].items[0]
    assert low_item.confidence == 0.4 and not low_item.actionable

    actionable = [item for section in first.sections for item in section.items if item.actionable]
    assert actionable
    assert all(item.evidence and item.evidence[0].source_ref for item in actionable)
    assert all(item.suggested_action for item in actionable)


def test_missing_evidence_is_omitted_not_invented() -> None:
    composed = compose_sections([_signal("em-missing", "request", priority=0.8, band="high")], [])
    assert composed.included_signals == 0
    assert composed.omitted_signals == 1
    assert all(not section.items for section in composed.sections)


def test_empty_summary_is_honest() -> None:
    composed = compose_sections([], [])
    summary = deterministic_summary(composed.sections)
    assert "nothing to review yet" in summary.lower()


def test_optional_prose_must_exactly_match_supported_sentence() -> None:
    valid = BriefCompositionOutput.model_validate(
        {"summary_sentences": [{"signal_id": "s1", "text": "Supported sentence."}]}
    )
    assert (
        validate_optional_summary(valid, allowed={"s1": "Supported sentence."})
        == "Supported sentence."
    )

    unsupported = BriefCompositionOutput.model_validate(
        {
            "summary_sentences": [
                {"signal_id": "s1", "text": "Do this by an invented Friday deadline."}
            ]
        }
    )
    with pytest.raises(BriefProseValidationError, match="exactly match"):
        validate_optional_summary(unsupported, allowed={"s1": "Supported sentence."})
