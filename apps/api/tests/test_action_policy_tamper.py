"""Policy-engine tamper defences (Stage 6 remediation).

Each test deliberately corrupts persisted approval state and proves the
deterministic policy engine refuses execution or approval with a stable
error code, a safe audit event, and no executor invocation.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL
from tests.test_action_proposals import (
    NOW,
    CountingExecutor,
    _approve,
    _proposal,
    _seed_proposals,
    _service,
)

from lifeflow_api.action_executors import SimulatedExecutorRegistry
from lifeflow_api.action_policy import ActionPolicyEngine, PolicyViolationError
from lifeflow_api.action_proposal_service import ProposalConflictError
from lifeflow_api.models import AccountStatus, ActionProposal, ActionType
from lifeflow_api.repositories import AuditEventRepository, ConnectedAccountRepository

pytestmark = pytest.mark.integration

SAFE_DENIAL_KEYS = {"action_type", "reason_code", "version"}


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


async def _last_denied_event(
    session: AsyncSession, user_id: uuid.UUID, proposal_id: uuid.UUID, event_type: str
):
    events = await AuditEventRepository(session, user_id).list_for_entity(
        entity_type="action_proposal", entity_id=str(proposal_id)
    )
    matching = [event for event in events if event.event_type == event_type]
    assert matching, f"expected a {event_type} audit event"
    return matching[-1]


def _corrupt_incomplete(proposal: ActionProposal) -> None:
    proposal.approved_payload_hash = None


def _corrupt_action_type(proposal: ActionProposal) -> None:
    proposal.approved_action_type = str(ActionType.create_gmail_draft)


def _corrupt_version(proposal: ActionProposal) -> None:
    proposal.approved_version = 99


def _corrupt_payload_hash(proposal: ActionProposal) -> None:
    proposal.approved_payload_hash = "f" * 64


def _corrupt_payload_json(proposal: ActionProposal) -> None:
    proposal.approved_payload_json = {
        **(proposal.approved_payload_json or {}),
        "title": "Tampered after approval",
    }


def _corrupt_binding(proposal: ActionProposal) -> None:
    proposal.approved_binding_hash = "f" * 64


def _corrupt_edit_after_approval(proposal: ActionProposal) -> None:
    proposal.user_edited_at = NOW + timedelta(seconds=1)


@pytest.mark.parametrize(
    ("corrupt", "expected_code"),
    [
        (_corrupt_incomplete, "approval_missing"),
        (_corrupt_action_type, "approval_mismatch"),
        (_corrupt_version, "approval_mismatch"),
        (_corrupt_payload_hash, "approval_mismatch"),
        (_corrupt_payload_json, "approval_mismatch"),
        (_corrupt_binding, "approval_mismatch"),
        (_corrupt_edit_after_approval, "approval_stale"),
    ],
    ids=[
        "incomplete-snapshot",
        "action-type-mismatch",
        "version-mismatch",
        "payload-hash-mismatch",
        "payload-json-drift",
        "binding-hash-invalid",
        "approved-before-edit",
    ],
)
async def test_tampered_approval_state_denies_execution(
    session: AsyncSession,
    corrupt: Callable[[ActionProposal], None],
    expected_code: str,
) -> None:
    user, proposals = await _seed_proposals(session)
    executor = CountingExecutor()
    service = _service(
        session, user, executors=SimulatedExecutorRegistry({ActionType.create_task: executor})
    )
    task = _proposal(proposals, ActionType.create_task)
    await _approve(service, task)

    corrupt(task)
    await session.flush()

    with pytest.raises(ProposalConflictError) as conflict:
        await service.execute(task.id)
    assert conflict.value.code == expected_code
    assert executor.calls == 0  # the executor is never reached

    denied = await _last_denied_event(session, user.id, task.id, "execution.denied")
    assert denied.safe_metadata_json["reason_code"] == expected_code
    assert set(denied.safe_metadata_json) <= SAFE_DENIAL_KEYS
    assert "Tampered" not in str(denied.safe_metadata_json)


async def _remove_scope(session: AsyncSession, user_id: uuid.UUID) -> None:
    account = await ConnectedAccountRepository(session, user_id).get_by_provider("synthetic")
    assert account is not None
    account.granted_scopes = []
    await session.flush()


async def _disconnect_account(session: AsyncSession, user_id: uuid.UUID) -> None:
    account = await ConnectedAccountRepository(session, user_id).get_by_provider("synthetic")
    assert account is not None
    account.status = AccountStatus.disconnected
    await session.flush()


@pytest.mark.parametrize(
    "degrade",
    [_remove_scope, _disconnect_account],
    ids=["scope-removed", "account-disconnected"],
)
async def test_missing_simulated_capability_denies_approval_and_execution(
    session: AsyncSession,
    degrade: Callable[[AsyncSession, uuid.UUID], Awaitable[None]],
) -> None:
    user, proposals = await _seed_proposals(session)
    service = _service(session, user)
    draft = _proposal(proposals, ActionType.create_gmail_draft)
    calendar = _proposal(proposals, ActionType.create_calendar_event)

    # Approve one medium-risk proposal while the capability is still active,
    # then degrade the account: execution must also be denied.
    await _approve(service, draft)
    await degrade(session, user.id)

    with pytest.raises(ProposalConflictError) as approval_conflict:
        await _approve(service, calendar)
    assert approval_conflict.value.code == "simulated_scope_missing"
    denied_approval = await _last_denied_event(session, user.id, calendar.id, "approval.denied")
    assert denied_approval.safe_metadata_json["reason_code"] == "simulated_scope_missing"

    with pytest.raises(ProposalConflictError) as execution_conflict:
        await service.execute(draft.id)
    assert execution_conflict.value.code == "simulated_scope_missing"
    denied_execution = await _last_denied_event(session, user.id, draft.id, "execution.denied")
    assert denied_execution.safe_metadata_json["reason_code"] == "simulated_scope_missing"
    assert set(denied_execution.safe_metadata_json) <= SAFE_DENIAL_KEYS


async def test_policy_engine_rejects_foreign_ownership_directly(
    session: AsyncSession,
) -> None:
    """Defence-in-depth: repositories already return not_found for other
    users; the policy engine independently refuses a foreign proposal."""
    user, proposals = await _seed_proposals(session)
    task = _proposal(proposals, ActionType.create_task)
    accounts = await ConnectedAccountRepository(session, user.id).list()

    with pytest.raises(PolicyViolationError) as violation:
        ActionPolicyEngine().validate_approval(
            task,
            user_id=uuid.uuid4(),  # a different user
            accounts=accounts,
            now=NOW,
            displayed_action_type=ActionType(task.action_type),
            displayed_payload_hash=task.payload_hash,
            displayed_version=task.version,
        )
    assert violation.value.code == "ownership_mismatch"
