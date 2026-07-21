"""Stage 6 proposal lifecycle, integrity, expiry, and simulated execution."""

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL
from tests.helpers import REFERENCE, TIMEZONE, demo_source_items, scheduling_email_source

from lifeflow_api.action_executors import (
    ExecutorOutcome,
    ExecutorRegistry,
    FinalExecutionError,
    SimulatedExecutorRegistry,
)
from lifeflow_api.action_payloads import (
    action_payload_hash,
    approval_binding_hash,
    canonical_payload,
)
from lifeflow_api.action_proposal_service import (
    ActionProposalService,
    PostCommitHook,
    ProposalConflictError,
)
from lifeflow_api.brief_composition import BriefService
from lifeflow_api.execution_context import execution_context_hash, resolve_execution_context
from lifeflow_api.models import (
    AccountStatus,
    ActionProposal,
    ActionType,
    ConnectedAccount,
    ProposalStatus,
    RiskLevel,
    SourceItem,
    User,
)
from lifeflow_api.repositories import (
    ActionProposalRepository,
    AuditEventRepository,
    ConnectedAccountRepository,
    SourceItemRepository,
)

pytestmark = pytest.mark.integration
NOW = REFERENCE + timedelta(hours=1)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


async def _seed_proposals(
    session: AsyncSession,
) -> tuple[User, list[ActionProposal]]:
    user = User(email=f"actions-{uuid.uuid4()}@lifeflow.local", display_name="Actions Demo")
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
    assert {ActionType(item.action_type) for item in proposals} == set(ActionType)
    return user, proposals


async def _seed_google_sourced_proposals(
    session: AsyncSession, *, granted_scopes: list[str]
) -> tuple[User, ConnectedAccount, list[ActionProposal]]:
    """Like `_seed_proposals`, but every `SourceItem`'s evidence is tagged
    to a real `google` `ConnectedAccount` instead of left unlinked — so
    `resolve_execution_context` resolves Google provenance, not synthetic
    (Stage 7 remediation blocker #1). Used to test the real-execution path
    without conflating it with demo/synthetic evidence."""
    user = User(
        email=f"google-actions-{uuid.uuid4()}@lifeflow.local", display_name="Google Actions"
    )
    session.add(user)
    await session.flush()
    account = ConnectedAccount(
        user_id=user.id,
        provider="google",
        encrypted_access_token=None,
        encrypted_refresh_token=None,
        granted_scopes=granted_scopes,
        expires_at=None,
        status=AccountStatus.active,
        last_sync_at=None,
    )
    session.add(account)
    await session.flush()
    session.add_all(await demo_source_items(user.id, account_id=account.id))
    session.add(scheduling_email_source(user.id, account_id=account.id))
    await session.flush()
    await BriefService(session, user.id).generate(timezone=TIMEZONE, reference=REFERENCE)
    proposals = await ActionProposalRepository(session, user.id).list()
    assert {ActionType(item.action_type) for item in proposals} == set(ActionType)
    return user, account, proposals


def _proposal(proposals: list[ActionProposal], action_type: ActionType) -> ActionProposal:
    return next(item for item in proposals if item.action_type == action_type)


def _service(
    session: AsyncSession,
    user: User,
    *,
    executors: SimulatedExecutorRegistry | None = None,
    google_executors: ExecutorRegistry | None = None,
    post_commit_hook: PostCommitHook | None = None,
) -> ActionProposalService:
    return ActionProposalService(
        session,
        user.id,
        executors=executors,
        google_executors=google_executors,
        now_factory=lambda: NOW,
        post_commit_hook=post_commit_hook,
    )


async def _displayed_execution_context_hash(
    session: AsyncSession, user: User, proposal: ActionProposal
) -> str:
    accounts = await ConnectedAccountRepository(session, user.id).list()
    evidence_sources = await SourceItemRepository(session, user.id).list_by_external_ids(
        list(proposal.source_refs)
    )
    context = resolve_execution_context(
        ActionType(proposal.action_type), accounts=accounts, evidence_sources=evidence_sources
    )
    return execution_context_hash(context)


