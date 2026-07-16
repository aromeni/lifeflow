"""Normalisation is deterministic and timezone-correct, including DST."""

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from lifeflow_api.connectors.interfaces import CalendarEvent, EmailFolder, EmailMessage
from lifeflow_api.normalisation import email_to_source_item, event_to_source_item

LONDON = ZoneInfo("Europe/London")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def make_message(**overrides: object) -> EmailMessage:
    defaults: dict = dict(
        external_id="em-x",
        folder=EmailFolder.inbox,
        sender_name="Dana Whitfield",
        sender_email="dana@northgate-consulting.example",
        recipients=("demo@lifeflow.local",),
        subject="Contract terms",
        body_text="Please confirm by Wednesday.",
        sent_at=datetime(2026, 7, 14, 9, 14, tzinfo=LONDON),
        thread_id="t-1",
    )
    defaults.update(overrides)
    return EmailMessage(**defaults)


def test_email_normalisation_is_deterministic() -> None:
    a = email_to_source_item(make_message(), user_id=USER_ID, account_id=None)
    b = email_to_source_item(make_message(), user_id=USER_ID, account_id=None)
    assert a.content_fingerprint == b.content_fingerprint
    assert a.metadata_json == b.metadata_json
    assert a.occurred_at == b.occurred_at


def test_fingerprint_changes_when_content_changes() -> None:
    original = email_to_source_item(make_message(), user_id=USER_ID, account_id=None)
    edited = email_to_source_item(
        make_message(body_text="Please confirm by Thursday."), user_id=USER_ID, account_id=None
    )
    assert original.content_fingerprint != edited.content_fingerprint


def test_email_times_are_stored_in_utc() -> None:
    # 09:14 BST (summer) is 08:14 UTC.
    item = email_to_source_item(make_message(), user_id=USER_ID, account_id=None)
    assert item.occurred_at == datetime(2026, 7, 14, 8, 14, tzinfo=UTC)


def test_event_times_are_correct_across_the_dst_boundary() -> None:
    """UK clocks go forward 2026-03-29 01:00 GMT → 02:00 BST."""

    def event_at(day: int, hour: int) -> CalendarEvent:
        return CalendarEvent(
            external_id=f"ev-dst-{day}",
            title="DST check",
            organiser_email="demo@lifeflow.local",
            starts_at=datetime(2026, 3, day, hour, 0, tzinfo=LONDON),
            ends_at=datetime(2026, 3, day, hour + 1, 0, tzinfo=LONDON),
        )

    before = event_to_source_item(event_at(28, 10), user_id=USER_ID, account_id=None)
    after = event_to_source_item(event_at(29, 10), user_id=USER_ID, account_id=None)

    # Same wall-clock hour, different UTC offsets on either side of the change.
    assert before.occurred_at == datetime(2026, 3, 28, 10, 0, tzinfo=UTC)  # GMT: UTC+0
    assert after.occurred_at == datetime(2026, 3, 29, 9, 0, tzinfo=UTC)  # BST: UTC+1


def test_event_metadata_captures_end_time_in_utc() -> None:
    event = CalendarEvent(
        external_id="ev-x",
        title="Workshop",
        organiser_email="dana@northgate-consulting.example",
        starts_at=datetime(2026, 7, 17, 14, 0, tzinfo=LONDON),
        ends_at=datetime(2026, 7, 17, 15, 30, tzinfo=LONDON),
        location="Meeting Room 4",
        attendees=("b@x.example", "a@x.example"),
    )
    item = event_to_source_item(event, user_id=USER_ID, account_id=None)
    assert item.metadata_json["ends_at"] == "2026-07-17T14:30:00+00:00"
    assert item.metadata_json["attendees"] == ["a@x.example", "b@x.example"]  # sorted, stable


def test_long_bodies_are_truncated_in_metadata() -> None:
    item = email_to_source_item(
        make_message(body_text="x" * 1000), user_id=USER_ID, account_id=None
    )
    assert len(item.metadata_json["body_preview"]) == 280
