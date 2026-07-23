"""Stage 9 Delivery Phase 2: the durable deletion engine (ADR 0005).

Exercises the planner semantics, operation lifecycle, idempotency/crash
recovery, retention, and account anonymisation directly against a real
PostgreSQL session with a controllable clock — no Redis and no running worker
(the worker glue is a thin wrapper over these functions, covered separately by
the queue integration test).
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL

from lifeflow_api.account_deletion import run_account_deletion_step
from lifeflow_api.deletion import (
    cancel_operation,
    claim_operation,
    confirm_operation,
    create_account_deletion_preview,
    create_imported_data_preview,
    recover_stale_operations,
    run_operation,
)
from lifeflow_api.deletion_ops import (
    CONFIRM_ACCOUNT,
    CONFIRM_IMPORTED_DATA,
    ERROR_WORKER_STALE_TIMEOUT,
    InvalidConfirmationError,
    InvalidDeletionStateError,
    PreviewChangedError,
    PreviewExpiredError,
    StaleDeletionVersionError,
    scope_key_for,
)
from lifeflow_api.models import (
    ActionExecution,
    ActionProposal,
    AuditEvent,
    ConnectedAccount,
    DataDeletionOperation,
    DeletionOperationState,
    DeletionOperationType,
    ExecutionOutcome,
    MemoryEvidence,
    MemoryItem,
    Preference,
    ProposalStatus,
    Provenance,
    Signal,
    SourceItem,
    User,
    UserAccountState,
)
from lifeflow_api.retention import (
    RetentionHorizons,
    run_retention_step,
    scan_and_create_retention_operations,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
HORIZONS = RetentionHorizons(
    source_items_days=30,
    brief_versions_days=90,
    unapproved_proposals_days=90,
    scheduled_runs_days=90,
    memory_evidence_days=90,
)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


# --- builders ---------------------------------------------------------------


async def _user(session: AsyncSession, *, email: str | None = None) -> User:
    user = User(
        email=email or f"del-{uuid.uuid4()}@example.com",
        display_name="Deletion Tester",
        google_subject=f"sub-{uuid.uuid4()}",
    )
    session.add(user)
    await session.flush()
    return user


async def _account(
    session: AsyncSession, user_id: uuid.UUID, *, provider: str = "google"
) -> ConnectedAccount:
    account = ConnectedAccount(user_id=user_id, provider=provider, granted_scopes=[])
    session.add(account)
    await session.flush()
    return account


async def _source(
    session: AsyncSession,
    user_id: uuid.UUID,
    account_id: uuid.UUID | None,
    external_id: str,
    *,
    created_at: datetime = NOW,
) -> SourceItem:
    item = SourceItem(
        user_id=user_id,
        source_type="email",
        external_id=external_id,
        source_account_id=account_id,
        title="subject that must never leak",
        sender_or_organiser="someone@example.com",
        occurred_at=NOW,
        content_fingerprint=f"fp-{external_id}",
        created_at=created_at,
    )
    session.add(item)
    await session.flush()
    return item


async def _signal(
    session: AsyncSession, user_id: uuid.UUID, refs: list[str], *, dedupe: str
) -> Signal:
    sig = Signal(
        user_id=user_id,
        signal_type="request",
        title="signal title",
        summary="signal summary",
        evidence_refs=refs,
        confidence=0.9,
        urgency=0.5,
        importance=0.5,
        extraction_version="v1",
        dedupe_key=dedupe,
    )
    session.add(sig)
    await session.flush()
    return sig


async def _proposal(
    session: AsyncSession,
    user_id: uuid.UUID,
    refs: list[str],
    *,
    status: str = ProposalStatus.proposed,
    approved: bool = False,
    fingerprint: str,
) -> ActionProposal:
    proposal = ActionProposal(
        user_id=user_id,
        origin_fingerprint=fingerprint,
        action_type="create_gmail_draft",
        rationale="rationale that must never leak",
        source_refs=refs,
        payload_json={"subject": "secret subject", "body": "secret body"},
        payload_hash="hash",
        risk_level="medium",
        confidence=0.9,
        status=status,
        expires_at=NOW + timedelta(days=7),
        approved_at=NOW if approved else None,
        approved_payload_json={"body": "secret approved body"} if approved else None,
    )
    session.add(proposal)
    await session.flush()
    return proposal


async def _execution(
    session: AsyncSession, proposal_id: uuid.UUID, outcome: str
) -> ActionExecution:
    execution = ActionExecution(
        proposal_id=proposal_id,
        idempotency_key=f"idem-{uuid.uuid4()}",
        approved_action_type="create_gmail_draft",
        approved_proposal_version=1,
        executed_payload_json={"body": "secret executed body"},
        executed_payload_hash="hash",
        approval_binding_hash="bind",
        execution_mode="simulation",
        outcome=outcome,
        result_json={"draft_id": "secret-draft-id"},
    )
    session.add(execution)
    await session.flush()
    return execution


async def _count(session: AsyncSession, model: type, user_id: uuid.UUID) -> int:
    return int(
        (
            await session.execute(
                select(func.count()).select_from(model).where(model.user_id == user_id)
            )
        ).scalar_one()
    )


async def _seed_imported_dataset(session: AsyncSession) -> dict[str, object]:
    """A user with two accounts (A deleted, B kept) and a full reference graph."""
    user = await _user(session)
    account_a = await _account(session, user.id, provider="google")
    account_b = await _account(session, user.id, provider="secondary")
    await _source(session, user.id, account_a.id, "a-em-1")
    await _source(session, user.id, account_a.id, "a-em-2")
    await _source(session, user.id, account_b.id, "b-em-1")

    s1 = await _signal(session, user.id, ["a-em-1"], dedupe="d1")  # fully in A -> delete
    s2 = await _signal(session, user.id, ["a-em-2", "b-em-1"], dedupe="d2")  # mixed -> keep+prune
    s3 = await _signal(session, user.id, ["b-em-1"], dedupe="d3")  # unaffected

    p1 = await _proposal(session, user.id, ["a-em-1"], fingerprint="f1")  # unapproved -> delete
    p2 = await _proposal(
        session,
        user.id,
        ["a-em-1"],
        status=ProposalStatus.executed,
        approved=True,
        fingerprint="f2",
    )
    await _execution(session, p2.id, ExecutionOutcome.succeeded)  # terminal -> minimise
    p3 = await _proposal(
        session,
        user.id,
        ["a-em-2"],
        status=ProposalStatus.executing,
        approved=True,
        fingerprint="f3",
    )
    await _execution(session, p3.id, ExecutionOutcome.pending)  # pending -> preserve
    p4 = await _proposal(session, user.id, ["b-em-1"], fingerprint="f4")  # unaffected

    # Confirmed explicit preference must never be deleted.
    session.add(
        Preference(
            user_id=user.id,
            key="preferred_email_signoff",
            value_json={"value": "Kind regards"},
            provenance=Provenance.explicit,
        )
    )
    # Inferred memory whose evidence points at p1 (which will be deleted).
    memory = MemoryItem(
        user_id=user.id,
        memory_key="preferred_email_signoff",
        value_json={"value": "Kind regards"},
        confidence=0.8,
    )
    session.add(memory)
    await session.flush()
    session.add(
        MemoryEvidence(
            memory_item_id=memory.id,
            user_id=user.id,
            evidence_type="approved_edited_draft",
            source_proposal_id=p1.id,
            observed_at=NOW,
            derived_value="Kind regards",
            reason_code="approved_edited_draft",
        )
    )
    await session.flush()
    return {
        "user": user,
        "account_a": account_a,
        "account_b": account_b,
        "s1": s1.id,
        "s2": s2.id,
        "s3": s3.id,
        "p1": p1.id,
        "p2": p2.id,
        "p3": p3.id,
        "p4": p4.id,
    }


async def _run_to_completion(
    session: AsyncSession, operation_id: uuid.UUID
) -> DataDeletionOperation:
    await run_operation(
        session,
        operation_id,
        now=NOW,
        horizons=HORIZONS,
        batch_size=1,  # tiny batches to exercise the loop/cursor
        max_attempts=3,
    )
    op = await session.get(DataDeletionOperation, operation_id, populate_existing=True)
    assert op is not None
    return op


# --- preview accuracy (§6, tests 1/5/6/7) -----------------------------------


async def test_imported_preview_counts_match_database(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    # 2 source items in account A.
    assert op.preview_counts_json["source_items"] == 2
    # s1 fully unsupported -> deleted; s2 mixed -> recomputed (preserved).
    assert op.preview_counts_json.get("signals") == 1
    # p1 unapproved-unsupported -> deleted.
    assert op.preview_counts_json.get("action_proposals") == 1
    # p2 minimised history; p3 preserved pending.
    assert op.preserved_counts_json.get("minimised_proposal_history") == 1
    assert op.preserved_counts_json.get("preserved_pending_uncertain_executions") == 1


async def test_preview_is_owner_scoped_and_no_content(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    blob = str(op.preview_counts_json) + str(op.preserved_counts_json) + str(op.scope_json)
    for leak in ("secret subject", "secret body", "Kind regards", "a-em-1"):
        assert leak not in blob


async def test_preview_snapshot_excludes_later_data(session: AsyncSession) -> None:
    """New provider data imported after the snapshot survives (§7, test 42)."""
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    # A later import for account A, created after the snapshot cutoff.
    await _source(session, user.id, account_a.id, "a-em-late", created_at=NOW + timedelta(hours=1))
    await session.commit()
    confirmed = await confirm_operation(
        session,
        user,
        op.id,
        expected_version=op.version,
        phrase=CONFIRM_IMPORTED_DATA,
        now=NOW,
        preview_ttl_minutes=30,
    )
    await session.commit()
    await _run_to_completion(session, confirmed.id)
    survivor = (
        await session.execute(select(SourceItem).where(SourceItem.external_id == "a-em-late"))
    ).scalar_one_or_none()
    assert survivor is not None  # created after the snapshot -> not swept


# --- preview-plan binding (focused remediation §1) --------------------------


async def _preview_account_a(session: AsyncSession, data: dict[str, object]):
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    return user, await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )


async def _confirm(session, user, op, phrase=CONFIRM_IMPORTED_DATA, version=None):
    return await confirm_operation(
        session,
        user,
        op.id,
        expected_version=op.version if version is None else version,
        phrase=phrase,
        now=NOW,
        preview_ttl_minutes=30,
    )


async def test_unchanged_plan_confirms_successfully(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user, op = await _preview_account_a(session, data)
    confirmed = await _confirm(session, user, op)
    assert confirmed.state == DeletionOperationState.pending


async def test_fingerprint_is_content_free(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    _user, op = await _preview_account_a(session, data)
    assert op.plan_fingerprint is not None and len(op.plan_fingerprint) == 64
    # A hex digest — never any content, provider external id, or record payload.
    for leak in ("a-em-1", "a-em-2", "secret subject", "secret body", "Kind regards"):
        assert leak not in op.plan_fingerprint


async def test_proposal_state_change_invalidates_preview(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user, op = await _preview_account_a(session, data)
    original_version = op.version
    # An affected unapproved proposal (p1) becomes approved after preview.
    p1 = await session.get(ActionProposal, data["p1"])
    assert p1 is not None
    p1.status = ProposalStatus.approved
    p1.approved_at = NOW
    await session.flush()
    with pytest.raises(PreviewChangedError):
        await _confirm(session, user, op)
    refreshed = await session.get(DataDeletionOperation, op.id, populate_existing=True)
    assert refreshed is not None
    assert refreshed.state == DeletionOperationState.previewed  # not enqueued
    assert refreshed.version == original_version + 1  # refreshed


async def test_new_pending_execution_after_preview_invalidates(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user, op = await _preview_account_a(session, data)
    # A pending execution appears on an affected proposal (p1) after preview.
    await _execution(session, data["p1"], ExecutionOutcome.pending)  # type: ignore[arg-type]
    await session.flush()
    with pytest.raises(PreviewChangedError):
        await _confirm(session, user, op)


async def test_changed_derived_dependency_invalidates(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user, op = await _preview_account_a(session, data)
    # Removing account B's surviving source flips mixed signal s2 from
    # recompute to fully-unsupported (delete) — a disposition change.
    await session.execute(
        delete(SourceItem).where(SourceItem.user_id == user.id, SourceItem.external_id == "b-em-1")
    )
    await session.flush()
    with pytest.raises(PreviewChangedError):
        await _confirm(session, user, op)


async def test_later_out_of_snapshot_source_does_not_invalidate(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user, op = await _preview_account_a(session, data)
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    # A brand-new source for account A, imported after the snapshot, alters no
    # listed derived disposition — so the reviewed plan is unchanged.
    await _source(session, user.id, account_a.id, "a-em-late", created_at=NOW + timedelta(hours=1))
    await session.flush()
    confirmed = await _confirm(session, user, op)
    assert confirmed.state == DeletionOperationState.pending


async def test_confirm_after_refresh_is_idempotent(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user, op = await _preview_account_a(session, data)
    p1 = await session.get(ActionProposal, data["p1"])
    assert p1 is not None
    p1.approved_at = NOW
    await session.flush()
    with pytest.raises(PreviewChangedError):
        await _confirm(session, user, op)
    refreshed = await session.get(DataDeletionOperation, op.id, populate_existing=True)
    assert refreshed is not None
    # Confirming with the STALE version now fails (racers can't confirm an old
    # plan version); confirming with the refreshed version succeeds.
    with pytest.raises(StaleDeletionVersionError):
        await _confirm(session, user, refreshed, version=refreshed.version - 1)
    c1 = await _confirm(session, user, refreshed)
    assert c1.state == DeletionOperationState.pending
    c2 = await _confirm(session, user, refreshed)  # idempotent
    assert c2.id == c1.id and c2.state == DeletionOperationState.pending


# --- confirmation and idempotency (§5, tests 8/9/10/11/12) ------------------


async def test_wrong_phrase_rejected(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    with pytest.raises(InvalidConfirmationError):
        await confirm_operation(
            session,
            user,
            op.id,
            expected_version=op.version,
            phrase="delete imported data",
            now=NOW,
            preview_ttl_minutes=30,
        )


async def test_stale_version_rejected(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    with pytest.raises(StaleDeletionVersionError):
        await confirm_operation(
            session,
            user,
            op.id,
            expected_version=op.version + 5,
            phrase=CONFIRM_IMPORTED_DATA,
            now=NOW,
            preview_ttl_minutes=30,
        )


async def test_expired_preview_rejected(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    with pytest.raises(PreviewExpiredError):
        await confirm_operation(
            session,
            user,
            op.id,
            expected_version=op.version,
            phrase=CONFIRM_IMPORTED_DATA,
            now=NOW + timedelta(minutes=31),
            preview_ttl_minutes=30,
        )


async def test_repeated_preview_reuses_active_operation(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op1 = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    op2 = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    assert op1.id == op2.id


async def test_repeated_confirmation_is_idempotent(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    c1 = await confirm_operation(
        session,
        user,
        op.id,
        expected_version=op.version,
        phrase=CONFIRM_IMPORTED_DATA,
        now=NOW,
        preview_ttl_minutes=30,
    )
    c2 = await confirm_operation(
        session,
        user,
        op.id,
        expected_version=999,
        phrase="anything",
        now=NOW,
        preview_ttl_minutes=30,
    )
    assert c1.id == c2.id
    assert c2.state == DeletionOperationState.pending


# --- deletion semantics (§8, tests 21-33) -----------------------------------


async def test_imported_deletion_semantics(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    confirmed = await confirm_operation(
        session,
        user,
        op.id,
        expected_version=op.version,
        phrase=CONFIRM_IMPORTED_DATA,
        now=NOW,
        preview_ttl_minutes=30,
    )
    await session.commit()
    final = await _run_to_completion(session, confirmed.id)
    assert final.state == DeletionOperationState.succeeded

    # Account A source items gone; account B's remain (test 21/22).
    remaining_sources = {
        r[0]
        for r in (
            await session.execute(
                select(SourceItem.external_id).where(SourceItem.user_id == user.id)
            )
        ).all()
    }
    assert remaining_sources == {"b-em-1"}

    # s1 deleted, s2 retained with a-em-2 pruned, s3 untouched (test 24/25).
    s1 = await session.get(Signal, data["s1"])
    assert s1 is None
    s2 = await session.get(Signal, data["s2"], populate_existing=True)
    assert s2 is not None and s2.evidence_refs == ["b-em-1"]
    s3 = await session.get(Signal, data["s3"], populate_existing=True)
    assert s3 is not None

    # p1 deleted; p2 minimised (content stripped) but present; p3 preserved;
    # p4 untouched (tests 26/27/28/30).
    assert await session.get(ActionProposal, data["p1"]) is None
    p2 = await session.get(ActionProposal, data["p2"], populate_existing=True)
    assert p2 is not None and p2.payload_json == {} and p2.approved_payload_json is None
    p3 = await session.get(ActionProposal, data["p3"], populate_existing=True)
    assert p3 is not None
    exec3 = (
        await session.execute(select(ActionExecution).where(ActionExecution.proposal_id == p3.id))
    ).scalar_one()
    assert exec3.outcome == ExecutionOutcome.pending  # never deleted (test 28)
    assert exec3.executed_payload_json == {}  # minimised (test 30)
    p4 = await session.get(ActionProposal, data["p4"], populate_existing=True)
    assert p4 is not None and p4.payload_json != {}

    # Confirmed explicit preference remains (test 33).
    assert await _count(session, Preference, user.id) == 1

    # Memory evidence's reference to the deleted p1 was nulled (test 31).
    ev = (
        await session.execute(select(MemoryEvidence).where(MemoryEvidence.user_id == user.id))
    ).scalar_one()
    assert ev.source_proposal_id is None
    assert ev.derived_value == "Kind regards"  # safe token retained


async def test_deletion_never_calls_provider(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No Gmail/Calendar client is ever constructed or called for deletion
    (test 23/69): the engine imports no provider client at all."""
    import lifeflow_api.deletion as deletion_module

    source = deletion_module.__dict__
    assert "GmailDraftClient" not in source
    assert "CalendarEventClient" not in source


