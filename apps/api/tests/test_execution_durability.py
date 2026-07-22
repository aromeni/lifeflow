"""Stage 7: the durable pending/succeeded/failed/uncertain execution flow
(ADR 0003 D16) — provider-agnostic, so these tests exercise it through the
existing `SimulatedExecutorRegistry` seam rather than real Google calls.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL
from tests.test_action_proposals import NOW, _approve, _proposal, _seed_proposals, _service

from lifeflow_api.action_executors import ExecutorOutcome, SimulatedExecutorRegistry
from lifeflow_api.action_proposal_service import STALE_PENDING_AGE, effective_execution_status
from lifeflow_api.models import ActionExecution, ActionType, ExecutionOutcome, ProposalStatus
from lifeflow_api.repositories import ActionExecutionRepository, AuditEventRepository

pytestmark = pytest.mark.integration


class _UncertainExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, **_: object) -> ExecutorOutcome:
        self.calls += 1
        return ExecutorOutcome(
            status="uncertain", result={"message": "The call did not resolve before it ended."}
        )


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


def test_effective_execution_status_is_pending_while_fresh() -> None:
    execution = ActionExecution(
        proposal_id=uuid.uuid4(),
        idempotency_key="k1",
        approved_action_type=ActionType.create_task,
        approved_proposal_version=1,
        executed_payload_json={},
        executed_payload_hash="a" * 64,
        approval_binding_hash="b" * 64,
        execution_mode="simulation",
        outcome=ExecutionOutcome.pending,
        started_at=NOW,
    )
    assert effective_execution_status(execution, now=NOW + timedelta(seconds=1)) == "pending"


def test_effective_execution_status_is_uncertain_once_stale() -> None:
    execution = ActionExecution(
        proposal_id=uuid.uuid4(),
        idempotency_key="k2",
        approved_action_type=ActionType.create_task,
        approved_proposal_version=1,
        executed_payload_json={},
        executed_payload_hash="a" * 64,
        approval_binding_hash="b" * 64,
        execution_mode="simulation",
        outcome=ExecutionOutcome.pending,
        started_at=NOW,
    )
    stale_now = NOW + STALE_PENDING_AGE + timedelta(seconds=1)
    assert effective_execution_status(execution, now=stale_now) == "uncertain"


def test_effective_execution_status_passes_through_terminal_outcomes() -> None:
    for outcome in (
        ExecutionOutcome.succeeded,
        ExecutionOutcome.failed,
        ExecutionOutcome.uncertain,
    ):
        execution = ActionExecution(
            proposal_id=uuid.uuid4(),
            idempotency_key=f"k-{outcome}",
            approved_action_type=ActionType.create_task,
            approved_proposal_version=1,
            executed_payload_json={},
            executed_payload_hash="a" * 64,
            approval_binding_hash="b" * 64,
            execution_mode="simulation",
            outcome=outcome,
            started_at=NOW,
        )
        stale_now = NOW + STALE_PENDING_AGE + timedelta(seconds=1)
        assert effective_execution_status(execution, now=stale_now) == outcome


async def test_uncertain_outcome_leaves_proposal_executing_and_is_never_retried(
    session: AsyncSession,
) -> None:
    user, proposals = await _seed_proposals(session)
    task = _proposal(proposals, ActionType.create_task)
    executor = _UncertainExecutor()
    service = _service(
        session, user, executors=SimulatedExecutorRegistry({ActionType.create_task: executor})
    )
    await _approve(service, task, session=session, user=user)

    proposal, execution = await service.execute(task.id)
    assert execution.outcome == ExecutionOutcome.uncertain
    assert proposal.status == ProposalStatus.executing
    assert executor.calls == 1

    # Calling execute() again must replay, never call the executor again —
    # extends assumption A20 from "final failure" to "any non-confirmed
    # outcome" (ADR 0003 D16).
    proposal2, execution2 = await service.execute(task.id)
    assert execution2.id == execution.id
    assert execution2.outcome == ExecutionOutcome.uncertain
    assert proposal2.status == ProposalStatus.executing
    assert executor.calls == 1

    events = await AuditEventRepository(session, user.id).list_for_entity(
        entity_type="action_proposal", entity_id=str(task.id)
    )
    assert any(e.event_type == "execution.uncertain" for e in events)


async def test_stale_pending_attempt_transitions_to_uncertain_on_next_read(
    session: AsyncSession,
) -> None:
    """Simulates a crash between the durable pending commit and the outcome
    commit: a pending row is inserted directly (bypassing the executor
    call), backdated past STALE_PENDING_AGE, and the next execute() call
    must recover it to `uncertain` rather than leaving it ambiguous."""
    user, proposals = await _seed_proposals(session)
    task = _proposal(proposals, ActionType.create_task)
    service = _service(session, user)
    await _approve(service, task, session=session, user=user)

    stale_started_at = NOW - STALE_PENDING_AGE - timedelta(seconds=30)
    execution = ActionExecution(
        proposal_id=task.id,
        idempotency_key="crash-simulated-key",
        approved_action_type=task.action_type,
        approved_proposal_version=task.version,
        executed_payload_json=task.payload_json,
        executed_payload_hash=task.payload_hash,
        approval_binding_hash=task.approved_binding_hash,
        execution_mode="simulation",
        outcome=ExecutionOutcome.pending,
        started_at=stale_started_at,
    )
    session.add(execution)
    task.status = ProposalStatus.executing
    await session.flush()

    proposal, recovered = await service.execute(task.id)
    assert recovered.outcome == ExecutionOutcome.uncertain
    assert proposal.status == ProposalStatus.executing

    events = await AuditEventRepository(session, user.id).list_for_entity(
        entity_type="action_proposal", entity_id=str(task.id)
    )
    uncertain_events = [e for e in events if e.event_type == "execution.uncertain"]
    assert uncertain_events
    assert uncertain_events[-1].safe_metadata_json["reason_code"] == "stale_pending_attempt"


async def test_pending_attempt_is_durably_committed_before_the_executor_is_called(
    session: AsyncSession,
) -> None:
    """The core durability guarantee: a second, independent connection must
    already see the `pending` row while the executor call is still in
    flight — proving the commit happened before, not after, the call."""
    user, proposals = await _seed_proposals(session)
    task = _proposal(proposals, ActionType.create_task)
    service = _service(session, user)
    await _approve(service, task, session=session, user=user)
    await session.commit()

    seen_outcome: dict[str, str | None] = {"outcome": None}

    class _ObservingExecutor:
        async def execute(self, **_: object) -> ExecutorOutcome:
            engine = create_async_engine(TEST_DB_URL)
            try:
                maker = async_sessionmaker(engine, expire_on_commit=False)
                async with maker() as reader:
                    result = await reader.execute(
                        select(ActionExecution).where(ActionExecution.proposal_id == task.id)
                    )
                    row = result.scalar_one_or_none()
                    seen_outcome["outcome"] = row.outcome if row is not None else None
            finally:
                await engine.dispose()
            return ExecutorOutcome(status="succeeded", result={"status": "ok"})

    service_with_observer = _service(
        session,
        user,
        executors=SimulatedExecutorRegistry({ActionType.create_task: _ObservingExecutor()}),
    )
    await service_with_observer.execute(task.id)

    assert seen_outcome["outcome"] == ExecutionOutcome.pending


async def test_replay_never_calls_executor_twice_for_a_completed_execution(
    session: AsyncSession,
) -> None:
    user, proposals = await _seed_proposals(session)
    task = _proposal(proposals, ActionType.create_task)

    class _CountingExecutor:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, **_: object) -> ExecutorOutcome:
            self.calls += 1
            return ExecutorOutcome(status="succeeded", result={"status": "ok"})

    executor = _CountingExecutor()
    service = _service(
        session, user, executors=SimulatedExecutorRegistry({ActionType.create_task: executor})
    )
    await _approve(service, task, session=session, user=user)

    await service.execute(task.id)
    await service.execute(task.id)
    await service.execute(task.id)

    assert executor.calls == 1
    execution = await ActionExecutionRepository(session, user.id).get_by_proposal(task.id)
    assert execution is not None
    assert execution.outcome == ExecutionOutcome.succeeded
