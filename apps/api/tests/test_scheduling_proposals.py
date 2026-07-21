"""Email → `create_calendar_event` proposal path (ADR 0003 D39/D41).

Covers: the schedule_request detector, calendar-candidate composition from
an inbound scheduling email, the synthetic-only gating of the demo
"(proposed)" placeholder convention, duplicate protection against events
already on the synced calendar, brief display placement, the solo-event
disclosure counter, and (integration) the full generate → persist →
approval-inbox surfacing round trip.

All clocks are frozen (`REFERENCE`); email fixtures state dates relative to
that frozen reference, so nothing rots as wall-clock time passes.
"""

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL
from tests.test_scheduling_phrases import CONTROLLED_BODY, CONTROLLED_SUBJECT

from lifeflow_api.action_payloads import CalendarEventCreatePayload
from lifeflow_api.action_proposal_service import ActionProposalService
from lifeflow_api.brief_composition import (
    BriefSectionKey,
    _count_filtered_solo_events,
    compose_sections,
)
from lifeflow_api.connectors.interfaces import CalendarEvent, EmailFolder, EmailMessage
from lifeflow_api.detectors import detect_schedule_requests, run_deterministic_detectors
from lifeflow_api.models import (
    AccountStatus,
    ActionType,
    Brief,
    BriefStatus,
    ConnectedAccount,
    Signal,
    SignalType,
    SourceItem,
    User,
)
from lifeflow_api.normalisation import email_to_source_item, event_to_source_item
from lifeflow_api.proposal_composition import (
    EXISTING_EVENT_DUPLICATE,
    compose_proposal_candidates,
)
from lifeflow_api.repositories import ActionProposalRepository

REFERENCE = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
TIMEZONE = "Europe/London"
LONDON = ZoneInfo(TIMEZONE)
USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


def _email(
    ref: str,
    *,
    subject: str = CONTROLLED_SUBJECT,
    body: str = CONTROLLED_BODY,
    sender_email: str = "abdul@example.com",
    account_id: uuid.UUID | None = None,
    user_id: uuid.UUID = USER_ID,
) -> SourceItem:
    """Built through the exact normaliser the real Google connector uses —
    including its 280-character body-preview truncation, so these tests
    prove the extraction works on what is actually persisted."""
    message = EmailMessage(
        external_id=ref,
        folder=EmailFolder.inbox,
        sender_name="Abdul Omeni",
        sender_email=sender_email,
        recipients=("me@example.test",),
        subject=subject,
        body_text=body,
        sent_at=REFERENCE,
        thread_id=f"thread-{ref}",
    )
    return email_to_source_item(message, user_id=user_id, account_id=account_id)


def _calendar_item(
    ref: str,
    *,
    title: str,
    starts_at: datetime,
    ends_at: datetime,
    attendees: tuple[str, ...] = (),
    account_id: uuid.UUID | None = None,
    user_id: uuid.UUID = USER_ID,
) -> SourceItem:
    event = CalendarEvent(
        external_id=ref,
        title=title,
        organiser_email="me@example.test",
        starts_at=starts_at,
        ends_at=ends_at,
        location=None,
        description="",
        attendees=attendees,
        all_day=False,
    )
    return event_to_source_item(event, user_id=user_id, account_id=account_id)


def _schedule_signal(
    source: SourceItem,
    *,
    confidence: float = 0.9,
    priority: float = 0.7,
    user_id: uuid.UUID = USER_ID,
) -> Signal:
    return Signal(
        id=uuid.uuid4(),
        user_id=user_id,
        signal_type="schedule_request",
        title=f"Scheduling request: {source.title}",
        summary="Evidenced scheduling request for composition testing.",
        evidence_refs=[source.external_id],
        due_at=datetime(2026, 7, 19, 16, 0, tzinfo=LONDON),
        confidence=confidence,
        urgency=0.6,
        importance=0.5,
        extraction_version="det-v1",
        priority_score=priority,
        priority_band="high",
        reason_codes=["schedule_request", "event_details_extracted"],
        dedupe_key=uuid.uuid5(user_id, f"dedupe:schedule:{source.external_id}").hex,
    )


# --- Detection -------------------------------------------------------------


