"""Stage 8 Phase 3: the inferred-memory recompute lifecycle (ADR 0004 D53-D58).

Database-level behaviour with a controllable clock and deterministic evidence
fixtures — no Redis, no LLM. Covers evidence gathering, confidence, precedence
against explicit preferences, dismissal stickiness, decay, idempotency, safe
sources, pause, and account-deletion cascade.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL

from lifeflow_api.action_payloads import GmailDraftCreatePayload, action_payload_hash
from lifeflow_api.memory import MemoryService
from lifeflow_api.memory_inference import (
    expire_all_stale_memory,
    expire_stale_candidates,
    gather_signoff_observations,
    recompute_user_memory,
)
from lifeflow_api.memory_registry import PREFERRED_EMAIL_SIGNOFF_KEY
from lifeflow_api.models import (
    ActionProposal,
    ActionType,
    AuditEvent,
    MemoryEvidence,
    MemoryItem,
    MemoryStatus,
    Preference,
    ProposalStatus,
    Provenance,
    SourceItem,
    SourceType,
    User,
)
from lifeflow_api.preferences import MEMORY_INFERENCE_ENABLED_KEY

pytestmark = pytest.mark.integration

NOW = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


async def _make_user(session: AsyncSession, *, marker: str = "mem") -> User:
    user = User(
        email=f"{marker}-{uuid.uuid4()}@example.com",
        display_name="Memory Tester",
        timezone="Europe/London",
    )
    session.add(user)
    await session.flush()
    return user


async def _enable_inference(
    session: AsyncSession, user_id: uuid.UUID, *, enabled: bool = True
) -> None:
    session.add(
        Preference(
            user_id=user_id,
            key=MEMORY_INFERENCE_ENABLED_KEY,
            value_json={"enabled": enabled},
            provenance=Provenance.explicit,
            confidence=None,
        )
    )
    await session.flush()


async def _set_explicit_signoff(session: AsyncSession, user_id: uuid.UUID, value: str) -> None:
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


async def _edited_draft(
    session: AsyncSession,
    user_id: uuid.UUID,
    signoff: str,
    *,
    ref: str,
    observed_at: datetime = NOW,
    status: ProposalStatus = ProposalStatus.approved,
    user_edited: bool = True,
) -> ActionProposal:
    """A `create_gmail_draft` proposal ending with `signoff` — the one
    evidence source for inferred memory (D53). `user_edited=False` and
    non-approved statuses model actions that must NOT qualify."""
    payload = GmailDraftCreatePayload(
        to=["someone@example.test"],
        subject="Re: Something",
        body=f"Hi there,\n\nThanks for your message.\n\n{signoff}",
        thread_id=None,
    )
    payload_json = payload.model_dump(mode="json")
    proposal = ActionProposal(
        user_id=user_id,
        origin_fingerprint=f"fp-{ref}-{uuid.uuid4().hex}",
        action_type=str(ActionType.create_gmail_draft),
        rationale="Prepare a draft reply.",
        source_refs=[],
        payload_json=payload_json,
        payload_hash=action_payload_hash(ActionType.create_gmail_draft, payload_json),
        version=2 if user_edited else 1,
        risk_level="medium",
        confidence=0.8,
        status=str(status),
        expires_at=observed_at + timedelta(days=7),
        user_edited_at=observed_at if user_edited else None,
    )
    session.add(proposal)
    await session.flush()
    return proposal


async def _item(session: AsyncSession, user_id: uuid.UUID) -> MemoryItem | None:
    result = await session.execute(
        select(MemoryItem).where(
            MemoryItem.user_id == user_id, MemoryItem.memory_key == PREFERRED_EMAIL_SIGNOFF_KEY
        )
    )
    return result.scalar_one_or_none()


# --- Evidence gathering & safe sources (tests 12, 13, 14) -------------------


async def test_only_user_edited_approved_gmail_drafts_are_evidence(session: AsyncSession) -> None:
    user = await _make_user(session)
    await _edited_draft(session, user.id, "Best", ref="approved-edited")
    await _edited_draft(session, user.id, "Regards", ref="not-edited", user_edited=False)
    await _edited_draft(session, user.id, "Cheers", ref="rejected", status=ProposalStatus.rejected)
    observations = await gather_signoff_observations(session, user.id)
    assert [o.value for o in observations] == ["Best"]


async def test_inbound_email_text_alone_creates_no_preference(session: AsyncSession) -> None:
    """A recognised sign-off phrase in a *received* email is not the user's
    preference — nothing in inference reads SourceItem content (skill §11.1)."""
    user = await _make_user(session)
    await _enable_inference(session, user.id)
    session.add(
        SourceItem(
            user_id=user.id,
            source_type=str(SourceType.email),
            external_id="em-inbound-1",
            title="Newsletter",
            sender_or_organiser="marketing@example.test",
            occurred_at=NOW,
            metadata_json={"folder": "inbox", "body_preview": "Buy now!\n\nKind regards\nThe Team"},
            content_fingerprint="cf-1",
        )
    )
    await session.flush()
    result = await recompute_user_memory(session, user.id, now=NOW)
    assert result.observations == 0
    assert await _item(session, user.id) is None


# --- Candidate creation & confidence (tests 6, 7, 8) ------------------------


async def test_one_observation_makes_a_low_confidence_unsurfaced_candidate(
    session: AsyncSession,
) -> None:
    user = await _make_user(session)
    await _enable_inference(session, user.id)
    await _edited_draft(session, user.id, "Best", ref="one")
    await recompute_user_memory(session, user.id, now=NOW)
    item = await _item(session, user.id)
    assert item is not None
    assert item.status == MemoryStatus.candidate
    assert item.evidence_count == 1  # below MIN_EVIDENCE=2 → not surfaced-active
    assert item.confidence <= 0.25


async def test_repeated_consistent_observations_make_one_candidate(session: AsyncSession) -> None:
    user = await _make_user(session)
    await _enable_inference(session, user.id)
    for i in range(3):
        await _edited_draft(session, user.id, "Kind regards", ref=f"k{i}")
    await recompute_user_memory(session, user.id, now=NOW)
    item = await _item(session, user.id)
    assert item is not None
    assert item.value_json == {"value": "Kind regards"}
    assert item.evidence_count == 3
    assert item.status == MemoryStatus.candidate
    # Exactly one memory item and three evidence rows.
    items = (
        (await session.execute(select(MemoryItem).where(MemoryItem.user_id == user.id)))
        .scalars()
        .all()
    )
    assert len(items) == 1
    evidence = (
        (await session.execute(select(MemoryEvidence).where(MemoryEvidence.user_id == user.id)))
        .scalars()
        .all()
    )
    assert len(evidence) == 3


async def test_recompute_is_idempotent(session: AsyncSession) -> None:
    user = await _make_user(session)
    await _enable_inference(session, user.id)
    for i in range(2):
        await _edited_draft(session, user.id, "Best", ref=f"b{i}")
    first = await recompute_user_memory(session, user.id, now=NOW)
    second = await recompute_user_memory(session, user.id, now=NOW)
    assert first.evidence_added == 2
    assert second.evidence_added == 0  # nothing new to record
    evidence = (
        (await session.execute(select(MemoryEvidence).where(MemoryEvidence.user_id == user.id)))
        .scalars()
        .all()
    )
    assert len(evidence) == 2


async def test_second_independent_recompute_never_duplicates(session: AsyncSession) -> None:
    """A second worker (e.g. a redundant enqueue, or the self-healing rescan)
    running after the first committed must never create a duplicate item or
    evidence — the `(user_id, memory_key)` and `(memory_item_id,
    source_proposal_id)` unique constraints are the final guards (D56)."""
    user = await _make_user(session)
    await _enable_inference(session, user.id)
    for i in range(2):
        await _edited_draft(session, user.id, "Best", ref=f"c{i}")
    await session.commit()

    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s1:
        await recompute_user_memory(s1, user.id, now=NOW)
        await s1.commit()
    async with maker() as s2:
        result = await recompute_user_memory(s2, user.id, now=NOW)
        await s2.commit()
        assert result.evidence_added == 0  # the second run finds nothing new
    await engine.dispose()

    items = (
        (await session.execute(select(MemoryItem).where(MemoryItem.user_id == user.id)))
        .scalars()
        .all()
    )
    assert len(items) == 1
    evidence = (
        (await session.execute(select(MemoryEvidence).where(MemoryEvidence.user_id == user.id)))
        .scalars()
        .all()
    )
    assert len(evidence) == 2


# --- Contradiction & decay (tests 10, 11) -----------------------------------


async def test_contradictory_evidence_updates_dominant_value_visibly(session: AsyncSession) -> None:
    user = await _make_user(session)
    await _enable_inference(session, user.id)
    for i in range(2):
        await _edited_draft(session, user.id, "Best", ref=f"first{i}")
    await recompute_user_memory(session, user.id, now=NOW)
    # Three newer, consistent "Kind regards" edits overtake the dominant value.
    for i in range(3):
        await _edited_draft(session, user.id, "Kind regards", ref=f"second{i}")
    await recompute_user_memory(session, user.id, now=NOW)
    item = await _item(session, user.id)
    assert item is not None
    assert item.value_json == {"value": "Kind regards"}  # dominant flipped, visible
    assert item.evidence_count == 3


async def test_old_evidence_decays_to_expired(session: AsyncSession) -> None:
    user = await _make_user(session)
    await _enable_inference(session, user.id)
    for i in range(2):
        await _edited_draft(session, user.id, "Best", ref=f"old{i}", observed_at=NOW)
    # Recompute a year later: freshness collapses below the expiry floor.
    much_later = NOW + timedelta(days=365)
    await recompute_user_memory(session, user.id, now=much_later)
    item = await _item(session, user.id)
    assert item is not None
    assert item.status == MemoryStatus.expired


# --- Precedence against explicit preferences (tests 15, 16, 17, 18) ---------


async def test_explicit_preference_supersedes_candidate(session: AsyncSession) -> None:
    user = await _make_user(session)
    await _enable_inference(session, user.id)
    await _set_explicit_signoff(session, user.id, "Sincerely")
    for i in range(3):
        await _edited_draft(session, user.id, "Best", ref=f"s{i}")
    await recompute_user_memory(session, user.id, now=NOW)
    item = await _item(session, user.id)
    assert item is not None
    # Visible but inactive: explicit always wins (skill §3.1).
    assert item.status == MemoryStatus.superseded
    assert item.overridden_by_explicit is True


async def test_deleting_explicit_preference_resurfaces_confirmed_as_candidate(
    session: AsyncSession,
) -> None:
    user = await _make_user(session)
    await _enable_inference(session, user.id)
    for i in range(2):
        await _edited_draft(session, user.id, "Best", ref=f"d{i}")
    await recompute_user_memory(session, user.id, now=NOW)
    item = await _item(session, user.id)
    assert item is not None
    # Confirm it (writes the explicit preference).
    await MemoryService(session, user.id).confirm(item.id, expected_version=item.version)
    confirmed = await _item(session, user.id)
    assert confirmed is not None and confirmed.status == MemoryStatus.confirmed
    # Delete the explicit preference directly (the documented fallback path).
    await session.execute(
        delete(Preference).where(
            Preference.user_id == user.id, Preference.key == PREFERRED_EMAIL_SIGNOFF_KEY
        )
    )
    await session.flush()
    await recompute_user_memory(session, user.id, now=NOW)
    resurfaced = await _item(session, user.id)
    assert resurfaced is not None
    # Falls back to system default, re-surfaces for fresh confirmation (D55).
    assert resurfaced.status == MemoryStatus.candidate


# --- Dismissal stickiness (tests 24, 25) ------------------------------------


async def test_dismissed_candidate_does_not_reappear_from_same_evidence(
    session: AsyncSession,
) -> None:
    user = await _make_user(session)
    await _enable_inference(session, user.id)
    for i in range(2):
        await _edited_draft(session, user.id, "Best", ref=f"dm{i}")
    await recompute_user_memory(session, user.id, now=NOW)
    item = await _item(session, user.id)
    assert item is not None
    await MemoryService(session, user.id).dismiss(item.id, expected_version=item.version, now=NOW)
    # Recompute over the SAME evidence keeps it dismissed.
    await recompute_user_memory(session, user.id, now=NOW)
    still = await _item(session, user.id)
    assert still is not None
    assert still.status == MemoryStatus.dismissed


async def test_materially_new_evidence_reconsiders_a_dismissed_candidate(
    session: AsyncSession,
) -> None:
    user = await _make_user(session)
    await _enable_inference(session, user.id)
    for i in range(2):
        await _edited_draft(session, user.id, "Best", ref=f"dn{i}")
    await recompute_user_memory(session, user.id, now=NOW)
    item = await _item(session, user.id)
    assert item is not None
    await MemoryService(session, user.id).dismiss(item.id, expected_version=item.version, now=NOW)
    # A genuinely new observation changes the fingerprint → reconsidered.
    await _edited_draft(session, user.id, "Best", ref="dn-new")
    await recompute_user_memory(session, user.id, now=NOW)
    reconsidered = await _item(session, user.id)
    assert reconsidered is not None
    assert reconsidered.status == MemoryStatus.candidate


# --- Pause & cascade (tests 28, 30) -----------------------------------------


async def test_paused_inference_creates_no_candidate(session: AsyncSession) -> None:
    user = await _make_user(session)
    await _enable_inference(session, user.id, enabled=False)  # default off
    for i in range(3):
        await _edited_draft(session, user.id, "Best", ref=f"p{i}")
    result = await recompute_user_memory(session, user.id, now=NOW)
    assert result.paused is True
    assert await _item(session, user.id) is None


async def test_account_deletion_cascades_memory(session: AsyncSession) -> None:
    user = await _make_user(session)
    await _enable_inference(session, user.id)
    for i in range(2):
        await _edited_draft(session, user.id, "Best", ref=f"cas{i}")
    await recompute_user_memory(session, user.id, now=NOW)
    assert await _item(session, user.id) is not None
    await session.execute(delete(User).where(User.id == user.id))
    await session.flush()
    items = (
        (await session.execute(select(MemoryItem).where(MemoryItem.user_id == user.id)))
        .scalars()
        .all()
    )
    evidence = (
        (await session.execute(select(MemoryEvidence).where(MemoryEvidence.user_id == user.id)))
        .scalars()
        .all()
    )
    assert items == []
    assert evidence == []


# --- Negative evidence: only edited-AND-approved qualifies (test 14) ---------


async def test_edited_but_unapproved_draft_creates_no_evidence(session: AsyncSession) -> None:
    """An edited draft the user has NOT yet approved is not evidence — only a
    draft the user deliberately edited and then approved qualifies (D53)."""
    user = await _make_user(session)
    await _enable_inference(session, user.id)
    # user_edited_at set, but status still 'edited' (not approved/executed).
    await _edited_draft(session, user.id, "Kind regards", ref="e1", status=ProposalStatus.edited)
    await _edited_draft(session, user.id, "Kind regards", ref="e2", status=ProposalStatus.edited)
    observations = await gather_signoff_observations(session, user.id)
    assert observations == []
    result = await recompute_user_memory(session, user.id, now=NOW)
    assert result.observations == 0
    assert await _item(session, user.id) is None


# --- Effective expiry with time alone (Point 2: tests 1-7) ------------------


async def _memory_expired_audit_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    rows = (
        (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.user_id == user_id, AuditEvent.event_type == "memory.expired"
                )
            )
        )
        .scalars()
        .all()
    )
    return len(rows)


async def test_candidate_stays_active_then_expires_with_time_alone(session: AsyncSession) -> None:
    """(1) active before the threshold; (2) time advances with no new evidence
    or user action; (3) confidence decays; (4) becomes expired below the
    floor — all via `expire_stale_candidates`, which the read routes and the
    daily cron both call."""
    user = await _make_user(session)
    await _enable_inference(session, user.id)
    for i in range(3):
        await _edited_draft(session, user.id, "Kind regards", ref=f"x{i}")
    await recompute_user_memory(session, user.id, now=NOW)
    item = await _item(session, user.id)
    assert item is not None and item.status == MemoryStatus.candidate
    active_confidence = item.confidence

    # (1) Just after evaluation it is not expired.
    expired = await expire_stale_candidates(session, user.id, now=NOW)
    assert expired == 0
    item = await _item(session, user.id)
    assert item is not None and item.status == MemoryStatus.candidate

    # (2)+(3) A year passes with no new evidence and no user action — the
    # effective confidence the API would show has decayed far below active.
    from lifeflow_api.memory_registry import effective_confidence

    much_later = NOW + timedelta(days=365)
    assert effective_confidence(active_confidence, item.last_evaluated_at, much_later) < 0.15

    # (4) Evaluating at that time expires it.
    expired = await expire_stale_candidates(session, user.id, now=much_later)
    assert expired == 1
    item = await _item(session, user.id)
    assert item is not None
    assert item.status == MemoryStatus.expired
    assert item.confidence < active_confidence  # decayed value persisted
    assert item.expires_at == much_later


async def test_expired_candidate_is_not_applicable(session: AsyncSession) -> None:
    """(5) An expired candidate is not applied to anything — it never wrote an
    explicit preference, so composition still uses the system default."""
    from lifeflow_api.preferences import explicit_signoff

    user = await _make_user(session)
    await _enable_inference(session, user.id)
    for i in range(2):
        await _edited_draft(session, user.id, "Kind regards", ref=f"na{i}")
    await recompute_user_memory(session, user.id, now=NOW)
    await expire_stale_candidates(session, user.id, now=NOW + timedelta(days=365))
    item = await _item(session, user.id)
    assert item is not None and item.status == MemoryStatus.expired
    # No explicit preference was ever written by a mere candidate/expiry.
    assert await explicit_signoff(session, user.id) is None


async def test_repeated_expiry_evaluation_audits_once(session: AsyncSession) -> None:
    """(6) Repeated evaluation does not duplicate the `memory.expired` audit —
    only a `candidate` transitions, and an already-`expired` item is skipped."""
    user = await _make_user(session)
    await _enable_inference(session, user.id)
    for i in range(2):
        await _edited_draft(session, user.id, "Kind regards", ref=f"au{i}")
    await recompute_user_memory(session, user.id, now=NOW)
    much_later = NOW + timedelta(days=365)
    for _ in range(3):
        await expire_stale_candidates(session, user.id, now=much_later)
    assert await _memory_expired_audit_count(session, user.id) == 1


async def test_confirmed_preference_never_decays(session: AsyncSession) -> None:
    """(7) A confirmed explicit preference never decays or expires — it lives
    in the preference table, and expiry only ever touches candidates."""
    from lifeflow_api.preferences import explicit_signoff

    user = await _make_user(session)
    await _enable_inference(session, user.id)
    for i in range(2):
        await _edited_draft(session, user.id, "Kind regards", ref=f"cf{i}")
    await recompute_user_memory(session, user.id, now=NOW)
    item = await _item(session, user.id)
    assert item is not None
    await MemoryService(session, user.id).confirm(item.id, expected_version=item.version)

    # Far in the future, expiry maintenance runs — the confirmed item and its
    # explicit preference are untouched.
    expired = await expire_stale_candidates(session, user.id, now=NOW + timedelta(days=3650))
    assert expired == 0
    item = await _item(session, user.id)
    assert item is not None and item.status == MemoryStatus.confirmed
    assert await explicit_signoff(session, user.id) == "Kind regards"


async def test_cross_user_maintenance_expires_all_decayed_candidates(session: AsyncSession) -> None:
    """The daily cross-user maintenance expires every user's decayed
    candidate, so expiry never depends on a user opening Settings; idempotent
    on repeat."""
    users = []
    for marker in ("cm1", "cm2"):
        user = await _make_user(session, marker=marker)
        await _enable_inference(session, user.id)
        for i in range(2):
            await _edited_draft(session, user.id, "Kind regards", ref=f"{marker}{i}")
        await recompute_user_memory(session, user.id, now=NOW)
        users.append(user)
    await session.commit()

    much_later = NOW + timedelta(days=365)
    expired = await expire_all_stale_memory(session, now=much_later)
    assert expired == 2
    for user in users:
        item = await _item(session, user.id)
        assert item is not None and item.status == MemoryStatus.expired
    # Idempotent: a second sweep changes nothing.
    assert await expire_all_stale_memory(session, now=much_later) == 0
