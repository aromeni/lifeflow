"""Stage 8 Phase 3: visible, reviewable adaptation from a confirmed sign-off
(ADR 0004 D57).

The adaptation happens during *composition* only. A confirmed sign-off reaches
the composer solely as the explicit `preferred_email_signoff` preference; the
adapted body is part of the payload (and its hash), approval stays mandatory,
recipients never change, and existing user-touched proposals are immutable.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL

from lifeflow_api.action_payloads import action_payload_hash
from lifeflow_api.action_proposal_service import ActionProposalService
from lifeflow_api.connectors.interfaces import EmailFolder, EmailMessage
from lifeflow_api.models import (
    ActionType,
    Brief,
    Preference,
    ProposalStatus,
    Provenance,
    Signal,
    SourceItem,
    User,
)
from lifeflow_api.normalisation import email_to_source_item
from lifeflow_api.preferences import PREFERRED_EMAIL_SIGNOFF_KEY
from lifeflow_api.proposal_composition import (
    candidate_payload_json,
    compose_proposal_candidates,
)
from lifeflow_api.repositories import ActionProposalRepository

REFERENCE = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
TIMEZONE = "Europe/London"
USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000bb")


def _request_email(ref: str = "em-req-1", *, user_id: uuid.UUID = USER_ID) -> SourceItem:
    message = EmailMessage(
        external_id=ref,
        folder=EmailFolder.inbox,
        sender_name="Priya Chandra",
        sender_email="priya@thameside-analytics.example",
        recipients=("me@example.test",),
        subject="Could you review the Q3 draft?",
        body_text="Hi — could you take a look at the Q3 draft when you get a moment? Thanks, Priya",
        sent_at=REFERENCE,
        thread_id=f"thread-{ref}",
    )
    return email_to_source_item(message, user_id=user_id, account_id=None)


def _request_signal(source: SourceItem, *, user_id: uuid.UUID = USER_ID) -> Signal:
    return Signal(
        id=uuid.uuid4(),
        user_id=user_id,
        signal_type="request",
        title=f"Request: {source.title}",
        summary="Evidenced request for composition testing.",
        evidence_refs=[source.external_id],
        due_at=None,
        confidence=0.9,
        urgency=0.6,
        importance=0.5,
        extraction_version="det-v1",
        priority_score=0.7,
        priority_band="high",
        reason_codes=["request"],
        dedupe_key=uuid.uuid5(user_id, f"req:{source.external_id}").hex,
    )


def _draft(composed) -> object:
    drafts = [c for c in composed.candidates if c.action_type == ActionType.create_gmail_draft]
    assert len(drafts) == 1
    return drafts[0]


# --- Pure composition (tests 31, 33, 34, 38) --------------------------------


def test_default_signoff_when_no_preference() -> None:
    source = _request_email()
    composed = compose_proposal_candidates(
        [_request_signal(source)], [source], reference=REFERENCE, timezone=TIMEZONE
    )
    draft = _draft(composed)
    assert draft.payload.body.rstrip().endswith("Best")
    assert "confirmed preference" not in draft.rationale


def test_confirmed_signoff_is_applied_and_provenance_recorded() -> None:
    source = _request_email()
    composed = compose_proposal_candidates(
        [_request_signal(source)],
        [source],
        reference=REFERENCE,
        timezone=TIMEZONE,
        preferred_signoff="Kind regards",
    )
    draft = _draft(composed)
    assert draft.payload.body.rstrip().endswith("Kind regards")
    assert not draft.payload.body.rstrip().endswith("Best")
    # Provenance is recorded in the proposal the user reviews (D57).
    assert "Sign-off applied from your confirmed preference." in draft.rationale


def test_adapted_body_changes_the_payload_hash() -> None:
    """The adapted body is part of the canonical payload, so it is part of the
    approval-binding hash automatically — nothing about approval is bypassed."""
    source = _request_email()
    signal = _request_signal(source)
    default = _draft(
        compose_proposal_candidates([signal], [source], reference=REFERENCE, timezone=TIMEZONE)
    )
    adapted = _draft(
        compose_proposal_candidates(
            [signal],
            [source],
            reference=REFERENCE,
            timezone=TIMEZONE,
            preferred_signoff="Kind regards",
        )
    )
    default_hash = action_payload_hash(
        ActionType.create_gmail_draft, candidate_payload_json(default)
    )
    adapted_hash = action_payload_hash(
        ActionType.create_gmail_draft, candidate_payload_json(adapted)
    )
    assert default_hash != adapted_hash


def test_signoff_never_changes_recipients() -> None:
    source = _request_email()
    signal = _request_signal(source)
    default = _draft(
        compose_proposal_candidates([signal], [source], reference=REFERENCE, timezone=TIMEZONE)
    )
    adapted = _draft(
        compose_proposal_candidates(
            [signal],
            [source],
            reference=REFERENCE,
            timezone=TIMEZONE,
            preferred_signoff="Kind regards",
        )
    )
    assert default.payload.to == adapted.payload.to  # recipients are evidence-derived only


def test_value_equal_to_default_is_not_flagged_as_applied() -> None:
    source = _request_email()
    composed = compose_proposal_candidates(
        [_request_signal(source)],
        [source],
        reference=REFERENCE,
        timezone=TIMEZONE,
        preferred_signoff="Best",  # equals the system default
    )
    draft = _draft(composed)
    assert "confirmed preference" not in draft.rationale


# --- Integration: full generation path (tests 31, 32, 35) -------------------


@pytest.fixture
async def session():
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


async def _user(session: AsyncSession) -> User:
    user = User(
        email=f"adapt-{uuid.uuid4()}@example.com",
        display_name="Adapt",
        timezone=TIMEZONE,
    )
    session.add(user)
    await session.flush()
    return user


async def _brief(session: AsyncSession, user_id: uuid.UUID) -> Brief:
    brief = Brief(
        user_id=user_id,
        briefing_date=REFERENCE,
        version=1,
        summary="Test brief.",
        sections_json={"sections": []},
        source_window="14d",
        model_metadata={},
    )
    session.add(brief)
    await session.flush()
    return brief


async def _set_signoff(session: AsyncSession, user_id: uuid.UUID, value: str) -> None:
    session.add(
        Preference(
            user_id=user_id,
            key=PREFERRED_EMAIL_SIGNOFF_KEY,
            value_json={"value": value},
            provenance=Provenance.explicit,
            confidence=None,
        )
    )
    await session.flush()


async def test_confirmed_signoff_adapts_future_draft_and_approval_still_required(
    session: AsyncSession,
) -> None:
    user = await _user(session)
    await _set_signoff(session, user.id, "Kind regards")
    brief = await _brief(session, user.id)
    source = _request_email(user_id=user.id)
    live_reference = datetime.now(UTC)
    summary = await ActionProposalService(session, user.id).generate_from_brief(
        brief=brief,
        signals=[_request_signal(source, user_id=user.id)],
        sources=[source],
        timezone=TIMEZONE,
        reference=live_reference,
        preferred_signoff="Kind regards",
    )
    assert summary.created == 1
    proposals = await ActionProposalRepository(session, user.id).list()
    draft = next(p for p in proposals if p.action_type == str(ActionType.create_gmail_draft))
    assert draft.payload_json["body"].rstrip().endswith("Kind regards")
    # Approval is still mandatory: the proposal is merely proposed, never
    # approved or executed by memory (skill §12).
    assert draft.status == str(ProposalStatus.proposed)
    assert draft.approved_at is None


async def test_user_edited_draft_is_not_rewritten_by_a_signoff_change(
    session: AsyncSession,
) -> None:
    user = await _user(session)
    brief = await _brief(session, user.id)
    source = _request_email(user_id=user.id)
    signal = _request_signal(source, user_id=user.id)
    live_reference = datetime.now(UTC)
    # First generation with the default sign-off.
    await ActionProposalService(session, user.id).generate_from_brief(
        brief=brief, signals=[signal], sources=[source], timezone=TIMEZONE, reference=live_reference
    )
    proposals = await ActionProposalRepository(session, user.id).list()
    draft = next(p for p in proposals if p.action_type == str(ActionType.create_gmail_draft))
    assert draft.payload_json["body"].rstrip().endswith("Best")
    # The user edits it (marking it user-touched and immutable to regeneration).
    draft.user_edited_at = live_reference
    draft.status = str(ProposalStatus.edited)
    await session.flush()
    # Now a sign-off is confirmed and the brief regenerates.
    await _set_signoff(session, user.id, "Kind regards")
    await ActionProposalService(session, user.id).generate_from_brief(
        brief=brief,
        signals=[signal],
        sources=[source],
        timezone=TIMEZONE,
        reference=live_reference,
        preferred_signoff="Kind regards",
    )
    await session.refresh(draft)
    # The user-edited proposal is preserved unchanged — only *newly* composed
    # candidates pick up the sign-off (D57).
    assert draft.payload_json["body"].rstrip().endswith("Best")