def test_controlled_email_yields_one_schedule_request_signal_and_no_generic_request() -> None:
    items = [_email("em-sched-1")]
    result = run_deterministic_detectors(items, reference=REFERENCE, timezone=TIMEZONE)
    schedule = [s for s in result.signals if s.signal_type == SignalType.schedule_request]
    generic = [s for s in result.signals if s.signal_type == SignalType.request]
    deadlines = [s for s in result.signals if s.signal_type == SignalType.deadline]
    assert len(schedule) == 1
    assert schedule[0].confidence == 0.9
    assert schedule[0].due_at == datetime(2026, 7, 19, 16, 0, tzinfo=LONDON)
    assert "event_details_extracted" in schedule[0].reason_codes
    assert schedule[0].evidence_refs == ("em-sched-1",)
    assert not generic, "'please schedule' must be scheduling, not a generic request"
    assert not deadlines, "a scheduling email must not double-report as a deadline"


def test_incomplete_scheduling_email_is_a_low_confidence_clarification_signal() -> None:
    body = (
        "Please schedule a 30-minute calendar event for Sunday, 19 July 2026, at 3:00 PM "
        "Europe/London. Title: LifeFlow Calendar Verification Test 2. "
        "No guests need to be invited."
    )
    signals = detect_schedule_requests(
        [_email("em-sched-2", subject="Calendar test", body=body)],
        timezone=TIMEZONE,
        reference=REFERENCE,
    )
    assert len(signals) == 1
    assert signals[0].confidence < 0.5
    assert "event_details_incomplete" in signals[0].reason_codes
    assert "missing_attendees" in signals[0].reason_codes
    assert signals[0].due_at is None


def test_past_event_scheduling_email_is_not_executable() -> None:
    body = (
        "Please schedule a call named 'Old' for Wednesday 1 July 2026 "
        "from 4:00 PM to 4:30 PM. Invite me."
    )
    signals = detect_schedule_requests(
        [_email("em-sched-3", subject="Old event", body=body)],
        timezone=TIMEZONE,
        reference=REFERENCE,
    )
    assert len(signals) == 1
    assert signals[0].confidence < 0.5
    assert "event_in_past" in signals[0].reason_codes


def test_bulk_mail_never_yields_a_schedule_request() -> None:
    message = EmailMessage(
        external_id="em-bulk",
        folder=EmailFolder.inbox,
        sender_name="Marketing",
        sender_email="marketing@example.com",
        recipients=("me@example.test",),
        subject="Please schedule your demo!",
        body_text="Please schedule a demo today. Unsubscribe here.",
        sent_at=REFERENCE,
        thread_id="thread-bulk",
    )
    item = email_to_source_item(message, user_id=USER_ID, account_id=None)
    assert detect_schedule_requests([item], timezone=TIMEZONE, reference=REFERENCE) == []


def test_ordinary_reply_request_still_becomes_a_request_not_a_schedule() -> None:
    body = "Could you send over the Q3 figures? Thanks."
    items = [_email("em-req-1", subject="Q3 figures", body=body)]
    result = run_deterministic_detectors(items, reference=REFERENCE, timezone=TIMEZONE)
    assert any(s.signal_type == SignalType.request for s in result.signals)
    assert not any(s.signal_type == SignalType.schedule_request for s in result.signals)


# --- Composition -----------------------------------------------------------


def test_schedule_signal_composes_an_exact_calendar_candidate() -> None:
    source = _email("em-sched-4")
    signal = _schedule_signal(source)
    composed = compose_proposal_candidates(
        [signal], [source], reference=REFERENCE, timezone=TIMEZONE
    )
    events = [c for c in composed.candidates if c.action_type == ActionType.create_calendar_event]
    assert len(events) == 1
    payload = events[0].payload
    assert isinstance(payload, CalendarEventCreatePayload)
    assert payload.title == "LifeFlow Calendar Verification Test 3"
    assert payload.starts_at == datetime(2026, 7, 19, 16, 0, tzinfo=LONDON)
    assert payload.ends_at == datetime(2026, 7, 19, 16, 30, tzinfo=LONDON)
    assert payload.timezone == "Europe/London"
    assert payload.attendees == ["abdul@example.com"]
    assert events[0].source_refs == ("em-sched-4",)
    assert str(events[0].risk_level) == "medium"


def test_incomplete_schedule_signal_composes_nothing() -> None:
    body = (
        "Please schedule a 30-minute calendar event for Sunday, 19 July 2026, at 3:00 PM. "
        "No guests need to be invited."
    )
    source = _email("em-sched-5", subject="Calendar test", body=body)
    signal = _schedule_signal(source, confidence=0.45)
    composed = compose_proposal_candidates(
        [signal], [source], reference=REFERENCE, timezone=TIMEZONE
    )
    assert composed.candidates == ()
    assert composed.skipped == ()