async def _approve(
    service: ActionProposalService, proposal: ActionProposal, *, session: AsyncSession, user: User
) -> ActionProposal:
    context_hash = await _displayed_execution_context_hash(session, user, proposal)
    return await service.approve(
        proposal.id,
        expected_version=proposal.version,
        action_type=ActionType(proposal.action_type),
        displayed_payload_hash=proposal.payload_hash,
        displayed_execution_context_hash=context_hash,
    )


def _assert_conflict(exc: pytest.ExceptionInfo[ProposalConflictError], code: str) -> None:
    assert exc.value.code == code


async def test_generation_is_grounded_change_aware_and_idempotent(
    session: AsyncSession,
) -> None:
    user, first = await _seed_proposals(session)
    first_state = {
        item.origin_fingerprint: (
            item.id,
            item.version,
            item.payload_json,
            item.payload_hash,
            item.updated_at,
        )
        for item in first
    }
    assert len(first_state) == 3
    assert all(item.source_refs for item in first)
    assert all("em-004" not in item.source_refs for item in first)

    second_brief = await BriefService(session, user.id).generate(
        timezone=TIMEZONE, reference=REFERENCE
    )
    second = await ActionProposalRepository(session, user.id).list()

    assert second_brief.model_metadata["proposal_generation"] == {
        "created": 0,
        "updated": 0,
        "unchanged": 3,
        "preserved": 0,
        "skipped": 0,
    }
    assert {
        item.origin_fingerprint: (
            item.id,
            item.version,
            item.payload_json,
            item.payload_hash,
            item.updated_at,
        )
        for item in second
    } == first_state


@pytest.mark.parametrize(
    "protected_status",
    [
        ProposalStatus.edited,
        ProposalStatus.approved,
        ProposalStatus.rejected,
        ProposalStatus.expired,
        ProposalStatus.executed,
        ProposalStatus.failed,
    ],
)
async def test_regeneration_never_overwrites_user_or_terminal_state(
    session: AsyncSession, protected_status: ProposalStatus
) -> None:
    user, proposals = await _seed_proposals(session)
    proposal = _proposal(proposals, ActionType.create_task)
    marker = {
        "title": f"Protected {protected_status}",
        "notes": "This payload must survive regeneration.",
        "due_at": proposal.payload_json["due_at"],
    }
    proposal.payload_json = canonical_payload(ActionType.create_task, marker)
    proposal.payload_hash = action_payload_hash(ActionType.create_task, marker)
    proposal.status = protected_status
    if protected_status == ProposalStatus.edited:
        proposal.user_edited_at = NOW
    await session.flush()

    brief = await BriefService(session, user.id).generate(timezone=TIMEZONE, reference=REFERENCE)
    await session.refresh(proposal)

    assert proposal.status == protected_status
    assert proposal.payload_json["title"] == f"Protected {protected_status}"
    assert brief.model_metadata["proposal_generation"]["preserved"] >= 1


async def test_all_action_types_require_explicit_approval(session: AsyncSession) -> None:
    user, proposals = await _seed_proposals(session)
    service = _service(session, user)

    for proposal in proposals:
        with pytest.raises(ProposalConflictError) as exc:
            await service.execute(proposal.id)
        _assert_conflict(exc, "invalid_transition")
        events = await AuditEventRepository(session, user.id).list_for_entity(
            entity_type="action_proposal", entity_id=str(proposal.id)
        )
        assert events[-1].event_type == "execution.denied"


async def test_approval_binds_exact_displayed_type_payload_and_version(
    session: AsyncSession,
) -> None:
    user, proposals = await _seed_proposals(session)
    proposal = _proposal(proposals, ActionType.create_task)
    service = _service(session, user)

    with pytest.raises(ProposalConflictError) as stale_payload:
        await service.approve(
            proposal.id,
            expected_version=proposal.version,
            action_type=ActionType.create_task,
            displayed_payload_hash="0" * 64,
            displayed_execution_context_hash="0" * 64,
        )
    _assert_conflict(stale_payload, "stale_preview")

    approved = await _approve(service, proposal, session=session, user=user)
    assert approved.status == ProposalStatus.approved
    assert approved.approved_action_type == approved.action_type
    assert approved.approved_payload_json == approved.payload_json
    assert approved.approved_payload_hash == approved.payload_hash
    assert approved.approved_version == approved.version
    assert approved.approved_execution_context_hash is not None
    assert approved.approved_binding_hash == approval_binding_hash(
        ActionType(approved.action_type),
        approved.payload_json,
        approved.version,
        approved.approved_execution_context_hash,
    )


