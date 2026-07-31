"""Stage 11A Phase 2 (docs/delivery/stage-11a-phase-2-plan.md): repeatability
proof for both the "accepted-but-unconfirmed write" (uncertain) case and the
"refused before any provider call was attempted" case, across both
write-capable action types (Gmail draft, Calendar event) — at the required
repetition counts (10x uncertain, 5x refused-before-call) this contract
demands, extending `test_execution_durability.py`'s single-cycle,
`create_task`-only proof.

Real product code confirmed by reading `action_executors.py`
(`GoogleGmailDraftExecutor`/`GoogleCalendarEventExecutor`): a transient
failure touching the actual write call or its confirmation read is *always*
classified `uncertain`, never silently retried — there is no "safe to
automatically retry a write" path in this product by design (only reads
retry, via `retry_read`). The one genuinely distinct case is a failure
*before* any provider network call is attempted (token/context/authorisation
checks), which raises `FinalExecutionError` and is classified `failed` — a
disclosed refusal, not an ambiguous outcome, and never retried either. Both
are exercised here via a test-double `ExecutorRegistry` (mirroring
`SimulatedExecutorRegistry`'s shape), not real Google calls.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL
from tests.test_action_proposals import NOW, _approve, _proposal, _seed_google_sourced_proposals

from lifeflow_api.action_executors import ExecutorOutcome, FinalExecutionError
from lifeflow_api.action_proposal_service import ActionProposalService
from lifeflow_api.google_scopes import (
    CALENDAR_EVENTS_SCOPE,
    CALENDAR_READONLY_SCOPE,
    GMAIL_COMPOSE_SCOPE,
    GMAIL_READONLY_SCOPE,
)
from lifeflow_api.models import ActionType, ExecutionOutcome, ProposalStatus

pytestmark = pytest.mark.integration

ALL_SCOPES = [
    GMAIL_READONLY_SCOPE,
    GMAIL_COMPOSE_SCOPE,
    CALENDAR_READONLY_SCOPE,
    CALENDAR_EVENTS_SCOPE,
]
WRITE_ACTION_TYPES = (ActionType.create_gmail_draft, ActionType.create_calendar_event)


class _ScriptedGoogleRegistry:
    """A minimal `ExecutorRegistry`-shaped double standing in for the real
    Google write path — either the "uncertain" outcome a lost confirmation
    produces, or the `FinalExecutionError` a before-any-call refusal raises.
    Counts calls so a replay can assert the executor is never re-invoked."""

    def __init__(
        self, *, outcome: ExecutorOutcome | None = None, raises: BaseException | None = None
    ) -> None:
        self.calls = 0
        self._outcome = outcome
        self._raises = raises

    async def execute(
        self,
        action_type: ActionType,
        *,
        proposal_id: uuid.UUID,
        payload: object,
        approved_authorization: object,
    ) -> ExecutorOutcome:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        assert self._outcome is not None
        return self._outcome


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


async def _one_uncertain_cycle(session: AsyncSession, action_type: ActionType) -> None:
    user, _account, proposals = await _seed_google_sourced_proposals(
        session, granted_scopes=ALL_SCOPES
    )
    proposal = _proposal(proposals, action_type)
    registry = _ScriptedGoogleRegistry(
        outcome=ExecutorOutcome(
            status="uncertain",
            result={"message": "The provider did not confirm the write before the call ended."},
        )
    )
    service = ActionProposalService(
        session, user.id, google_executors=registry, now_factory=lambda: NOW
    )
    approved = await _approve(service, proposal, session=session, user=user)
    _, execution = await service.execute(approved.id)

    assert execution.outcome == ExecutionOutcome.uncertain
    assert registry.calls == 1

    # Restart-safety: a fresh ActionProposalService instance (standing in
    # for a brand-new API process) must never re-invoke the executor — the
    # durable ActionExecution row alone must short-circuit the replay.
    restarted_service = ActionProposalService(
        session, user.id, google_executors=registry, now_factory=lambda: NOW
    )
    _, replayed = await restarted_service.execute(approved.id)
    assert replayed.id == execution.id
    assert registry.calls == 1, "the write executor must never be invoked a second time"


async def _one_refused_before_call_cycle(session: AsyncSession, action_type: ActionType) -> None:
    user, _account, proposals = await _seed_google_sourced_proposals(
        session, granted_scopes=ALL_SCOPES
    )
    proposal = _proposal(proposals, action_type)
    registry = _ScriptedGoogleRegistry(raises=FinalExecutionError("approval_context_changed"))
    service = ActionProposalService(
        session, user.id, google_executors=registry, now_factory=lambda: NOW
    )
    approved = await _approve(service, proposal, session=session, user=user)
    proposal_after, execution = await service.execute(approved.id)

    assert execution.outcome == ExecutionOutcome.failed
    assert proposal_after.status == ProposalStatus.failed
    assert execution.result_json["status"] == "failed"
    assert "No external action was attempted" in execution.result_json["message"]
    assert registry.calls == 1

    restarted_service = ActionProposalService(
        session, user.id, google_executors=registry, now_factory=lambda: NOW
    )
    _, replayed = await restarted_service.execute(approved.id)
    assert replayed.id == execution.id
    assert registry.calls == 1, "a disclosed refusal must never be retried either"


@pytest.mark.parametrize("action_type", WRITE_ACTION_TYPES)
async def test_ten_uncertain_write_cycles_never_duplicate_or_replay(
    session: AsyncSession, action_type: ActionType
) -> None:
    for _ in range(10):
        await _one_uncertain_cycle(session, action_type)


@pytest.mark.parametrize("action_type", WRITE_ACTION_TYPES)
async def test_five_refused_before_call_cycles_are_disclosed_not_uncertain(
    session: AsyncSession, action_type: ActionType
) -> None:
    for _ in range(5):
        await _one_refused_before_call_cycle(session, action_type)
