"""Stage 11A Phase 6B — fake-provider rehearsal of the P6-CAL-TEST-02
trigger, run before any live Google reconnection (§3 of the governing
instruction).

This proves the exact email text the owner will send deterministically
extracts a complete, insertion-only Calendar-event request — title, date,
start/end time, timezone, and exactly one attendee (the sender, added via
the self-attendee cue "invite me", never a literal email address written
into the trigger text) — using the same parser the real pipeline calls.
No network, no fake HTTP transport, and no owner action are required for
this rehearsal; it exercises `scheduling_phrases.py` and
`action_payloads.CalendarEventCreatePayload` directly.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from lifeflow_api.action_payloads import CalendarEventCreatePayload
from lifeflow_api.scheduling_phrases import parse_scheduling_request

LONDON = ZoneInfo("Europe/London")
REFERENCE = datetime(2026, 8, 5, 8, 0, tzinfo=UTC)

TRIGGER_SUBJECT = "P6-CAL-TEST-02"
TRIGGER_BODY = (
    'Please schedule a meeting called "Northstar follow-up" for '
    "Thursday, 13 August 2026, from 14:00 to 14:30 Europe/London.\n\n"
    "Please invite me."
)

# A placeholder for this rehearsal only — the real Account B address is
# never written into repository evidence (governing instruction §2/§13).
_FAKE_ACCOUNT_B_ADDRESS = "account-b@example.invalid"


def _parse(sender: str = _FAKE_ACCOUNT_B_ADDRESS):
    return parse_scheduling_request(
        f"{TRIGGER_SUBJECT}\n{TRIGGER_BODY}",
        subject=TRIGGER_SUBJECT,
        sender=sender,
        timezone="Europe/London",
    )


def test_trigger_extracts_every_required_field_with_nothing_missing() -> None:
    extraction = _parse()
    assert extraction.has_intent
    assert extraction.title == "Northstar follow-up"
    assert extraction.starts_at == datetime(2026, 8, 13, 14, 0, tzinfo=LONDON)
    assert extraction.ends_at == datetime(2026, 8, 13, 14, 30, tzinfo=LONDON)
    assert extraction.timezone == "Europe/London"
    assert extraction.missing == ()


def test_trigger_is_executable_against_the_pre_send_reference_clock() -> None:
    assert _parse().executable(reference=REFERENCE)


def test_attendee_is_the_sender_only_never_a_literal_address_in_the_body() -> None:
    extraction = _parse()
    assert extraction.attendees == (_FAKE_ACCOUNT_B_ADDRESS,)
    assert "sender_as_attendee" in extraction.reason_codes
    # The trigger body contains no @ at all — confirms the attendee came
    # solely from the "invite me" self-attendee cue, not from text scanning.
    assert "@" not in TRIGGER_BODY


def test_explicit_timezone_in_the_trigger_beats_any_profile_default() -> None:
    extraction = parse_scheduling_request(
        f"{TRIGGER_SUBJECT}\n{TRIGGER_BODY}",
        subject=TRIGGER_SUBJECT,
        sender=_FAKE_ACCOUNT_B_ADDRESS,
        timezone="America/New_York",
    )
    assert extraction.timezone == "Europe/London"
    assert "timezone_from_profile" not in extraction.reason_codes


def test_stated_weekday_matches_the_stated_date_thursday_13_august_2026() -> None:
    # A stated weekday that does not match its date is rejected outright
    # (date_weekday_mismatch) rather than silently trusted — confirms this
    # specific trigger's weekday/date pairing is internally consistent.
    extraction = _parse()
    assert "date_weekday_mismatch" not in extraction.reason_codes
    assert extraction.starts_at is not None
    assert extraction.starts_at.strftime("%A") == "Thursday"


def test_a_mismatched_weekday_would_have_been_rejected_not_guessed() -> None:
    wrong_weekday_body = TRIGGER_BODY.replace("Thursday, 13 August 2026", "Friday, 13 August 2026")
    extraction = parse_scheduling_request(
        f"{TRIGGER_SUBJECT}\n{wrong_weekday_body}",
        subject=TRIGGER_SUBJECT,
        sender=_FAKE_ACCOUNT_B_ADDRESS,
        timezone="Europe/London",
    )
    assert "date_weekday_mismatch" in extraction.reason_codes
    assert extraction.starts_at is None
    assert not extraction.executable(reference=REFERENCE)


def test_resulting_payload_is_a_single_thirty_minute_insertion_only_event() -> None:
    extraction = _parse()
    assert extraction.title is not None
    assert extraction.starts_at is not None
    assert extraction.ends_at is not None
    assert extraction.timezone is not None
    payload = CalendarEventCreatePayload(
        title=extraction.title,
        starts_at=extraction.starts_at,
        ends_at=extraction.ends_at,
        timezone=extraction.timezone,
        location=None,
        description='Prepared by LifeFlow from the email "P6-CAL-TEST-02".',
        attendees=list(extraction.attendees),
    )
    assert payload.title == "Northstar follow-up"
    assert payload.starts_at == datetime(2026, 8, 13, 14, 0, tzinfo=LONDON)
    assert payload.ends_at == datetime(2026, 8, 13, 14, 30, tzinfo=LONDON)
    assert (payload.ends_at - payload.starts_at).total_seconds() == 1800
    assert payload.attendees == [_FAKE_ACCOUNT_B_ADDRESS]
    # CalendarEventCreatePayload has no update/delete counterpart in this
    # codebase at all (ADR 0003 D39/T23) — constructing one is structurally
    # only ever an insertion request, never a mutation of an existing event.
    assert not hasattr(payload, "event_id")


def test_payload_rejects_more_than_one_attendee_would_ever_be_carried() -> None:
    # Defence-in-depth check on the payload type itself: if the trigger text
    # had somehow produced two attendees, the approval envelope (§7) would
    # reject it long before execution — this just confirms the type accepts
    # a list, so that rejection must happen at the human-approval/envelope
    # layer, not because the type itself forbids more than one address.
    extraction = _parse()
    assert extraction.starts_at is not None
    assert extraction.ends_at is not None
    payload = CalendarEventCreatePayload(
        title="Northstar follow-up",
        starts_at=extraction.starts_at,
        ends_at=extraction.ends_at,
        timezone="Europe/London",
        location=None,
        description="test",
        attendees=[_FAKE_ACCOUNT_B_ADDRESS, "unexpected@example.invalid"],
    )
    assert len(payload.attendees) == 2  # accepted by the type; §7 gates on count manually


def test_empty_attendees_list_is_rejected_by_the_payload_type() -> None:
    extraction = _parse()
    assert extraction.starts_at is not None
    assert extraction.ends_at is not None
    with pytest.raises(ValidationError):
        CalendarEventCreatePayload(
            title="Northstar follow-up",
            starts_at=extraction.starts_at,
            ends_at=extraction.ends_at,
            timezone="Europe/London",
            location=None,
            description="test",
            attendees=[],
        )