async def test_editing_approved_atomically_invalidates_and_versions_approval(
    session: AsyncSession,
) -> None:
    user, proposals = await _seed_proposals(session)
    proposal = _proposal(proposals, ActionType.create_task)
    service = _service(session, user)
    approved = await _approve(service, proposal, session=session, user=user)
    old_version = approved.version
    old_hash = approved.payload_hash
    edited_payload = {
        **approved.payload_json,
        "title": "Edited after exact approval",
    }

    edited = await service.edit(
        approved.id,
        expected_version=old_version,
        action_type=ActionType.create_task,
        payload=edited_payload,
    )

    assert edited.status == ProposalStatus.edited
    assert edited.version == old_version + 1
    assert edited.payload_hash != old_hash
    assert edited.approved_at is None
    assert edited.approved_payload_json is None
    events = await AuditEventRepository(session, user.id).list_for_entity(
        entity_type="action_proposal", entity_id=str(edited.id)
    )
    assert [event.event_type for event in events][-2:] == [
        "approval.invalidated",
        "proposal.edited",
    ]

    with pytest.raises(ProposalConflictError) as stale:
        await service.edit(
            edited.id,
            expected_version=old_version,
            action_type=ActionType.create_task,
            payload=edited_payload,
        )
    _assert_conflict(stale, "stale_version")


class CountingExecutor:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def execute(self, **_: Any) -> ExecutorOutcome:
        self.calls += 1
        if self.fail:
            raise FinalExecutionError("simulated_final_failure")
        return ExecutorOutcome(
            status="succeeded",
            result={
                "status": "simulated",
                "simulated_id": "counted-once",
                "message": "Exactly one simulated call.",
            },
        )


async def test_simulated_execution_uses_approved_snapshot_and_is_idempotent(
    session: AsyncSession,
) -> None:
    user, proposals = await _seed_proposals(session)
    proposal = _proposal(proposals, ActionType.create_task)
    executor = CountingExecutor()
    registry = SimulatedExecutorRegistry({ActionType.create_task: executor})
    service = _service(session, user, executors=registry)
    approved = await _approve(service, proposal, session=session, user=user)

    first_proposal, first_execution = await service.execute(approved.id)
    second_proposal, second_execution = await service.execute(approved.id)

    assert executor.calls == 1
    assert first_proposal.status == second_proposal.status == ProposalStatus.executed
    assert first_execution.id == second_execution.id
    assert first_execution.result_json == second_execution.result_json
    assert first_execution.executed_payload_json == approved.approved_payload_json
    assert first_execution.executed_payload_hash == approved.approved_payload_hash
    assert first_execution.approval_binding_hash == approved.approved_binding_hash
    assert first_execution.approved_proposal_version == approved.approved_version


async def test_final_failure_is_recorded_once_and_never_auto_retried(
    session: AsyncSession,
) -> None:
    user, proposals = await _seed_proposals(session)
    proposal = _proposal(proposals, ActionType.create_task)
    executor = CountingExecutor(fail=True)
    service = _service(
        session,
        user,
        executors=SimulatedExecutorRegistry({ActionType.create_task: executor}),
    )
    await _approve(service, proposal, session=session, user=user)

    first_proposal, first_execution = await service.execute(proposal.id)
    second_proposal, second_execution = await service.execute(proposal.id)

    assert executor.calls == 1
    assert first_proposal.status == second_proposal.status == ProposalStatus.failed
    assert first_execution.id == second_execution.id
    assert first_execution.error_code == "simulated_final_failure"


