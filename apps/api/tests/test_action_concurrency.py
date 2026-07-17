"""Real PostgreSQL concurrency behaviour for Stage 6 proposals.

Each racing task uses its own engine, connection, and transaction, so row
locks and the origin uniqueness constraint are exercised for real — nothing
is mocked.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL
from tests.helpers import REFERENCE, TIMEZONE, demo_source_items
from tests.test_action_proposals import NOW, CountingExecutor, _approve, _proposal, _service

from lifeflow_api.action_executors import SimulatedExecutorRegistry
from lifeflow_api.action_proposal_service import (
    ActionProposalService,
    ProposalConflictError,
    ProposalGenerationSummary,
)
from lifeflow_api.brief_composition import BriefService
from lifeflow_api.extraction import SignalExtractionService
from lifeflow_api.models import (
    AccountStatus,
    ActionProposal,
    ActionType,
    Brief,
    ConnectedAccount,
    ProposalStatus,
    User,
)
from lifeflow_api.repositories import (
    ActionProposalRepository,
    BriefRepository,
    SignalRepository,
    SourceItemRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


async def _seed_signals_and_brief(session: AsyncSession) -> tuple[User, uuid.UUID]:
    """User + account + sources + extracted signals + a brief row, committed,
    WITHOUT any proposals — the racing tasks generate those."""
    user = User(email=f"race-{uuid.uuid4()}@lifeflow.local", display_name="Race")
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
    session.add_all(await demo_source_items(user.id))
    await session.flush()
    await SignalExtractionService(session, user.id).extract(timezone=TIMEZONE, reference=REFERENCE)
    brief = Brief(
        user_id=user.id,
        briefing_date=datetime(2026, 7, 15, tzinfo=UTC),
        version=1,
        status="complete",
        summary="seed brief for concurrency tests",
        sections_json={"sections": [], "notices": []},
        source_window="test",
    )
    session.add(brief)
    await session.flush()
    brief_id = brief.id
    await session.commit()
    return user, brief_id


async def _seed_full(session: AsyncSession) -> tuple[User, list[ActionProposal]]:
    """User with generated proposals, committed so other connections see them."""
    user = User(email=f"race-full-{uuid.uuid4()}@lifeflow.local", display_name="Race Full")
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
    session.add_all(await demo_source_items(user.id))
    await session.flush()
    await BriefService(session, user.id).generate(timezone=TIMEZONE, reference=REFERENCE)
    proposals = await ActionProposalRepository(session, user.id).list()
    await session.commit()
    return user, proposals


async def test_concurrent_first_generation_creates_each_origin_exactly_once(
    session: AsyncSession,
) -> None:
    """M1: the losing insert handles the unique-constraint conflict and falls
    through to the change-aware path instead of surfacing a 500."""
    user, brief_id = await _seed_signals_and_brief(session)

    async def generate_once() -> ProposalGenerationSummary:
        engine = create_async_engine(TEST_DB_URL)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as racing:
                signals = await SignalRepository(racing, user.id).list_ranked(limit=500)
                sources = await SourceItemRepository(racing, user.id).list(limit=1000)
                brief = await BriefRepository(racing, user.id).get(brief_id)
                assert brief is not None
                summary = await ActionProposalService(
                    racing, user.id, now_factory=lambda: NOW
                ).generate_from_brief(
                    brief=brief,
                    signals=signals,
                    sources=sources,
                    timezone=TIMEZONE,
                    reference=REFERENCE,
                )
                await racing.commit()
                return summary
        finally:
            await engine.dispose()

    first, second = await asyncio.gather(generate_once(), generate_once())

    assert first.created + second.created == 3
    assert first.created + first.unchanged + first.updated == 3
    assert second.created + second.unchanged + second.updated == 3
    proposals = await ActionProposalRepository(session, user.id).list()
    assert len(proposals) == 3
    assert len({proposal.origin_fingerprint for proposal in proposals}) == 3


async def test_concurrent_execution_invokes_executor_once(session: AsyncSession) -> None:
    user, proposals = await _seed_full(session)
    task = _proposal(proposals, ActionType.create_task)
    await _approve(_service(session, user), task)
    await session.commit()
    executor = CountingExecutor()

    async def execute_once() -> tuple[str, str]:
        engine = create_async_engine(TEST_DB_URL)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as racing:
                service = ActionProposalService(
                    racing,
                    user.id,
                    executors=SimulatedExecutorRegistry({ActionType.create_task: executor}),
                    now_factory=lambda: NOW,
                )
                proposal, execution = await service.execute(task.id)
                await racing.commit()
                return str(execution.id), str(proposal.status)
        finally:
            await engine.dispose()

    (first_id, first_status), (second_id, second_status) = await asyncio.gather(
        execute_once(), execute_once()
    )

    assert executor.calls == 1  # exactly one real invocation; the other replays
    assert first_id == second_id
    assert first_status == second_status == ProposalStatus.executed


async def test_concurrent_approve_and_edit_stay_controlled_and_consistent(
    session: AsyncSession,
) -> None:
    user, proposals = await _seed_full(session)
    task = _proposal(proposals, ActionType.create_task)
    edited_payload = {**task.payload_json, "title": "Edited concurrently"}

    async def approve_task() -> object:
        engine = create_async_engine(TEST_DB_URL)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as racing:
                service = ActionProposalService(racing, user.id, now_factory=lambda: NOW)
                proposal = await service.approve(
                    task.id,
                    expected_version=task.version,
                    action_type=ActionType.create_task,
                    displayed_payload_hash=task.payload_hash,
                )
                await racing.commit()
                return proposal.status
        finally:
            await engine.dispose()

    async def edit_task() -> object:
        engine = create_async_engine(TEST_DB_URL)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as racing:
                service = ActionProposalService(racing, user.id, now_factory=lambda: NOW)
                proposal = await service.edit(
                    task.id,
                    expected_version=task.version,
                    action_type=ActionType.create_task,
                    payload=edited_payload,
                )
                await racing.commit()
                return proposal.status
        finally:
            await engine.dispose()

    outcomes = await asyncio.gather(approve_task(), edit_task(), return_exceptions=True)

    # Every outcome is either a success or a CONTROLLED conflict — never an
    # unhandled error surfacing as a 500.
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            assert isinstance(outcome, ProposalConflictError)
            assert outcome.code in {"stale_version", "invalid_transition", "stale_preview"}

    # Whatever the interleaving, the persisted proposal is internally
    # consistent: an approved row carries a snapshot matching its version;
    # an edited row has no approval and an incremented version.
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as reader:
            final = await ActionProposalRepository(reader, user.id).get(task.id)
            assert final is not None
            if final.status == ProposalStatus.approved:
                assert final.approved_version == final.version
                assert final.approved_payload_hash == final.payload_hash
            elif final.status == ProposalStatus.edited:
                assert final.version == task.version + 1
                assert final.approved_at is None
                assert final.approved_payload_json is None
            else:
                pytest.fail(f"unexpected final status: {final.status}")
    finally:
        await engine.dispose()
