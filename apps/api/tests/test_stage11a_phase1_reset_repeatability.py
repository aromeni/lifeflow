"""Stage 11A Phase 1 (docs/delivery/stage-11a-phase-1-plan.md): proves the
owner-facing workflow — demo import, brief generation, one proposal
approved and executed, full account deletion — is safe and repeatable
across 10 independent synthetic cycles, using the real HTTP surface for
the user-facing steps and the real worker body (`run_operation`) to
complete the queued deletion without needing a live arq process.

No production reset endpoint exists for this purpose (the only reset route,
`POST /__control__/reset` in `testing/fake_google_server.py`, is scoped to
the resilience E2E harness). This test is that harness for Stage 11A: each
cycle uses a fresh synthetic user and ends by deleting it via the
already-tested account-deletion path, so no cycle can contaminate the next.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL, _make_client, _test_settings

from lifeflow_api.deletion import run_operation
from lifeflow_api.models import (
    ActionExecution,
    ActionProposal,
    AuditEvent,
    ConnectedAccount,
    MemoryItem,
    Preference,
    Signal,
    SourceItem,
    User,
    UserAccountState,
)
from lifeflow_api.retention import RetentionHorizons

pytestmark = pytest.mark.integration

CYCLES = 10
NOW = datetime.now(UTC)
HORIZONS = RetentionHorizons(
    source_items_days=30,
    brief_versions_days=90,
    unapproved_proposals_days=90,
    scheduled_runs_days=90,
    memory_evidence_days=90,
)
CONFIRM_ACCOUNT_PHRASE = "DELETE MY LIFEFLOW ACCOUNT"


async def _count(session: AsyncSession, model: type, user_id: object) -> int:
    return len(
        (await session.execute(select(model).where(model.user_id == user_id))).scalars().all()
    )


async def _run_one_cycle(cycle: int) -> dict[str, int]:
    email = f"stage11a-phase1-cycle-{cycle}@lifeflow-owner-validation.example"
    settings = _test_settings("development")

    user_id_str = ""
    imported = 0
    proposal_count = 0
    execution_count_after_double_execute = 0

    async for client in _make_client(settings):
        login = await client.post("/auth/dev-login", json={"email": email}, headers=CSRF_HEADERS)
        assert login.status_code == 200
        user_id_str = login.json()["user_id"]

        start = await client.post("/demo/start", headers=CSRF_HEADERS)
        assert start.status_code == 200
        imported = start.json()["imported"]
        assert imported > 0

        brief = await client.post("/briefs/generate", headers=CSRF_HEADERS)
        assert brief.status_code == 200

        proposals = (await client.get("/action-proposals")).json()["proposals"]
        proposal_count = len(proposals)
        assert proposal_count > 0

        target = proposals[0]
        approve = await client.post(
            f"/action-proposals/{target['id']}/approve",
            headers=CSRF_HEADERS,
            json={
                "expected_version": target["version"],
                "action_type": target["action_type"],
                "displayed_payload_hash": target["payload_hash"],
                "displayed_execution_context_hash": target["execution_context_hash"],
            },
        )
        assert approve.status_code == 200

        first_execute = await client.post(
            f"/action-proposals/{target['id']}/execute", headers=CSRF_HEADERS
        )
        assert first_execute.status_code == 200
        assert first_execute.json()["execution"] is not None

        # Safety invariant (S-H5 / ADR 0003 D16): a second execute call must
        # never dispatch the executor again — replay only, no duplicate write.
        second_execute = await client.post(
            f"/action-proposals/{target['id']}/execute", headers=CSRF_HEADERS
        )
        assert second_execute.status_code == 200
        assert (
            second_execute.json()["execution"]["id"] == first_execute.json()["execution"]["id"]
        ), "a duplicate execution record was created by a repeated execute call"

        preview = await client.post("/privacy/account-deletion/preview", headers=CSRF_HEADERS)
        assert preview.status_code == 200
        preview_body = preview.json()
        assert preview_body["confirmation_phrase"] == CONFIRM_ACCOUNT_PHRASE

        confirm = await client.post(
            f"/privacy/deletion-operations/{preview_body['operation_id']}/confirm",
            json={
                "expected_version": preview_body["version"],
                "confirmation_phrase": CONFIRM_ACCOUNT_PHRASE,
            },
            headers=CSRF_HEADERS,
        )
        assert confirm.status_code == 200
        operation_id = preview_body["operation_id"]

    # Complete the queued deletion by invoking the real worker body directly
    # (no live arq/Redis worker is started for this synthetic harness).
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await run_operation(
            session,
            operation_id,
            now=NOW,
            horizons=HORIZONS,
            batch_size=50,
            max_attempts=3,
        )
        await session.commit()

        user_id = user_id_str
        reloaded = await session.get(User, user_id, populate_existing=True)
        assert reloaded is not None
        assert reloaded.account_state == UserAccountState.deleted
        assert "@deleted.invalid" in reloaded.email

        # No content-bearing residual data survives (test_deletion_engine.py's
        # test_account_deletion_anonymises_and_preserves_tombstones asserts
        # the identical residual contract this reuses).
        assert await _count(session, SourceItem, user_id) == 0
        assert await _count(session, Signal, user_id) == 0
        assert await _count(session, ConnectedAccount, user_id) == 0
        assert await _count(session, Preference, user_id) == 0
        assert await _count(session, MemoryItem, user_id) == 0
        # Content-free tombstones are permitted and expected to remain.
        assert await _count(session, AuditEvent, user_id) > 0

        execution_count_after_double_execute = len(
            (
                await session.execute(
                    select(ActionExecution)
                    .join(ActionProposal, ActionProposal.id == ActionExecution.proposal_id)
                    .where(ActionProposal.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()

    return {
        "imported": imported,
        "proposal_count": proposal_count,
        "execution_count": execution_count_after_double_execute,
    }


async def test_ten_reset_cycles_are_deterministic_and_leave_no_residue() -> None:
    results = [await _run_one_cycle(cycle) for cycle in range(1, CYCLES + 1)]

    assert len(results) == CYCLES

    imported_counts = {r["imported"] for r in results}
    assert len(imported_counts) == 1, (
        f"demo import produced different counts across cycles: {imported_counts} "
        "— the synthetic dataset must yield an identical import count every cycle"
    )

    proposal_counts = {r["proposal_count"] for r in results}
    assert len(proposal_counts) == 1, (
        f"brief generation produced different proposal counts across cycles: {proposal_counts}"
    )

    execution_counts = {r["execution_count"] for r in results}
    assert execution_counts == {1}, (
        "every cycle must retain exactly one execution tombstone per approved-and-"
        f"executed proposal, with zero duplicates from the repeated execute call; got {results}"
    )
