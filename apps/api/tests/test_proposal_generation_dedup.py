"""Stage 7 sandbox finding (ADR 0003 D36): proposal generation must not let
one signal's terminal or dead-ended proposal permanently suppress a
distinct, newer eligible signal of the same action type.

Root cause: `compose_proposal_candidates` returned only the single
highest-ranked eligible signal per action type, so once that signal's
proposal existed — regardless of its status — no other signal of the same
type was ever even composed into a candidate, let alone persisted. A second,
genuinely new Gmail message could then never produce its own proposal while
an older message's proposal sat in `executing` (uncertain execution),
`rejected`, `executed`, `failed`, or `expired`.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL
from tests.test_action_proposals import _approve

from lifeflow_api.action_executors import ExecutorOutcome, SimulatedExecutorRegistry
from lifeflow_api.action_proposal_service import ActionProposalService
from lifeflow_api.connectors.interfaces import EmailFolder, EmailMessage
from lifeflow_api.models import (
    AccountStatus,
    ActionProposal,
    ActionType,
    Brief,
    BriefStatus,
    ConnectedAccount,
    ExecutionOutcome,
    ProposalStatus,
    Signal,
    SourceItem,
    User,
)
from lifeflow_api.normalisation import email_to_source_item
from lifeflow_api.proposal_composition import compose_proposal_candidates
from lifeflow_api.repositories import ActionExecutionRepository, ActionProposalRepository

pytestmark = pytest.mark.integration

REFERENCE = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
TIMEZONE = "Europe/London"


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


async def _user_with_synthetic_account(session: AsyncSession) -> User:
    user = User(email=f"dedup-{uuid.uuid4()}@lifeflow.local", display_name="Dedup Test")
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
        summary="Dedup test brief",
        sections_json={},
        source_window="test-window",
    )
    session.add(brief)
    await session.flush()
    return brief


def _gmail_source(
    user_id: uuid.UUID, ref: str, *, thread_id: str, sender_email: str = "priya.shah@example.test"
) -> SourceItem:
    """Built through the exact same normaliser the real Google connector
    uses (`normalisation.email_to_source_item`) — a genuinely
    Google-normalised `SourceItem` shape, not a hand-rolled test fixture."""
    message = EmailMessage(
        external_id=ref,
        folder=EmailFolder.inbox,
        sender_name="Priya Shah",
        sender_email=sender_email,
        recipients=("me@example.test",),
        subject=f"Question about the {ref} proposal",
        body_text=f"Could you send over the details for {ref}? Thanks, Priya",
        sent_at=REFERENCE,
        thread_id=thread_id,
    )
    return email_to_source_item(message, user_id=user_id, account_id=None)


def _request_signal(
    user_id: uuid.UUID, source: SourceItem, *, dedupe_suffix: str, priority: float = 0.6
) -> Signal:
    return Signal(
        id=uuid.uuid4(),
        user_id=user_id,
        signal_type="request",
        title=f"Request: {source.title}",
        summary="Evidenced request signal for dedup testing.",
        evidence_refs=[source.external_id],
        due_at=None,
        confidence=0.8,
        urgency=0.5,
        importance=0.5,
        extraction_version="det-v1",
        priority_score=priority,
        priority_band="medium",
        reason_codes=["explicit_request"],
        dedupe_key=uuid.uuid5(user_id, f"dedupe:request:{dedupe_suffix}").hex,
    )


def _draft_proposal(proposals: list[ActionProposal]) -> ActionProposal:
    return next(p for p in proposals if p.action_type == ActionType.create_gmail_draft)


class _UncertainExecutor:
    """Mirrors the real sandbox finding: the provider call may have
    succeeded, but LifeFlow could not verify it, so the outcome is
    `uncertain`, never `succeeded` or `failed`."""

    async def execute(self, **_: object) -> ExecutorOutcome:
        return ExecutorOutcome(status="uncertain", result={"status": "uncertain"})


async def _make_uncertain(
    session: AsyncSession, user: User, proposal: ActionProposal
) -> ActionProposal:
    exec_service = ActionProposalService(
        session,
        user.id,
        executors=SimulatedExecutorRegistry({ActionType.create_gmail_draft: _UncertainExecutor()}),
        now_factory=lambda: REFERENCE,
    )
    approved = await _approve(exec_service, proposal, session=session, user=user)
    _, execution = await exec_service.execute(approved.id)
    assert execution.outcome == ExecutionOutcome.uncertain
    await session.refresh(proposal)
    assert proposal.status == ProposalStatus.executing
    return proposal


async def test_new_message_creates_proposal_despite_existing_uncertain_proposal(
    session: AsyncSession,
) -> None:
    """Requirement 1: an existing `uncertain`-execution proposal for message A
    must not block a fresh proposal for a genuinely new message B."""
    user = await _user_with_synthetic_account(session)
    service = ActionProposalService(session, user.id)

    source_a = _gmail_source(user.id, "gmail-msg-old", thread_id="thread-old")
    signal_a = _request_signal(user.id, source_a, dedupe_suffix="old", priority=0.9)
    brief1 = await _brief(session, user, version=1)
    summary1 = await service.generate_from_brief(
        brief=brief1, signals=[signal_a], sources=[source_a], timezone=TIMEZONE, reference=REFERENCE
    )
    assert summary1.created == 1
    proposal_a = _draft_proposal(await ActionProposalRepository(session, user.id).list())
    await _make_uncertain(session, user, proposal_a)

    source_b = _gmail_source(user.id, "gmail-msg-new", thread_id="thread-new")
    signal_b = _request_signal(user.id, source_b, dedupe_suffix="new", priority=0.5)
    brief2 = await _brief(session, user, version=2)
    summary2 = await service.generate_from_brief(
        brief=brief2,
        signals=[signal_a, signal_b],
        sources=[source_a, source_b],
        timezone=TIMEZONE,
        reference=REFERENCE,
    )

    assert summary2.created == 1
    assert summary2.preserved == 1

    drafts = [
        p
        for p in await ActionProposalRepository(session, user.id).list()
        if p.action_type == ActionType.create_gmail_draft
    ]
    assert len(drafts) == 2
    new_proposal = next(p for p in drafts if p.origin_fingerprint != proposal_a.origin_fingerprint)
    assert new_proposal.status == ProposalStatus.proposed
    assert new_proposal.source_refs == ["gmail-msg-new"]


@pytest.mark.parametrize(
    "terminal_status",
    [ProposalStatus.rejected, ProposalStatus.executed, ProposalStatus.failed],
)
async def test_terminal_proposal_does_not_suppress_unrelated_new_signal(
    session: AsyncSession, terminal_status: ProposalStatus
) -> None:
    """Requirements 2 and 3: a rejected or executed (and, by the same
    mechanism, failed) proposal for an old message must not suppress a
    fresh proposal for a distinct new message."""
    user = await _user_with_synthetic_account(session)
    service = ActionProposalService(session, user.id)

    source_a = _gmail_source(user.id, f"gmail-{terminal_status}-old", thread_id="thread-old")
    signal_a = _request_signal(
        user.id, source_a, dedupe_suffix=f"{terminal_status}-old", priority=0.9
    )
    brief1 = await _brief(session, user, version=1)
    await service.generate_from_brief(
        brief=brief1, signals=[signal_a], sources=[source_a], timezone=TIMEZONE, reference=REFERENCE
    )
    proposal_a = _draft_proposal(await ActionProposalRepository(session, user.id).list())
    proposal_a.status = terminal_status
    await session.flush()

    source_b = _gmail_source(user.id, f"gmail-{terminal_status}-new", thread_id="thread-new")
    signal_b = _request_signal(
        user.id, source_b, dedupe_suffix=f"{terminal_status}-new", priority=0.5
    )
    brief2 = await _brief(session, user, version=2)
    summary2 = await service.generate_from_brief(
        brief=brief2,
        signals=[signal_a, signal_b],
        sources=[source_a, source_b],
        timezone=TIMEZONE,
        reference=REFERENCE,
    )

    assert summary2.created == 1
    drafts = [
        p
        for p in await ActionProposalRepository(session, user.id).list()
        if p.action_type == ActionType.create_gmail_draft
    ]
    assert len(drafts) == 2
    await session.refresh(proposal_a)
    assert proposal_a.status == terminal_status  # untouched, immutable
    new_proposal = next(p for p in drafts if p.id != proposal_a.id)
    assert new_proposal.status == ProposalStatus.proposed
    assert new_proposal.source_refs == [f"gmail-{terminal_status}-new"]


def test_different_threads_from_the_same_sender_produce_distinct_origins() -> None:
    """Requirement 4: origin identity must distinguish message/thread
    lineage, not just sender + action type — two different threads from the
    same sender are two different candidates with two different
    fingerprints."""
    user_id = uuid.uuid4()
    source_1 = _gmail_source(user_id, "gmail-thread-1", thread_id="thread-1")
    source_2 = _gmail_source(user_id, "gmail-thread-2", thread_id="thread-2")
    signal_1 = _request_signal(user_id, source_1, dedupe_suffix="thread-1", priority=0.9)
    signal_2 = _request_signal(user_id, source_2, dedupe_suffix="thread-2", priority=0.5)

    composed = compose_proposal_candidates(
        [signal_1, signal_2], [source_1, source_2], reference=REFERENCE, timezone=TIMEZONE
    )

    drafts = [c for c in composed.candidates if c.action_type == ActionType.create_gmail_draft]
    assert len(drafts) == 2
    assert drafts[0].origin_fingerprint != drafts[1].origin_fingerprint
    assert {c.source_refs for c in drafts} == {("gmail-thread-1",), ("gmail-thread-2",)}


async def test_cap_is_filled_by_a_later_candidate_past_two_protected_terminal_proposals(
    session: AsyncSession,
) -> None:
    """Requirement 5: with several protected (terminal) proposals ranked
    ahead of it, the generator keeps walking ranked candidates until it
    fills the one active slot for the action type, rather than stopping
    after the first (still-blocked) candidate."""
    user = await _user_with_synthetic_account(session)
    service = ActionProposalService(session, user.id)

    source_a = _gmail_source(user.id, "gmail-cap-a", thread_id="thread-a")
    signal_a = _request_signal(user.id, source_a, dedupe_suffix="cap-a", priority=0.9)
    source_b = _gmail_source(user.id, "gmail-cap-b", thread_id="thread-b")
    signal_b = _request_signal(user.id, source_b, dedupe_suffix="cap-b", priority=0.8)
    brief1 = await _brief(session, user, version=1)
    await service.generate_from_brief(
        brief=brief1,
        signals=[signal_a, signal_b],
        sources=[source_a, source_b],
        timezone=TIMEZONE,
        reference=REFERENCE,
    )
    # Only A was created (the one active slot); reject it, then generate
    # again so B is created too, then reject B as well — leaving both
    # protected/terminal ahead of a third, fresh candidate C.
    proposals = await ActionProposalRepository(session, user.id).list()
    proposal_a = _draft_proposal(proposals)
    proposal_a.status = ProposalStatus.rejected
    await session.flush()

    brief2 = await _brief(session, user, version=2)
    await service.generate_from_brief(
        brief=brief2,
        signals=[signal_a, signal_b],
        sources=[source_a, source_b],
        timezone=TIMEZONE,
        reference=REFERENCE,
    )
    drafts = [
        p
        for p in await ActionProposalRepository(session, user.id).list()
        if p.action_type == ActionType.create_gmail_draft
    ]
    proposal_b = next(p for p in drafts if p.id != proposal_a.id)
    proposal_b.status = ProposalStatus.rejected
    await session.flush()

    source_c = _gmail_source(user.id, "gmail-cap-c", thread_id="thread-c")
    signal_c = _request_signal(user.id, source_c, dedupe_suffix="cap-c", priority=0.5)
    brief3 = await _brief(session, user, version=3)
    summary3 = await service.generate_from_brief(
        brief=brief3,
        signals=[signal_a, signal_b, signal_c],
        sources=[source_a, source_b, source_c],
        timezone=TIMEZONE,
        reference=REFERENCE,
    )

    assert summary3.created == 1
    assert summary3.preserved == 2
    drafts_final = [
        p
        for p in await ActionProposalRepository(session, user.id).list()
        if p.action_type == ActionType.create_gmail_draft
    ]
    assert len(drafts_final) == 3
    new_proposal = next(p for p in drafts_final if p.source_refs == ["gmail-cap-c"])
    assert new_proposal.status == ProposalStatus.proposed


async def test_regenerating_the_same_pair_of_messages_remains_idempotent(
    session: AsyncSession,
) -> None:
    """Requirement 6: once the old proposal is terminal and the new one has
    been created, regenerating from the same two signals a further time
    creates no duplicates and reports the new proposal as unchanged."""
    user = await _user_with_synthetic_account(session)
    service = ActionProposalService(session, user.id)

    source_a = _gmail_source(user.id, "gmail-idem-old", thread_id="thread-old")
    signal_a = _request_signal(user.id, source_a, dedupe_suffix="idem-old", priority=0.9)
    brief1 = await _brief(session, user, version=1)
    await service.generate_from_brief(
        brief=brief1, signals=[signal_a], sources=[source_a], timezone=TIMEZONE, reference=REFERENCE
    )
    proposal_a = _draft_proposal(await ActionProposalRepository(session, user.id).list())
    proposal_a.status = ProposalStatus.rejected
    await session.flush()

    source_b = _gmail_source(user.id, "gmail-idem-new", thread_id="thread-new")
    signal_b = _request_signal(user.id, source_b, dedupe_suffix="idem-new", priority=0.5)
    brief2 = await _brief(session, user, version=2)
    summary2 = await service.generate_from_brief(
        brief=brief2,
        signals=[signal_a, signal_b],
        sources=[source_a, source_b],
        timezone=TIMEZONE,
        reference=REFERENCE,
    )
    assert summary2.created == 1

    brief3 = await _brief(session, user, version=3)
    summary3 = await service.generate_from_brief(
        brief=brief3,
        signals=[signal_a, signal_b],
        sources=[source_a, source_b],
        timezone=TIMEZONE,
        reference=REFERENCE,
    )
    assert summary3.created == 0
    assert summary3.updated == 0
    assert summary3.unchanged == 1
    assert summary3.preserved == 1
    drafts = [
        p
        for p in await ActionProposalRepository(session, user.id).list()
        if p.action_type == ActionType.create_gmail_draft
    ]
    assert len(drafts) == 2


async def test_approval_inbox_route_returns_the_new_proposal(
    dev_client: AsyncClient,
) -> None:
    """Requirement 7 + real Google-normalised SourceItem shape: the new
    proposal must actually surface through `GET /action-proposals`, not just
    exist in the database, and the existing uncertain one must still appear
    unchanged alongside it."""
    login = await dev_client.post(
        "/auth/dev-login",
        json={"email": f"route-dedup-{uuid.uuid4()}@example.com", "display_name": "Route Dedup"},
        headers=CSRF_HEADERS,
    )
    assert login.status_code == 200
    user_id = uuid.UUID(login.json()["user_id"])

    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        user = await session.get(User, user_id)
        assert user is not None
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
        service = ActionProposalService(session, user.id)

        source_a = _gmail_source(user.id, "gmail-route-old", thread_id="thread-old")
        signal_a = _request_signal(user.id, source_a, dedupe_suffix="route-old", priority=0.9)
        session.add(source_a)
        await session.flush()
        brief1 = await _brief(session, user, version=1)
        await service.generate_from_brief(
            brief=brief1,
            signals=[signal_a],
            sources=[source_a],
            timezone=TIMEZONE,
            reference=REFERENCE,
        )
        await session.commit()

        proposal_a = _draft_proposal(await ActionProposalRepository(session, user.id).list())
        await _make_uncertain(session, user, proposal_a)
        await session.commit()

        source_b = _gmail_source(user.id, "gmail-route-new", thread_id="thread-new")
        signal_b = _request_signal(user.id, source_b, dedupe_suffix="route-new", priority=0.5)
        session.add(source_b)
        await session.flush()
        brief2 = await _brief(session, user, version=2)
        await service.generate_from_brief(
            brief=brief2,
            signals=[signal_a, signal_b],
            sources=[source_a, source_b],
            timezone=TIMEZONE,
            reference=REFERENCE,
        )
        await session.commit()
    await engine.dispose()

    listed = await dev_client.get("/action-proposals")
    assert listed.status_code == 200
    proposals = listed.json()["proposals"]
    drafts = [p for p in proposals if p["action_type"] == "create_gmail_draft"]
    assert len(drafts) == 2
    new_proposal = next(p for p in drafts if p["source_refs"] == ["gmail-route-new"])
    assert new_proposal["status"] == "proposed"
    old_proposal = next(p for p in drafts if p["source_refs"] == ["gmail-route-old"])
    assert old_proposal["execution"]["effective_status"] == "uncertain"


async def test_uncertain_execution_is_never_retried_by_generation(session: AsyncSession) -> None:
    """Requirement 8: regenerating proposals (including composing a fresh
    proposal for an unrelated new message) must never touch, replay, or
    re-attempt an existing uncertain execution."""
    user = await _user_with_synthetic_account(session)
    service = ActionProposalService(session, user.id)

    source_a = _gmail_source(user.id, "gmail-noretry-old", thread_id="thread-old")
    signal_a = _request_signal(user.id, source_a, dedupe_suffix="noretry-old", priority=0.9)
    brief1 = await _brief(session, user, version=1)
    await service.generate_from_brief(
        brief=brief1, signals=[signal_a], sources=[source_a], timezone=TIMEZONE, reference=REFERENCE
    )
    proposal_a = _draft_proposal(await ActionProposalRepository(session, user.id).list())
    await _make_uncertain(session, user, proposal_a)
    executions = ActionExecutionRepository(session, user.id)
    original_execution = await executions.get_by_proposal(proposal_a.id)
    assert original_execution is not None
    original_execution_id = original_execution.id

    source_b = _gmail_source(user.id, "gmail-noretry-new", thread_id="thread-new")
    signal_b = _request_signal(user.id, source_b, dedupe_suffix="noretry-new", priority=0.5)
    brief2 = await _brief(session, user, version=2)
    await service.generate_from_brief(
        brief=brief2,
        signals=[signal_a, signal_b],
        sources=[source_a, source_b],
        timezone=TIMEZONE,
        reference=REFERENCE,
    )

    await session.refresh(proposal_a)
    assert proposal_a.status == ProposalStatus.executing
    execution_after = await executions.get_by_proposal(proposal_a.id)
    assert execution_after is not None
    assert execution_after.id == original_execution_id
    assert execution_after.outcome == ExecutionOutcome.uncertain
