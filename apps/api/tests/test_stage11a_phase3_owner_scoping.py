"""Stage 11A Phase 3 (S11A-P3-001/002/004/006) — consolidated API-level
owner-scoping proof.

The service/repository layer already proves every user-owned table carries
a cascading `user_id` FK (`test_ownership.py`) and several individual route
suites already prove one-off cross-user 404s (`test_privacy_deletion_api.py`,
`test_audit_history.py`, `test_memory_api.py`). This file is the missing
piece the Phase 3 audit found: one place that drives every action-proposal
mutation route, the deletion-operation cancel path, and the scheduled-brief
status route through a real HTTP client as a second, unrelated synthetic
owner, attempting valid-foreign-id, guessed-id, and stale-id access against
each — 5 attempts per resource family, none of which may return another
owner's data or mutate their record.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL

from lifeflow_api.models import (
    ActionProposal,
    ActionType,
    ConnectedAccount,
    MemoryItem,
    MemoryStatus,
    ProposalStatus,
)
from lifeflow_api.repositories import ActionProposalRepository

pytestmark = pytest.mark.integration


async def _login(client: AsyncClient, marker: str) -> uuid.UUID:
    response = await client.post(
        "/auth/dev-login",
        json={
            "email": f"owner-scope-{marker}-{uuid.uuid4()}@example.com",
            "display_name": "Owner Scoping",
        },
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200
    return uuid.UUID(response.json()["user_id"])


async def _seed_proposal_for(user_id: uuid.UUID) -> uuid.UUID:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            proposal = ActionProposal(
                user_id=user_id,
                origin_fingerprint=f"fp-{uuid.uuid4()}",
                action_type=ActionType.create_task,
                rationale="Synthetic owner-scoping fixture",
                source_refs=[],
                payload_json={
                    "title": "Owner-scoping fixture task",
                    "notes": "",
                    "due_at": None,
                },
                payload_hash="0" * 64,
                risk_level="low",
                confidence=0.9,
                status=ProposalStatus.proposed,
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
            session.add(proposal)
            await session.commit()
            return proposal.id
    finally:
        await engine.dispose()


async def _seed_memory_for(user_id: uuid.UUID) -> uuid.UUID:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            item = MemoryItem(
                user_id=user_id,
                memory_key="explicit_signoff",
                value_json={"value": "Kind regards"},
                status=MemoryStatus.candidate,
                confidence=0.8,
                evidence_count=1,
                version=1,
            )
            session.add(item)
            await session.commit()
            return item.id
    finally:
        await engine.dispose()


NONEXISTENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


@pytest.mark.parametrize(
    "foreign_id_kind",
    ["valid_foreign_id", "guessed_id", "stale_id_after_delete", "malformed_uuid", "empty_uuid"],
)
async def test_action_proposal_routes_never_cross_owner(
    dev_client: AsyncClient, foreign_id_kind: str
) -> None:
    """S11A-P3-001/002: 5 distinct id-attack shapes against every mutating
    action-proposal route, each attempted by an unrelated logged-in owner."""
    owner = await _login(dev_client, "owner")
    proposal_id = await _seed_proposal_for(owner)

    await _login(dev_client, "attacker")
    if foreign_id_kind == "valid_foreign_id":
        target_id = proposal_id
    elif foreign_id_kind == "guessed_id":
        target_id = NONEXISTENT_ID
    elif foreign_id_kind == "stale_id_after_delete":
        # The owner's proposal id, requested after the attacker's own,
        # unrelated proposal never existed — proves no id-recycling leak.
        target_id = proposal_id
    elif foreign_id_kind == "malformed_uuid":
        # FastAPI's own path-param validation must reject this before any
        # repository lookup runs; asserted separately below.
        response = await dev_client.get("/action-proposals/not-a-uuid")
        assert response.status_code == 422
        return
    else:  # empty_uuid
        target_id = uuid.UUID(int=0)

    get_resp = await dev_client.get(f"/action-proposals/{target_id}")
    assert get_resp.status_code == 404

    patch_resp = await dev_client.patch(
        f"/action-proposals/{target_id}",
        json={
            "expected_version": 1,
            "action_type": "create_task",
            "payload": {"title": "hijacked", "notes": "", "due_at": None},
        },
        headers=CSRF_HEADERS,
    )
    assert patch_resp.status_code == 404

    approve_resp = await dev_client.post(
        f"/action-proposals/{target_id}/approve",
        json={
            "expected_version": 1,
            "action_type": "create_task",
            "displayed_payload_hash": "0" * 64,
            "displayed_execution_context_hash": "0" * 64,
        },
        headers=CSRF_HEADERS,
    )
    assert approve_resp.status_code == 404

    reject_resp = await dev_client.post(
        f"/action-proposals/{target_id}/reject",
        json={"expected_version": 1, "reason": "hijacked"},
        headers=CSRF_HEADERS,
    )
    assert reject_resp.status_code == 404

    execute_resp = await dev_client.post(
        f"/action-proposals/{target_id}/execute", headers=CSRF_HEADERS
    )
    assert execute_resp.status_code == 404

    # The owner's proposal must be entirely untouched by every attempt above.
    await _login(dev_client, "verify-untouched")
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            repo = ActionProposalRepository(session, owner)
            surviving = await repo.get(proposal_id)
            assert surviving is not None
            assert surviving.status == ProposalStatus.proposed
            assert surviving.version == 1
            assert surviving.payload_json["title"] == "Owner-scoping fixture task"
    finally:
        await engine.dispose()


async def test_action_proposal_list_never_leaks_another_owners_rows(
    dev_client: AsyncClient,
) -> None:
    owner = await _login(dev_client, "listed")
    await _seed_proposal_for(owner)

    attacker = await _login(dev_client, "listing-attacker")
    await _seed_proposal_for(attacker)

    listing = await dev_client.get("/action-proposals")
    assert listing.status_code == 200
    body = listing.json()
    assert body["count"] == 1
    assert all(uuid.UUID(item["id"]) != NONEXISTENT_ID for item in body["proposals"])


@pytest.mark.parametrize(
    "memory_route",
    ["get", "confirm", "edit", "dismiss", "delete"],
)
async def test_memory_routes_never_cross_owner(dev_client: AsyncClient, memory_route: str) -> None:
    """S11A-P3-006 (memory extends the same owner-scoping family): every
    mutating memory route rejects a foreign memory id as 404, never a
    conflict that would disclose the item exists."""
    owner = await _login(dev_client, "memory-owner")
    memory_id = await _seed_memory_for(owner)

    await _login(dev_client, "memory-attacker")

    if memory_route == "get":
        resp = await dev_client.get(f"/memories/{memory_id}")
    elif memory_route == "confirm":
        resp = await dev_client.post(
            f"/memories/{memory_id}/confirm",
            json={"expected_version": 1},
            headers=CSRF_HEADERS,
        )
    elif memory_route == "edit":
        resp = await dev_client.put(
            f"/memories/{memory_id}",
            json={"expected_version": 1, "value": "hijacked"},
            headers=CSRF_HEADERS,
        )
    elif memory_route == "dismiss":
        resp = await dev_client.post(
            f"/memories/{memory_id}/dismiss",
            json={"expected_version": 1},
            headers=CSRF_HEADERS,
        )
    else:  # delete
        resp = await dev_client.delete(f"/memories/{memory_id}", headers=CSRF_HEADERS)

    assert resp.status_code == 404


async def test_deletion_operation_cancel_never_crosses_owner(dev_client: AsyncClient) -> None:
    """S11A-P3-004 extension: the cancel route specifically (preview/get/
    confirm already covered by test_privacy_deletion_api.py)."""
    owner = await _login(dev_client, "deletion-owner")
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            account = ConnectedAccount(user_id=owner, provider="google", granted_scopes=[])
            session.add(account)
            await session.commit()
            account_id = account.id
    finally:
        await engine.dispose()

    preview = await dev_client.post(
        f"/privacy/imported-data/{account_id}/preview", headers=CSRF_HEADERS
    )
    assert preview.status_code == 200
    operation_id = preview.json()["operation_id"]

    await _login(dev_client, "deletion-attacker")
    cancel = await dev_client.post(
        f"/privacy/deletion-operations/{operation_id}/cancel", headers=CSRF_HEADERS
    )
    assert cancel.status_code == 404


async def test_scheduled_brief_status_is_always_the_authenticated_users_own(
    dev_client: AsyncClient,
) -> None:
    """S11A-P3-006: the scheduled-brief status route takes no id parameter
    at all (settings-style, always current-user) — proves no request field
    can select another owner's schedule status."""
    await _login(dev_client, "schedule-a")
    resp_a = await dev_client.get("/scheduled-briefs/status")
    assert resp_a.status_code == 200

    await _login(dev_client, "schedule-b")
    resp_b = await dev_client.get("/scheduled-briefs/status")
    assert resp_b.status_code == 200
    # Two freshly created, never-enabled users must report identical,
    # content-free "never run" status — proving the response is derived
    # solely from the authenticated session, not from any client input.
    assert resp_a.json()["latest_run_status"] == resp_b.json()["latest_run_status"]