async def test_rejection_is_terminal(session: AsyncSession) -> None:
    user, proposals = await _seed_proposals(session)
    proposal = _proposal(proposals, ActionType.create_task)
    service = _service(session, user)
    rejected = await service.reject(
        proposal.id, expected_version=proposal.version, reason="Not useful"
    )
    assert rejected.status == ProposalStatus.rejected

    with pytest.raises(ProposalConflictError) as edit_conflict:
        await service.edit(
            rejected.id,
            expected_version=rejected.version,
            action_type=ActionType.create_task,
            payload=rejected.payload_json,
        )
    _assert_conflict(edit_conflict, "invalid_transition")
    with pytest.raises(ProposalConflictError) as approve_conflict:
        await _approve(service, rejected, session=session, user=user)
    _assert_conflict(approve_conflict, "invalid_transition")
    with pytest.raises(ProposalConflictError) as execute_conflict:
        await service.execute(rejected.id)
    _assert_conflict(execute_conflict, "invalid_transition")


async def test_expiry_is_checked_immediately_before_approval_and_execution(
    session: AsyncSession,
) -> None:
    user, proposals = await _seed_proposals(session)
    service = _service(session, user)
    approval_target = _proposal(proposals, ActionType.create_task)
    approval_target.expires_at = NOW
    await session.flush()

    with pytest.raises(ProposalConflictError) as approval_conflict:
        await _approve(service, approval_target, session=session, user=user)
    _assert_conflict(approval_conflict, "proposal_expired")
    assert approval_target.status == ProposalStatus.expired

    execution_target = _proposal(proposals, ActionType.create_gmail_draft)
    await _approve(service, execution_target, session=session, user=user)
    execution_target.expires_at = NOW
    await session.flush()
    with pytest.raises(ProposalConflictError) as execution_conflict:
        await service.execute(execution_target.id)
    _assert_conflict(execution_conflict, "proposal_expired")
    assert execution_target.status == ProposalStatus.expired


async def test_database_constraints_close_action_types_and_origins(
    session: AsyncSession,
) -> None:
    user = User(email=f"constraints-{uuid.uuid4()}@lifeflow.local", display_name="Constraints")
    session.add(user)
    await session.flush()
    base = {
        "user_id": user.id,
        "origin_brief_id": None,
        "origin_fingerprint": "a" * 64,
        "rationale": "Invalid action must not persist.",
        "source_refs": ["source-1"],
        "payload_json": {"title": "Task", "notes": "Notes", "due_at": None},
        "payload_hash": "b" * 64,
        "version": 1,
        "risk_level": RiskLevel.low,
        "confidence": 0.9,
        "status": ProposalStatus.proposed,
        "expires_at": NOW + timedelta(days=1),
    }
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(ActionProposal(action_type="send_email", **base))
            await session.flush()

    valid = ActionProposal(action_type=ActionType.create_task, **base)
    session.add(valid)
    await session.flush()
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(
                ActionProposal(
                    action_type=ActionType.create_task,
                    **{**base, "payload_hash": "c" * 64},
                )
            )
            await session.flush()


async def test_proposals_and_executions_are_owner_scoped(session: AsyncSession) -> None:
    owner, proposals = await _seed_proposals(session)
    other = User(email=f"other-{uuid.uuid4()}@lifeflow.local", display_name="Other")
    session.add(other)
    await session.flush()

    assert await ActionProposalRepository(session, other.id).get(proposals[0].id) is None
    with pytest.raises(ProposalConflictError) as conflict:
        await _service(session, other).execute(proposals[0].id)
    _assert_conflict(conflict, "not_found")
    assert owner.id != other.id


