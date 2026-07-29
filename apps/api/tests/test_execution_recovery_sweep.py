"""Stage 9 Delivery Phase 5 (§10): `recover_stale_pending_executions` — the
proactive, cross-user cron sweep for `ActionExecution` rows stuck `pending`
past `STALE_PENDING_AGE`, closing the gap that `execute()`'s own re-entry
guard only covers if someone happens to act on that specific proposal
again."""

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL
from tests.test_action_proposals import NOW, _approve, _proposal, _seed_proposals, _service

from lifeflow_api.action_proposal_service import (
    STALE_PENDING_AGE,
    recover_stale_pending_executions,
)
from lifeflow_api.models import ActionExecution, ActionType, ExecutionOutcome, ProposalStatus
from lifeflow_api.repositories import ActionExecutionRepository, AuditEventRepository

pytestmark = pytest.mark.integration


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


async def _stale_pending_execution(
    session: AsyncSession, task: ActionExecution, *, age_past_threshold: timedelta
) -> ActionExecution:
    execution = ActionExecution(
        proposal_id=task.id,
        idempotency_key=f"crash-simulated-{task.id}",
        approved_action_type=task.action_type,
        approved_proposal_version=task.version,
        executed_payload_json=task.payload_json,
        executed_payload_hash=task.payload_hash,
        approval_binding_hash=task.approved_binding_hash,
        execution_mode="simulation",
        outcome=ExecutionOutcome.pending,
        started_at=NOW - STALE_PENDING_AGE - age_past_threshold,
    )
    session.add(execution)
    task.status = ProposalStatus.executing
    await session.flush()
    return execution


async def test_stale_pending_execution_is_recovered_to_uncertain(session: AsyncSession) -> None:
    user, proposals = await _seed_proposals(session)
    task = _proposal(proposals, ActionType.create_task)
    service = _service(session, user)
    await _approve(service, task, session=session, user=user)
    execution = await _stale_pending_execution(
        session, task, age_past_threshold=timedelta(seconds=30)
    )

    recovered_count = await recover_stale_pending_executions(
        session, now=NOW + timedelta(seconds=1)
    )

    assert recovered_count == 1
    stored = await ActionExecutionRepository(session, user.id).get_by_proposal(task.id)
    assert stored is not None
    assert stored.outcome == ExecutionOutcome.uncertain

    events = await AuditEventRepository(session, user.id).list_for_entity(
        entity_type="action_proposal", entity_id=str(task.id)
    )
    uncertain_events = [e for e in events if e.event_type == "execution.uncertain"]
    assert uncertain_events
    assert uncertain_events[-1].safe_metadata_json["reason_code"] == "stale_pending_attempt"
    assert uncertain_events[-1].safe_metadata_json["execution_id"] == str(execution.id)


async def test_fresh_pending_execution_is_left_untouched(session: AsyncSession) -> None:
    """A `pending` row younger than `STALE_PENDING_AGE` is a genuinely
    in-flight attempt — the sweep must never touch it."""
    user, proposals = await _seed_proposals(session)
    task = _proposal(proposals, ActionType.create_task)
    service = _service(session, user)
    await _approve(service, task, session=session, user=user)
    execution = ActionExecution(
        proposal_id=task.id,
        idempotency_key="fresh-pending-key",
        approved_action_type=task.action_type,
        approved_proposal_version=task.version,
        executed_payload_json=task.payload_json,
        executed_payload_hash=task.payload_hash,
        approval_binding_hash=task.approved_binding_hash,
        execution_mode="simulation",
        outcome=ExecutionOutcome.pending,
        started_at=NOW,
    )
    session.add(execution)
    task.status = ProposalStatus.executing
    await session.flush()

    recovered_count = await recover_stale_pending_executions(
        session, now=NOW + timedelta(seconds=1)
    )

    assert recovered_count == 0
    stored = await ActionExecutionRepository(session, user.id).get_by_proposal(task.id)
    assert stored is not None
    assert stored.outcome == ExecutionOutcome.pending


async def test_succeeded_failed_and_already_uncertain_rows_are_never_touched(
    session: AsyncSession,
) -> None:
    user, proposals = await _seed_proposals(session)
    for outcome, action_type in (
        (ExecutionOutcome.succeeded, ActionType.create_task),
        (ExecutionOutcome.failed, ActionType.create_gmail_draft),
        (ExecutionOutcome.uncertain, ActionType.create_calendar_event),
    ):
        task = _proposal(proposals, action_type)
        service = _service(session, user)
        await _approve(service, task, session=session, user=user)
        execution = ActionExecution(
            proposal_id=task.id,
            idempotency_key=f"terminal-{outcome}",
            approved_action_type=task.action_type,
            approved_proposal_version=task.version,
            executed_payload_json=task.payload_json,
            executed_payload_hash=task.payload_hash,
            approval_binding_hash=task.approved_binding_hash,
            execution_mode="simulation",
            outcome=outcome,
            started_at=NOW - STALE_PENDING_AGE - timedelta(hours=1),
        )
        session.add(execution)
        await session.flush()

    recovered_count = await recover_stale_pending_executions(
        session, now=NOW + timedelta(seconds=1)
    )
    assert recovered_count == 0


async def test_sweep_recovers_across_multiple_users_in_one_pass(session: AsyncSession) -> None:
    """Cross-user by necessity, like `recover_stale_operations` and
    `recover_stale_running` — one cron tick must recover every user's stale
    rows, not just the first it finds."""
    user_a, proposals_a = await _seed_proposals(session)
    user_b, proposals_b = await _seed_proposals(session)
    task_a = _proposal(proposals_a, ActionType.create_task)
    task_b = _proposal(proposals_b, ActionType.create_gmail_draft)
    await _approve(_service(session, user_a), task_a, session=session, user=user_a)
    await _approve(_service(session, user_b), task_b, session=session, user=user_b)
    await _stale_pending_execution(session, task_a, age_past_threshold=timedelta(seconds=1))
    await _stale_pending_execution(session, task_b, age_past_threshold=timedelta(minutes=5))

    recovered_count = await recover_stale_pending_executions(
        session, now=NOW + timedelta(seconds=1)
    )

    assert recovered_count == 2
    stored_a = await ActionExecutionRepository(session, user_a.id).get_by_proposal(task_a.id)
    stored_b = await ActionExecutionRepository(session, user_b.id).get_by_proposal(task_b.id)
    assert stored_a is not None and stored_a.outcome == ExecutionOutcome.uncertain
    assert stored_b is not None and stored_b.outcome == ExecutionOutcome.uncertain


async def test_sweep_is_idempotent_across_repeated_ticks(session: AsyncSession) -> None:
    """A second cron tick over an already-recovered row must not re-audit
    it or count it again — the row is no longer `pending`."""
    user, proposals = await _seed_proposals(session)
    task = _proposal(proposals, ActionType.create_task)
    service = _service(session, user)
    await _approve(service, task, session=session, user=user)
    await _stale_pending_execution(session, task, age_past_threshold=timedelta(seconds=30))

    first = await recover_stale_pending_executions(session, now=NOW + timedelta(seconds=1))
    second = await recover_stale_pending_executions(session, now=NOW + timedelta(seconds=2))

    assert first == 1
    assert second == 0
    events = await AuditEventRepository(session, user.id).list_for_entity(
        entity_type="action_proposal", entity_id=str(task.id)
    )
    uncertain_events = [e for e in events if e.event_type == "execution.uncertain"]
    assert len(uncertain_events) == 1