# --- idempotency and recovery (§10, tests 37/38/40/41) ----------------------


async def test_completed_operation_rerun_changes_nothing(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    confirmed = await confirm_operation(
        session,
        user,
        op.id,
        expected_version=op.version,
        phrase=CONFIRM_IMPORTED_DATA,
        now=NOW,
        preview_ttl_minutes=30,
    )
    await session.commit()
    final = await _run_to_completion(session, confirmed.id)
    sources_before = await _count(session, SourceItem, user.id)
    # Re-running a succeeded operation must be a no-op (claim only matches pending).
    await run_operation(session, final.id, now=NOW, horizons=HORIZONS, batch_size=1, max_attempts=3)
    assert await _count(session, SourceItem, user.id) == sources_before


async def test_stale_running_operation_recovered(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    confirmed = await confirm_operation(
        session,
        user,
        op.id,
        expected_version=op.version,
        phrase=CONFIRM_IMPORTED_DATA,
        now=NOW,
        preview_ttl_minutes=30,
    )
    # Simulate a crashed worker: running with an old heartbeat.
    confirmed.state = DeletionOperationState.running
    confirmed.heartbeat_at = NOW - timedelta(minutes=30)
    confirmed.attempt_count = 1
    await session.commit()
    result = await recover_stale_operations(
        session, None, now=NOW, heartbeat_timeout=timedelta(minutes=10), max_attempts=3
    )
    assert result.requeued == 1
    reloaded = await session.get(DataDeletionOperation, confirmed.id, populate_existing=True)
    assert reloaded is not None and reloaded.state == DeletionOperationState.pending


async def test_stale_running_exhausted_attempts_fails_safe(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    op.state = DeletionOperationState.running
    op.heartbeat_at = NOW - timedelta(minutes=30)
    op.attempt_count = 3
    await session.commit()
    result = await recover_stale_operations(
        session, None, now=NOW, heartbeat_timeout=timedelta(minutes=10), max_attempts=3
    )
    assert result.failed == 1
    reloaded = await session.get(DataDeletionOperation, op.id, populate_existing=True)
    assert reloaded is not None
    assert reloaded.state == DeletionOperationState.partially_failed
    assert reloaded.safe_error_code == ERROR_WORKER_STALE_TIMEOUT


# --- cancellation (§4, tests 15/16) -----------------------------------------


async def test_pending_operation_can_be_cancelled(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    confirmed = await confirm_operation(
        session,
        user,
        op.id,
        expected_version=op.version,
        phrase=CONFIRM_IMPORTED_DATA,
        now=NOW,
        preview_ttl_minutes=30,
    )
    cancelled = await cancel_operation(session, user, confirmed.id, now=NOW)
    assert cancelled.state == DeletionOperationState.cancelled


async def test_running_operation_cannot_be_cancelled(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    op.state = DeletionOperationState.running
    await session.commit()
    with pytest.raises(InvalidDeletionStateError):
        await cancel_operation(session, user, op.id, now=NOW)


# --- retention (§11, tests 45/46/48/49/53) ----------------------------------


async def test_retention_deletes_expired_sources_and_preserves(session: AsyncSession) -> None:
    user = await _user(session)
    account = await _account(session, user.id)
    old = NOW - timedelta(days=40)
    await _source(session, user.id, account.id, "old-1", created_at=old)
    await _source(session, user.id, account.id, "fresh-1", created_at=NOW)
    # A pending execution's proposal must survive retention.
    p_pending = await _proposal(
        session,
        user.id,
        ["old-1"],
        status=ProposalStatus.executing,
        approved=True,
        fingerprint="rp",
    )
    await _execution(session, p_pending.id, ExecutionOutcome.pending)
    session.add(
        Preference(user_id=user.id, key="k", value_json={"v": 1}, provenance=Provenance.explicit)
    )
    await session.commit()

    bucket = NOW.date().isoformat()
    op = DataDeletionOperation(
        user_id=user.id,
        operation_type=DeletionOperationType.retention,
        requester_type="system",
        scope_key=scope_key_for(DeletionOperationType.retention, retention_bucket=bucket),
        scope_json={"bucket": bucket},
        snapshot_cutoff=NOW,
        state=DeletionOperationState.running,
        heartbeat_at=NOW,
    )
    session.add(op)
    await session.flush()
    while True:
        step = await run_retention_step(session, op, horizons=HORIZONS, now=NOW, batch_size=50)
        await session.commit()
        if step.done:
            break

    remaining = {
        r[0]
        for r in (
            await session.execute(
                select(SourceItem.external_id).where(SourceItem.user_id == user.id)
            )
        ).all()
    }
    assert remaining == {"fresh-1"}  # expired gone, fresh kept (45/46)
    # Pending execution preserved (48); confirmed preference preserved (49).
    exec_row = (
        await session.execute(
            select(ActionExecution).where(ActionExecution.proposal_id == p_pending.id)
        )
    ).scalar_one_or_none()
    assert exec_row is not None and exec_row.outcome == ExecutionOutcome.pending
    assert await _count(session, Preference, user.id) == 1


async def test_retention_scan_is_idempotent_across_ticks(session: AsyncSession) -> None:
    user = await _user(session)
    account = await _account(session, user.id)
    await _source(session, user.id, account.id, "old-1", created_at=NOW - timedelta(days=40))
    await session.commit()
    r1, _ids1 = await scan_and_create_retention_operations(
        session, horizons=HORIZONS, now=NOW, max_operations=50
    )
    await session.commit()
    r2, _ids2 = await scan_and_create_retention_operations(
        session, horizons=HORIZONS, now=NOW, max_operations=50
    )
    await session.commit()
    assert r1.created == 1
    assert r2.created == 0 and r2.reused == 1  # same day bucket -> no duplicate


async def test_retention_horizon_alters_eligibility(session: AsyncSession) -> None:
    user = await _user(session)
    account = await _account(session, user.id)
    await _source(session, user.id, account.id, "d20", created_at=NOW - timedelta(days=20))
    await session.commit()
    # 30-day horizon: not eligible.
    r, _ = await scan_and_create_retention_operations(
        session, horizons=HORIZONS, now=NOW, max_operations=50
    )
    assert r.created == 0
    # 10-day horizon: now eligible.
    short = RetentionHorizons(
        source_items_days=10,
        brief_versions_days=90,
        unapproved_proposals_days=90,
        scheduled_runs_days=90,
        memory_evidence_days=90,
    )
    r2, _ = await scan_and_create_retention_operations(
        session, horizons=short, now=NOW, max_operations=50
    )
    assert r2.created == 1


# --- account deletion (§12, tests 55-66) ------------------------------------


async def test_account_deletion_anonymises_and_preserves_tombstones(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    original_email = user.email
    op = await create_account_deletion_preview(session, user, now=NOW, ttl_minutes=30)
    assert op.preview_counts_json["connected_accounts"] == 2
    confirmed = await confirm_operation(
        session,
        user,
        op.id,
        expected_version=op.version,
        phrase=CONFIRM_ACCOUNT,
        now=NOW,
        preview_ttl_minutes=30,
    )
    # Confirmation blocks the account immediately (test 55/58).
    assert user.account_state == UserAccountState.deletion_pending
    await session.commit()

    final = await _run_to_completion(session, confirmed.id)
    assert final.state == DeletionOperationState.succeeded

    reloaded = await session.get(User, user.id, populate_existing=True)
    assert reloaded is not None
    assert reloaded.account_state == UserAccountState.deleted  # terminal (63)
    assert reloaded.deletion_subject_id is not None  # random subject (62)
    assert (
        reloaded.email != original_email and "@deleted.invalid" in reloaded.email
    )  # identity cleared (61)
    assert reloaded.google_subject is None

    # Personal product data removed (59); tokens/accounts gone (56).
    assert await _count(session, SourceItem, user.id) == 0
    assert await _count(session, Signal, user.id) == 0
    assert await _count(session, ConnectedAccount, user.id) == 0
    assert await _count(session, Preference, user.id) == 0
    assert await _count(session, MemoryItem, user.id) == 0
    # Audit tombstones retained (60) and content-free.
    assert await _count(session, AuditEvent, user.id) > 0
    # An execution tombstone survives, minimised.
    exec_rows = (
        (
            await session.execute(
                select(ActionExecution)
                .join(ActionProposal, ActionProposal.id == ActionExecution.proposal_id)
                .where(ActionProposal.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    assert exec_rows and all(e.executed_payload_json == {} for e in exec_rows)


async def test_account_deletion_is_idempotent(session: AsyncSession) -> None:
    user = await _user(session)
    await _account(session, user.id)
    op = await create_account_deletion_preview(session, user, now=NOW, ttl_minutes=30)
    confirmed = await confirm_operation(
        session,
        user,
        op.id,
        expected_version=op.version,
        phrase=CONFIRM_ACCOUNT,
        now=NOW,
        preview_ttl_minutes=30,
    )
    await session.commit()
    await _run_to_completion(session, confirmed.id)
    reloaded = await session.get(User, user.id, populate_existing=True)
    assert reloaded is not None
    subject_first = reloaded.deletion_subject_id
    # Re-running the same terminal operation must not regenerate the subject id.
    step = await run_account_deletion_step(session, confirmed, now=NOW, batch_size=50)
    assert step.done is True
    assert reloaded.deletion_subject_id == subject_first


async def test_account_deletion_revoke_failure_still_clears_credentials(
    session: AsyncSession,
) -> None:
    """Provider revoke failure still erases local credentials and marks the
    operation partially_failed (test 57)."""
    user = await _user(session)
    account = await _account(session, user.id)
    account.encrypted_refresh_token = "ciphertext"
    await session.commit()

    async def failing_revoker(account: ConnectedAccount) -> None:
        raise RuntimeError("provider down: SENTINEL-token-abc")

    op = await create_account_deletion_preview(session, user, now=NOW, ttl_minutes=30)
    confirmed = await confirm_operation(
        session,
        user,
        op.id,
        expected_version=op.version,
        phrase=CONFIRM_ACCOUNT,
        now=NOW,
        preview_ttl_minutes=30,
    )
    await session.commit()
    await run_operation(
        session,
        confirmed.id,
        now=NOW,
        horizons=HORIZONS,
        batch_size=50,
        max_attempts=3,
        revoker=failing_revoker,
    )
    final = await session.get(DataDeletionOperation, confirmed.id, populate_existing=True)
    assert final is not None and final.state == DeletionOperationState.partially_failed
    assert final.safe_error_code == "provider_revoke_failed"
    # No token or raw provider exception text ever enters the operation record.
    assert "SENTINEL-token" not in str(final.safe_error_message)
    assert await _count(session, ConnectedAccount, user.id) == 0  # local creds erased regardless


async def test_account_deletion_revoke_success_is_recorded_and_not_repeated(
    session: AsyncSession,
) -> None:
    """A successful revoke is attempted once per account and safely recorded; a
    resume does not revoke an already-processed account again (idempotent)."""
    user = await _user(session)
    account = await _account(session, user.id)
    account.encrypted_refresh_token = "ciphertext"
    await session.commit()
    calls: list[uuid.UUID] = []

    async def ok_revoker(acct: ConnectedAccount) -> None:
        calls.append(acct.id)

    op = await create_account_deletion_preview(session, user, now=NOW, ttl_minutes=30)
    confirmed = await confirm_operation(
        session,
        user,
        op.id,
        expected_version=op.version,
        phrase=CONFIRM_ACCOUNT,
        now=NOW,
        preview_ttl_minutes=30,
    )
    await session.commit()
    # First step: the credentials phase (revoke attempted once).
    await run_account_deletion_step(session, confirmed, now=NOW, batch_size=50, revoker=ok_revoker)
    await session.commit()
    assert calls == [account.id]
    assert confirmed.deleted_counts_json.get("provider_revocations") == 1
    # Run the rest to completion; the credentials phase never re-runs.
    await run_operation(
        session,
        confirmed.id,
        now=NOW,
        horizons=HORIZONS,
        batch_size=50,
        max_attempts=3,
        revoker=ok_revoker,
    )
    final = await session.get(DataDeletionOperation, confirmed.id, populate_existing=True)
    assert final is not None and final.state == DeletionOperationState.succeeded
    assert calls == [account.id]  # not revoked twice


# --- concurrency: atomic claim (§9, tests 20/43) ----------------------------


async def test_claim_is_atomic(session: AsyncSession) -> None:
    data = await _seed_imported_dataset(session)
    user: User = data["user"]  # type: ignore[assignment]
    account_a: ConnectedAccount = data["account_a"]  # type: ignore[assignment]
    op = await create_imported_data_preview(
        session, user, source_account_id=account_a.id, now=NOW, ttl_minutes=30
    )
    confirmed = await confirm_operation(
        session,
        user,
        op.id,
        expected_version=op.version,
        phrase=CONFIRM_IMPORTED_DATA,
        now=NOW,
        preview_ttl_minutes=30,
    )
    await session.commit()
    first = await claim_operation(session, confirmed.id, now=NOW)
    second = await claim_operation(session, confirmed.id, now=NOW)
    assert first is not None
    assert second is None  # only one worker wins