def test_existing_synced_event_suppresses_a_duplicate_candidate() -> None:
    source = _email("em-sched-6")
    existing = _calendar_item(
        "ev-existing",
        title="LifeFlow Calendar Verification Test 3",
        starts_at=datetime(2026, 7, 19, 16, 0, tzinfo=LONDON),
        ends_at=datetime(2026, 7, 19, 16, 30, tzinfo=LONDON),
    )
    signal = _schedule_signal(source)
    composed = compose_proposal_candidates(
        [signal], [source, existing], reference=REFERENCE, timezone=TIMEZONE
    )
    assert composed.candidates == ()
    assert [s.reason_code for s in composed.skipped] == [EXISTING_EVENT_DUPLICATE]


def test_two_scheduling_emails_compose_two_distinct_origins() -> None:
    source_a = _email("em-sched-7a")
    body_b = CONTROLLED_BODY.replace("Test 3", "Test 4").replace(
        "4:00 PM to 4:30 PM", "5:00 PM to 5:30 PM"
    )
    source_b = _email("em-sched-7b", body=body_b)
    signals = [_schedule_signal(source_a), _schedule_signal(source_b)]
    composed = compose_proposal_candidates(
        signals, [source_a, source_b], reference=REFERENCE, timezone=TIMEZONE
    )
    events = [c for c in composed.candidates if c.action_type == ActionType.create_calendar_event]
    assert len(events) == 2
    assert events[0].origin_fingerprint != events[1].origin_fingerprint


def test_google_synced_proposed_placeholder_never_composes_a_sibling_event() -> None:
    """ADR 0003 D41: the "(proposed)" placeholder convention is demo-only.
    The identical evidence composes when synthetic and must not when it
    belongs to a connected Google account — otherwise approval would create
    a near-duplicate next to the user's own real event."""
    google_account_id = uuid.uuid4()
    placeholder = _calendar_item(
        "ev-proposed",
        title="Data audit kickoff (proposed)",
        starts_at=datetime(2026, 7, 21, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 21, 11, 0, tzinfo=UTC),
        attendees=("me@example.test", "rachel@example.test"),
        account_id=google_account_id,
    )
    meeting_signal = Signal(
        id=uuid.uuid4(),
        user_id=USER_ID,
        signal_type="meeting",
        title="Meeting: Data audit kickoff (proposed)",
        summary="Two attendees.",
        evidence_refs=["ev-proposed"],
        due_at=placeholder.occurred_at,
        confidence=0.95,
        urgency=0.4,
        importance=0.4,
        extraction_version="det-v1",
        priority_score=0.5,
        priority_band="medium",
        reason_codes=["meeting_upcoming"],
        dedupe_key=uuid.uuid5(USER_ID, "dedupe:meeting:ev-proposed").hex,
    )

    gated = compose_proposal_candidates(
        [meeting_signal],
        [placeholder],
        reference=REFERENCE,
        timezone=TIMEZONE,
        google_account_ids=frozenset({google_account_id}),
    )
    assert gated.candidates == ()

    synthetic = compose_proposal_candidates(
        [meeting_signal],
        [placeholder],
        reference=REFERENCE,
        timezone=TIMEZONE,
        google_account_ids=frozenset(),
    )
    assert [c.action_type for c in synthetic.candidates] == [ActionType.create_calendar_event]


# --- Brief display ---------------------------------------------------------


def test_executable_schedule_request_lands_in_needs_attention_with_an_action() -> None:
    source = _email("em-sched-8")
    signal = _schedule_signal(source)
    composed = compose_sections([signal], [source])
    needs = next(s for s in composed.sections if s.key == BriefSectionKey.needs_attention)
    assert [item.signal_type for item in needs.items] == ["schedule_request"]
    assert needs.items[0].actionable
    assert needs.items[0].suggested_action is not None


def test_incomplete_schedule_request_lands_in_low_confidence_review() -> None:
    source = _email("em-sched-9")
    signal = _schedule_signal(source, confidence=0.45)
    composed = compose_sections([signal], [source])
    low = next(s for s in composed.sections if s.key == BriefSectionKey.low_confidence_review)
    assert [item.signal_type for item in low.items] == ["schedule_request"]
    assert not low.items[0].actionable


