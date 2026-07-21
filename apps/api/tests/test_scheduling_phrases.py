"""Deterministic scheduling-request extraction (ADR 0003 D39).

Every test pins the reference clock explicitly, and every email fixture
writes its date relative to that frozen reference — nothing here rots as
wall-clock time passes.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from lifeflow_api.scheduling_phrases import parse_scheduling_request

REFERENCE = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
LONDON = ZoneInfo("Europe/London")

CONTROLLED_SUBJECT = "Please schedule LifeFlow Calendar Verification Test"
CONTROLLED_BODY = (
    "Hi Rashid,\n\nPlease schedule a 30-minute calendar event called "
    "“LifeFlow Calendar Verification Test 3” for Sunday 19 July 2026, "
    "from 4:00 PM to 4:30 PM Europe/London.\n\n"
    "Please add my email address as the attendee.\n\n"
    "This is a controlled sandbox test.\n\nThanks,\nAbdul"
)


def _parse(
    text: str, *, subject: str = CONTROLLED_SUBJECT, sender: str | None = "abdul@example.com"
):
    return parse_scheduling_request(text, subject=subject, sender=sender, timezone="Europe/London")


def test_controlled_scheduling_email_extracts_every_field() -> None:
    extraction = _parse(f"{CONTROLLED_SUBJECT}\n{CONTROLLED_BODY}")
    assert extraction.has_intent
    assert extraction.title == "LifeFlow Calendar Verification Test 3"
    assert extraction.starts_at == datetime(2026, 7, 19, 16, 0, tzinfo=LONDON)
    assert extraction.ends_at == datetime(2026, 7, 19, 16, 30, tzinfo=LONDON)
    assert extraction.timezone == "Europe/London"
    assert extraction.attendees == ("abdul@example.com",)
    assert extraction.missing == ()
    assert "sender_as_attendee" in extraction.reason_codes
    assert extraction.executable(reference=REFERENCE)


def test_explicit_europe_london_timezone_beats_the_profile_default() -> None:
    extraction = _parse(
        "Please schedule a call named 'Sync' for Sunday 19 July 2026 "
        "from 4:00 PM to 4:30 PM Europe/London. Invite me."
    )
    assert extraction.timezone == "Europe/London"
    assert "timezone_from_profile" not in extraction.reason_codes


def test_missing_timezone_falls_back_to_profile_with_a_disclosed_reason() -> None:
    extraction = _parse(
        "Please schedule a call named 'Sync' for Sunday 19 July 2026 "
        "from 4:00 PM to 4:30 PM. Invite me."
    )
    assert extraction.timezone == "Europe/London"
    assert "timezone_from_profile" in extraction.reason_codes
    assert extraction.missing == ()


def test_duration_phrase_derives_the_end_time() -> None:
    extraction = _parse(
        "Please schedule a 30-minute call named 'Sync' for Sunday 19 July 2026 "
        "at 3:00 PM Europe/London. Invite me."
    )
    assert extraction.starts_at == datetime(2026, 7, 19, 15, 0, tzinfo=LONDON)
    assert extraction.ends_at == datetime(2026, 7, 19, 15, 30, tzinfo=LONDON)


def test_a_dateless_request_is_incomplete_never_guessed() -> None:
    extraction = _parse("Please schedule a call named 'Sync' at 3:00 PM on Sunday. Invite me.")
    assert extraction.has_intent
    assert "date" in extraction.missing
    assert extraction.starts_at is None
    assert not extraction.executable(reference=REFERENCE)


def test_two_conflicting_dates_are_ambiguous() -> None:
    extraction = _parse(
        "Please schedule a call named 'Sync' for 19 July 2026 or 20 July 2026 "
        "at 3:00 PM for 30 minutes. Invite me."
    )
    assert "date" in extraction.missing
    assert "ambiguous_date" in extraction.reason_codes


def test_weekday_that_contradicts_the_date_is_rejected() -> None:
    # 19 July 2026 is a Sunday, not a Monday — never silently corrected.
    extraction = _parse(
        "Please schedule a call named 'Sync' for Monday 19 July 2026 "
        "from 4:00 PM to 4:30 PM. Invite me."
    )
    assert "date" in extraction.missing
    assert "date_weekday_mismatch" in extraction.reason_codes


def test_missing_start_time_is_incomplete() -> None:
    extraction = _parse(
        "Please schedule a 30-minute call named 'Sync' for Sunday 19 July 2026. Invite me."
    )
    assert "start_time" in extraction.missing
    assert not extraction.executable(reference=REFERENCE)


def test_missing_end_and_duration_is_incomplete() -> None:
    extraction = _parse(
        "Please schedule a call named 'Sync' for Sunday 19 July 2026 "
        "at 3:00 PM Europe/London. Invite me."
    )
    assert "end_or_duration" in extraction.missing


def test_a_bare_hour_without_meridiem_is_ambiguous() -> None:
    extraction = _parse(
        "Please schedule a 30-minute call named 'Sync' for Sunday 19 July 2026 at 3. Invite me."
    )
    assert "start_time" in extraction.missing


def test_a_past_event_is_never_executable() -> None:
    extraction = _parse(
        "Please schedule a call named 'Old' for Wednesday 1 July 2026 "
        "from 4:00 PM to 4:30 PM. Invite me."
    )
    assert extraction.complete
    assert not extraction.executable(reference=REFERENCE)


def test_no_attendee_request_is_incomplete_not_guessed() -> None:
    extraction = _parse(
        "Please schedule a 30-minute calendar event for Sunday, 19 July 2026, at 3:00 PM "
        "Europe/London. No guests need to be invited."
    )
    assert "attendees" in extraction.missing
    assert extraction.attendees == ()


def test_explicit_addresses_in_the_text_become_attendees() -> None:
    extraction = _parse(
        "Please schedule a call named 'Sync' for Sunday 19 July 2026 from 4:00 PM to 4:30 PM. "
        "Please invite priya@example.com and colleague@example.org."
    )
    assert extraction.attendees == ("priya@example.com", "colleague@example.org")


def test_marketing_prose_with_schedule_as_a_noun_has_no_intent() -> None:
    extraction = _parse(
        "Check out our schedule of summer events! Book of the month inside.",
        subject="Summer newsletter",
        sender=None,
    )
    assert not extraction.has_intent


def test_please_check_is_not_a_scheduling_request() -> None:
    extraction = _parse("Please check the figures by Friday.", subject="Figures", sender=None)
    assert not extraction.has_intent


def test_end_before_start_invalidates_the_range() -> None:
    extraction = _parse(
        "Please schedule a call named 'Sync' for Sunday 19 July 2026 "
        "from 4:00 PM to 3:00 PM. Invite me."
    )
    assert "end_or_duration" in extraction.missing
    assert "end_not_after_start" in extraction.reason_codes


def test_smart_and_straight_quotes_both_delimit_the_title() -> None:
    extraction = _parse(
        "Please schedule a call called 'Straight Quotes' for Sunday 19 July 2026 "
        "from 4:00 PM to 4:30 PM. Invite me."
    )
    assert extraction.title == "Straight Quotes"


def test_title_falls_back_to_the_cleaned_subject() -> None:
    extraction = _parse(
        "Please schedule a 30-minute call for Sunday 19 July 2026 at 3:00 PM. Invite me.",
        subject="Please schedule Quarterly planning",
    )
    assert extraction.title == "Quarterly planning"
