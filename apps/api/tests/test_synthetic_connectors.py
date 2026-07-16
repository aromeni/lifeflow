"""Synthetic adapters satisfy the shared connector contracts (Stage 3)."""

from datetime import UTC, date, datetime

import pytest

from lifeflow_api.connectors.interfaces import CalendarConnector, EmailConnector
from lifeflow_api.connectors.synthetic import (
    DEMO_TIMEZONE,
    SyntheticCalendarConnector,
    SyntheticEmailConnector,
)

ANCHOR = date(2026, 7, 15)
SINCE = datetime(2026, 7, 1, tzinfo=UTC)
UNTIL = datetime(2026, 8, 31, tzinfo=UTC)


def test_adapters_satisfy_the_connector_protocols() -> None:
    assert isinstance(SyntheticEmailConnector(ANCHOR), EmailConnector)
    assert isinstance(SyntheticCalendarConnector(ANCHOR), CalendarConnector)


async def test_emails_are_complete_timezone_aware_and_ordered() -> None:
    messages = await SyntheticEmailConnector(ANCHOR).fetch_recent(since=SINCE, until=UNTIL)
    assert 20 <= len(messages) <= 30, "skill §13 requires 20-30 emails"
    assert all(m.sent_at.tzinfo is not None for m in messages)
    assert messages == sorted(messages, key=lambda m: (m.sent_at, m.external_id))
    assert all(m.sender_email.endswith((".example", ".local")) for m in messages), (
        "dataset must be wholly fictional"
    )


async def test_events_are_complete_timezone_aware_and_ordered() -> None:
    events = await SyntheticCalendarConnector(ANCHOR).fetch_events(since=SINCE, until=UNTIL)
    assert 10 <= len(events) <= 15, "skill §13 requires 10-15 events"
    assert all(e.starts_at.tzinfo is not None and e.ends_at.tzinfo is not None for e in events)
    assert all(e.ends_at > e.starts_at for e in events)
    assert events == sorted(events, key=lambda e: (e.starts_at, e.external_id))


async def test_dataset_contains_the_required_scenarios() -> None:
    messages = await SyntheticEmailConnector(ANCHOR).fetch_recent(since=SINCE, until=UNTIL)
    events = await SyntheticCalendarConnector(ANCHOR).fetch_events(since=SINCE, until=UNTIL)
    subjects = " | ".join(m.subject.lower() for m in messages)
    bodies = " | ".join(m.body_text.lower() for m in messages)

    assert "ignore all previous instructions" in bodies  # prompt-injection fixture
    assert "newsletter" in " ".join(m.sender_email for m in messages)  # deprioritisable
    assert "that thing we discussed" in subjects  # ambiguous, low confidence
    assert any(m.folder == "sent" for m in messages)  # overdue follow-up material
    assert "confirm" in subjects and "wednesday" in subjects  # explicit request + deadline

    # Exactly one overlapping pair on the same day (the workshop/dentist conflict).
    overlaps = [
        (a.external_id, b.external_id)
        for i, a in enumerate(events)
        for b in events[i + 1 :]
        if not a.all_day and not b.all_day and a.starts_at < b.ends_at and b.starts_at < a.ends_at
    ]
    assert overlaps == [("ev-002", "ev-003")]


async def test_fetch_window_filters_by_date() -> None:
    connector = SyntheticEmailConnector(ANCHOR)
    narrow = await connector.fetch_recent(
        since=datetime(2026, 7, 15, tzinfo=DEMO_TIMEZONE),
        until=datetime(2026, 7, 16, tzinfo=DEMO_TIMEZONE),
    )
    assert {m.external_id for m in narrow} == {"em-021"}  # the only day-0 email


@pytest.mark.parametrize("run", [1, 2])
async def test_fetches_are_deterministic_for_a_fixed_anchor(run: int) -> None:
    first = await SyntheticEmailConnector(ANCHOR).fetch_recent(since=SINCE, until=UNTIL)
    second = await SyntheticEmailConnector(ANCHOR).fetch_recent(since=SINCE, until=UNTIL)
    assert first == second