def test_filtered_solo_event_counter_matches_the_meeting_threshold() -> None:
    solo_future = _calendar_item(
        "ev-solo",
        title="Dentist",
        starts_at=datetime(2026, 7, 20, 9, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 20, 9, 30, tzinfo=UTC),
    )
    meeting = _calendar_item(
        "ev-meeting",
        title="Team sync",
        starts_at=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 20, 10, 30, tzinfo=UTC),
        attendees=("a@example.test", "b@example.test"),
    )
    past_solo = _calendar_item(
        "ev-past",
        title="Old appointment",
        starts_at=datetime(2026, 7, 10, 9, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 10, 9, 30, tzinfo=UTC),
    )
    assert _count_filtered_solo_events([solo_future, meeting, past_solo], reference=REFERENCE) == 1


# --- Integration: generate → persist → approval inbox ----------------------

pytest_integration = pytest.mark.integration


@pytest_integration
async def test_scheduling_email_round_trip_creates_one_idempotent_proposal() -> None:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        user = await _user_with_synthetic_account(session)
        service = ActionProposalService(session, user.id)
        source = _email("em-sched-rt", user_id=user.id)
        signal = _schedule_signal(source, user_id=user.id)
        session.add(source)
        await session.flush()

        brief1 = await _brief(session, user, version=1)
        summary1 = await service.generate_from_brief(
            brief=brief1,
            signals=[signal],
            sources=[source],
            timezone=TIMEZONE,
            reference=REFERENCE,
        )
        assert summary1.created == 1

        proposals = await ActionProposalRepository(session, user.id).list()
        events = [p for p in proposals if p.action_type == ActionType.create_calendar_event]
        assert len(events) == 1
        assert events[0].source_refs == ["em-sched-rt"]
        assert events[0].payload_json["title"] == "LifeFlow Calendar Verification Test 3"
        assert events[0].payload_json["attendees"] == ["abdul@example.com"]

        brief2 = await _brief(session, user, version=2)
        summary2 = await service.generate_from_brief(
            brief=brief2,
            signals=[signal],
            sources=[source],
            timezone=TIMEZONE,
            reference=REFERENCE,
        )
        assert summary2.created == 0
        assert summary2.unchanged == 1
        events_after = [
            p
            for p in await ActionProposalRepository(session, user.id).list()
            if p.action_type == ActionType.create_calendar_event
        ]
        assert len(events_after) == 1
        await session.commit()
    await engine.dispose()


async def _user_with_synthetic_account(session: AsyncSession) -> User:
    user = User(email=f"sched-{uuid.uuid4()}@example.com", display_name="Sched Test")
    session.add(user)
    await session.flush()
    session.add(
        ConnectedAccount(
            user_id=user.id,
            provider="synthetic",
            encrypted_access_token=None,
            encrypted_refresh_token=None,
            granted_scopes=["demo"],
            expires_at=None,
            status=AccountStatus.active,
            last_sync_at=None,
        )
    )
    await session.flush()
    return user


async def _brief(session: AsyncSession, user: User, *, version: int) -> Brief:
    brief = Brief(
        user_id=user.id,
        briefing_date=REFERENCE,
        version=version,
        status=BriefStatus.complete,
        summary="Scheduling test brief",
        sections_json={},
        source_window="test-window",
    )
    session.add(brief)
    await session.flush()
    return brief


def test_list_unsubscribe_marked_mail_yields_no_signals_despite_request_cues() -> None:
    """ADR 0003 D42: real promotional mail that dodges the sender/keyword
    heuristics is still excluded once its List-Unsubscribe marker is
    recorded — it can never occupy the one active draft slot again."""
    message = EmailMessage(
        external_id="em-promo-flagged",
        folder=EmailFolder.inbox,
        sender_name="Big Shop",
        sender_email="deals@bigshop.example",
        recipients=("me@example.test",),
        subject="Could you check our summer sale?",
        body_text="Could you check our summer sale? Please reply for a voucher.",
        sent_at=REFERENCE,
        thread_id="thread-promo",
        list_unsubscribe=True,
    )
    item = email_to_source_item(message, user_id=USER_ID, account_id=None)
    assert item.metadata_json["list_unsubscribe"] is True
    result = run_deterministic_detectors([item], reference=REFERENCE, timezone=TIMEZONE)
    assert result.signals == []