async def test_action_proposal_api_exposes_exact_preview_and_safe_transitions(
    dev_client: AsyncClient,
) -> None:
    assert (
        await dev_client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
    ).status_code == 200
    assert (await dev_client.post("/demo/start", headers=CSRF_HEADERS)).status_code == 200
    assert (await dev_client.post("/briefs/generate", headers=CSRF_HEADERS)).status_code == 200

    listed = await dev_client.get("/action-proposals")
    assert listed.status_code == 200
    proposals = listed.json()["proposals"]
    assert len(proposals) == 3
    assert all(item["evidence"] for item in proposals)
    assert all(item["simulation_only"] is True for item in proposals)
    assert all("em-004" not in item["source_refs"] for item in proposals)

    task = next(item for item in proposals if item["action_type"] == "create_task")
    stale = await dev_client.post(
        f"/action-proposals/{task['id']}/approve",
        headers=CSRF_HEADERS,
        json={
            "expected_version": task["version"],
            "action_type": task["action_type"],
            "displayed_payload_hash": "0" * 64,
            "displayed_execution_context_hash": task["execution_context_hash"],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_preview"

    approved = await dev_client.post(
        f"/action-proposals/{task['id']}/approve",
        headers=CSRF_HEADERS,
        json={
            "expected_version": task["version"],
            "action_type": task["action_type"],
            "displayed_payload_hash": task["payload_hash"],
            "displayed_execution_context_hash": task["execution_context_hash"],
        },
    )
    assert approved.status_code == 200
    approved_body = approved.json()
    assert approved_body["approval"]["payload"] == task["payload"]
    assert approved_body["approval"]["payload_hash"] == task["payload_hash"]
    assert approved_body["approval"]["proposal_version"] == task["version"]
    assert approved_body["approval"]["execution_context"]["mode"] == "simulation"

    first_execution = await dev_client.post(
        f"/action-proposals/{task['id']}/execute", headers=CSRF_HEADERS
    )
    replay = await dev_client.post(f"/action-proposals/{task['id']}/execute", headers=CSRF_HEADERS)
    assert first_execution.status_code == replay.status_code == 200
    assert first_execution.json()["execution"] == replay.json()["execution"]
    assert first_execution.json()["execution"]["executed_payload"] == task["payload"]

    calendar = next(item for item in proposals if item["action_type"] == "create_calendar_event")
    rejected = await dev_client.post(
        f"/action-proposals/{calendar['id']}/reject",
        headers=CSRF_HEADERS,
        json={"expected_version": calendar["version"], "reason": "Not needed"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    terminal = await dev_client.post(
        f"/action-proposals/{calendar['id']}/approve",
        headers=CSRF_HEADERS,
        json={
            "expected_version": calendar["version"],
            "action_type": calendar["action_type"],
            "displayed_payload_hash": calendar["payload_hash"],
            "displayed_execution_context_hash": calendar["execution_context_hash"],
        },
    )
    assert terminal.status_code == 409
    assert terminal.json()["error"]["code"] == "invalid_transition"


async def test_action_proposal_api_accepts_emitted_iso_payload_and_invalidates_approval(
    dev_client: AsyncClient,
) -> None:
    await dev_client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
    await dev_client.post("/demo/start", headers=CSRF_HEADERS)
    await dev_client.post("/briefs/generate", headers=CSRF_HEADERS)
    proposals = (await dev_client.get("/action-proposals")).json()["proposals"]
    task = next(item for item in proposals if item["action_type"] == "create_task")
    approved = await dev_client.post(
        f"/action-proposals/{task['id']}/approve",
        headers=CSRF_HEADERS,
        json={
            "expected_version": task["version"],
            "action_type": task["action_type"],
            "displayed_payload_hash": task["payload_hash"],
            "displayed_execution_context_hash": task["execution_context_hash"],
        },
    )
    assert approved.status_code == 200

    edited = await dev_client.patch(
        f"/action-proposals/{task['id']}",
        headers=CSRF_HEADERS,
        json={
            "expected_version": task["version"],
            "action_type": task["action_type"],
            "payload": {
                **task["payload"],
                "title": "Edited through the generated JSON contract",
            },
        },
    )
    assert edited.status_code == 200
    body = edited.json()
    assert body["status"] == "edited"
    assert body["version"] == task["version"] + 1
    assert body["approval"] is None
    assert "approval.invalidated" in {event["event_type"] for event in body["audit_events"]}


async def _seed_user_sources(session: AsyncSession) -> User:
    """User + synthetic account + demo sources, WITHOUT generating a brief."""
    user = User(email=f"resilience-{uuid.uuid4()}@lifeflow.local", display_name="Resilience")
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
    return user


async def _corrupt_source(
    session: AsyncSession, user: User, external_id: str, corruption: dict[str, Any]
) -> None:
    result = await session.execute(
        select(SourceItem).where(
            SourceItem.user_id == user.id, SourceItem.external_id == external_id
        )
    )
    item = result.scalar_one()
    metadata = dict(item.metadata_json)
    for key, value in corruption.items():
        if value is _REMOVE:
            metadata.pop(key, None)
        else:
            metadata[key] = value
    item.metadata_json = metadata
    await session.flush()


_REMOVE = object()


@pytest.mark.parametrize(
    "corruption",
    [
        {"ends_at": _REMOVE},
        {"ends_at": "not-a-timestamp"},
        {"ends_at": 12345},
        {"ends_at": "2026-07-16T15:00:00"},  # timezone-naive: never guess a zone
        {"attendees": ["not-an-email-address", "also@@invalid"]},
        {"attendees": ["valid@example.com", {"email": "sneaky@example.com"}]},
    ],
    ids=[
        "missing-ends_at",
        "garbage-ends_at",
        "non-string-ends_at",
        "naive-ends_at",
        "invalid-attendees",
        "mixed-attendee-elements",
    ],
)
async def test_malformed_calendar_metadata_degrades_gracefully(
    session: AsyncSession, corruption: dict[str, Any]
) -> None:
    """H1: bad source metadata skips that candidate; the brief still generates."""
    user = await _seed_user_sources(session)
    await _corrupt_source(session, user, "ev-007", corruption)

    brief = await BriefService(session, user.id).generate(timezone=TIMEZONE, reference=REFERENCE)

    proposals = await ActionProposalRepository(session, user.id).list()
    types = {ActionType(item.action_type) for item in proposals}
    assert ActionType.create_calendar_event not in types
    assert {ActionType.create_task, ActionType.create_gmail_draft} <= types
    assert brief.status == "partial"
    assert brief.model_metadata["proposal_generation"]["skipped"] == 1
    notice_codes = {notice["code"] for notice in brief.sections_json["notices"]}
    assert "proposal_candidates_skipped" in notice_codes

    events = await AuditEventRepository(session, user.id).list(limit=200)
    skip_events = [e for e in events if e.event_type == "proposal.candidates_skipped"]
    assert len(skip_events) == 1
    metadata = skip_events[0].safe_metadata_json
    assert metadata == {
        "skipped": 1,
        "action_types": ["create_calendar_event"],
        "reason_codes": ["invalid_source_data"],
    }
    # No source content — including the malformed values themselves — may
    # leak through the skip path.
    dumped = str(metadata)
    assert "Data audit" not in dumped and "kickoff" not in dumped
    assert "sneaky@example.com" not in dumped and "2026-07-16T15:00:00" not in dumped


@pytest.mark.parametrize(
    "attendees",
    [
        "alice@example.com, bob@example.com",
        {"email": "alice@example.com", "cc": "bob@example.com"},
        7,
        None,
    ],
    ids=["string", "object", "number", "null"],
)
async def test_unusable_attendee_metadata_suppresses_meeting_detection(
    session: AsyncSession, attendees: Any
) -> None:
    """Whole-value malformed attendee metadata (string/object/number/null)
    cannot establish an attendee count, so the deterministic meeting detector
    emits no signal from it — never a TypeError that aborts extraction — and
    never guesses or coerces the value. Because this happens one layer before
    proposal composition, there is no candidate to skip; the brief must still
    surface the degradation honestly (partial status, a generic notice, and a
    safe diagnostic-backed audit event) rather than silently reporting
    "complete"."""
    user = await _seed_user_sources(session)
    await _corrupt_source(session, user, "ev-007", {"attendees": attendees})

    brief = await BriefService(session, user.id).generate(timezone=TIMEZONE, reference=REFERENCE)

    proposals = await ActionProposalRepository(session, user.id).list()
    types = {ActionType(item.action_type) for item in proposals}
    assert ActionType.create_calendar_event not in types
    assert {ActionType.create_task, ActionType.create_gmail_draft} <= types
    assert brief.status == "partial"
    assert brief.model_metadata["proposal_generation"]["skipped"] == 0
    assert brief.model_metadata["extraction"]["diagnostic_counts"] == {
        "invalid_attendees_metadata": 1
    }
    notice_codes = {notice["code"] for notice in brief.sections_json["notices"]}
    assert "signal_data_quality" in notice_codes
    notice_messages = {notice["message"] for notice in brief.sections_json["notices"]}
    assert "Some calendar information could not be processed." in notice_messages

    events = await AuditEventRepository(session, user.id).list(limit=200)
    extraction_event = next(e for e in events if e.event_type == "extraction.completed")
    assert extraction_event.safe_metadata_json["diagnostic_counts"] == {
        "invalid_attendees_metadata": 1
    }
    brief_event = next(e for e in events if e.event_type == "brief.generated")
    assert brief_event.safe_metadata_json["detection_diagnostics"] == {
        "invalid_attendees_metadata": 1
    }

    # No raw malformed value, name, or address may leak through diagnostics,
    # notices, or audit metadata — fixed codes and counts only.
    dumped = (
        str(brief.model_metadata)
        + str(brief.sections_json)
        + str([e.safe_metadata_json for e in events])
    )
    assert "alice@example.com" not in dumped
    assert "bob@example.com" not in dumped
    assert "ev-007" not in dumped


@pytest.mark.parametrize(
    "ends_at",
    [None, "2026-07-16T15:00:00"],
    ids=["missing-ends_at", "naive-ends_at"],
)
async def test_brief_generation_survives_malformed_source_metadata_api(
    dev_client: AsyncClient, ends_at: str | None
) -> None:
    """H1 at the HTTP boundary: malformed metadata must never produce a 500."""
    login = await dev_client.post(
        "/auth/dev-login",
        json={"email": f"api-resilience-{uuid.uuid4()}@example.com", "display_name": "R"},
        headers=CSRF_HEADERS,
    )
    assert login.status_code == 200
    assert (await dev_client.post("/demo/start", headers=CSRF_HEADERS)).status_code == 200
    me = (await dev_client.get("/me")).json()

    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        result = await db.execute(
            select(SourceItem).where(
                SourceItem.user_id == uuid.UUID(me["id"]),
                SourceItem.external_id == "ev-007",
            )
        )
        item = result.scalar_one()
        metadata = dict(item.metadata_json)
        if ends_at is None:
            metadata.pop("ends_at", None)
        else:
            metadata["ends_at"] = ends_at
        item.metadata_json = metadata
        await db.commit()
    await engine.dispose()

    generated = await dev_client.post("/briefs/generate", headers=CSRF_HEADERS)
    assert generated.status_code == 200
    body = generated.json()
    assert body["status"] == "partial"
    assert "proposal_candidates_skipped" in {notice["code"] for notice in body["notices"]}
    proposals = (await dev_client.get("/action-proposals")).json()["proposals"]
    assert {item["action_type"] for item in proposals} == {"create_task", "create_gmail_draft"}


@pytest.mark.parametrize(
    "attendees",
    [
        "alice@example.com, bob@example.com",
        {"email": "alice@example.com", "cc": "bob@example.com"},
        7,
        None,
    ],
    ids=["string", "object", "number", "null"],
)
async def test_brief_generation_survives_whole_value_malformed_attendees_api(
    dev_client: AsyncClient, attendees: Any
) -> None:
    """Whole-value malformed attendees at the HTTP boundary: 200, `partial`
    status (not a misleading `complete`), a generic data-quality notice, and
    task/draft proposals still generated."""
    login = await dev_client.post(
        "/auth/dev-login",
        json={"email": f"api-resilience-{uuid.uuid4()}@example.com", "display_name": "R"},
        headers=CSRF_HEADERS,
    )
    assert login.status_code == 200
    assert (await dev_client.post("/demo/start", headers=CSRF_HEADERS)).status_code == 200
    me = (await dev_client.get("/me")).json()

    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        result = await db.execute(
            select(SourceItem).where(
                SourceItem.user_id == uuid.UUID(me["id"]),
                SourceItem.external_id == "ev-007",
            )
        )
        item = result.scalar_one()
        metadata = dict(item.metadata_json)
        metadata["attendees"] = attendees
        item.metadata_json = metadata
        await db.commit()
    await engine.dispose()

    generated = await dev_client.post("/briefs/generate", headers=CSRF_HEADERS)
    assert generated.status_code == 200
    body = generated.json()
    assert body["status"] == "partial"
    notice_codes = {notice["code"] for notice in body["notices"]}
    assert "signal_data_quality" in notice_codes
    proposals = (await dev_client.get("/action-proposals")).json()["proposals"]
    assert {item["action_type"] for item in proposals} == {"create_task", "create_gmail_draft"}
    dumped = str(body)
    assert "alice@example.com" not in dumped and "bob@example.com" not in dumped


async def test_regeneration_updates_pristine_proposal_when_signal_changes(
    session: AsyncSession,
) -> None:
    """M3: the change-aware update path — same origin, new version, new hash."""
    user, proposals = await _seed_proposals(session)
    task = _proposal(proposals, ActionType.create_task)
    original = (task.id, task.origin_fingerprint, task.version, task.payload_hash)

    # Materially change the underlying source; the signal keeps its dedupe
    # key (same evidence) so the proposal origin is stable.
    result = await session.execute(
        select(SourceItem).where(SourceItem.user_id == user.id, SourceItem.external_id == "em-015")
    )
    source = result.scalar_one()
    source.title = f"{source.title} — revised scope"
    await session.flush()

    brief = await BriefService(session, user.id).generate(timezone=TIMEZONE, reference=REFERENCE)
    await session.refresh(task)

    assert (task.id, task.origin_fingerprint) == original[:2]  # lineage retained
    assert task.version == original[2] + 1
    assert task.payload_hash != original[3]
    assert "revised scope" in task.payload_json["title"]
    assert task.status == ProposalStatus.proposed  # system update, not a user edit
    assert task.user_edited_at is None
    assert brief.model_metadata["proposal_generation"]["updated"] == 1

    events = await AuditEventRepository(session, user.id).list_for_entity(
        entity_type="action_proposal", entity_id=str(task.id)
    )
    assert "proposal.updated" in {event.event_type for event in events}


FORBIDDEN_AUDIT_KEYS = {
    "to",
    "subject",
    "body",
    "attendees",
    "title",
    "notes",
    "description",
    "location",
    "recipients",
    "payload",
    "payload_json",
}


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(str(key))
            keys |= _walk_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            keys |= _walk_keys(nested)
    return keys


async def test_audit_metadata_never_contains_payload_content(session: AsyncSession) -> None:
    """Privacy regression: a full lifecycle leaves no payload fields in audit."""
    import json as _json

    user, proposals = await _seed_proposals(session)
    service = _service(session, user)
    task = _proposal(proposals, ActionType.create_task)
    draft = _proposal(proposals, ActionType.create_gmail_draft)
    calendar = _proposal(proposals, ActionType.create_calendar_event)

    sensitive_values = [
        draft.payload_json["to"][0],
        draft.payload_json["subject"],
        draft.payload_json["body"],
        task.payload_json["title"],
        calendar.payload_json["attendees"][0],
    ]

    await _approve(service, draft, session=session, user=user)
    await service.execute(draft.id)
    await service.execute(draft.id)  # replay
    await _approve(service, task, session=session, user=user)
    edited = await service.edit(
        task.id,
        expected_version=task.version,
        action_type=ActionType.create_task,
        payload={**task.payload_json, "title": "Privacy check edited title"},
    )
    await _approve(service, edited, session=session, user=user)
    rejection_reason = "Contains details about the Fenwick account."
    await service.reject(calendar.id, expected_version=calendar.version, reason=rejection_reason)
    sensitive_values.append("Privacy check edited title")
    sensitive_values.append(rejection_reason)

    events = await AuditEventRepository(session, user.id).list(limit=500)
    assert events
    all_metadata = [event.safe_metadata_json for event in events]
    seen_keys = set().union(*(_walk_keys(metadata) for metadata in all_metadata))
    assert not (seen_keys & FORBIDDEN_AUDIT_KEYS), seen_keys & FORBIDDEN_AUDIT_KEYS
    dumped = _json.dumps(all_metadata, default=str)
    for value in sensitive_values:
        assert value not in dumped, f"sensitive value leaked into audit metadata: {value[:24]}…"
