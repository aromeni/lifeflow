"""Stage 9 Delivery Phase 2: the privacy deletion API (ADR 0005 §13).

Owner-scoped preview/confirm/cancel/list/get for imported-data and account
deletion, plus the mutation guards that block a deletion-pending account and the
session invalidation that a deleted account enforces. A confirmed operation is
left `pending` (the worker cron drains it) so these tests never need Redis.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL, _make_client, _test_settings

from lifeflow_api.models import (
    ActionProposal,
    ConnectedAccount,
    SourceItem,
    User,
    UserAccountState,
)

pytestmark = pytest.mark.integration

SECRET_SUBJECT = "SENTINEL-subject-must-not-leak"  # pragma: allowlist secret
SECRET_BODY = "SENTINEL-body-must-not-leak"  # pragma: allowlist secret


async def _login(client: AsyncClient, marker: str) -> uuid.UUID:
    response = await client.post(
        "/auth/dev-login",
        json={"email": f"del-{marker}-{uuid.uuid4()}@example.com", "display_name": "Del"},
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200
    return uuid.UUID(response.json()["user_id"])


async def _seed_account(user_id: uuid.UUID, *, provider: str = "google") -> uuid.UUID:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as s:
            account = ConnectedAccount(user_id=user_id, provider=provider, granted_scopes=[])
            s.add(account)
            await s.flush()
            account_id = account.id
            s.add(
                SourceItem(
                    user_id=user_id,
                    source_type="email",
                    external_id=f"em-{uuid.uuid4()}",
                    source_account_id=account_id,
                    title=SECRET_SUBJECT,
                    sender_or_organiser="x@example.com",
                    occurred_at=datetime.now(UTC),
                    content_fingerprint="fp",
                )
            )
            s.add(
                ActionProposal(
                    user_id=user_id,
                    origin_fingerprint=f"f-{uuid.uuid4()}",
                    action_type="create_gmail_draft",
                    rationale="rationale",
                    source_refs=[],
                    payload_json={"body": SECRET_BODY},
                    payload_hash="h",
                    risk_level="medium",
                    confidence=0.9,
                    status="proposed",
                    expires_at=datetime.now(UTC) + timedelta(days=7),
                )
            )
            await s.commit()
            return account_id
    finally:
        await engine.dispose()


async def _set_account_state(user_id: uuid.UUID, state: str) -> None:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as s:
            user = await s.get(User, user_id)
            assert user is not None
            user.account_state = state
            await s.commit()
    finally:
        await engine.dispose()


@pytest.fixture
async def dev_client_unreachable_redis() -> AsyncIterator[AsyncClient]:
    settings = _test_settings("development").model_copy(
        update={"redis_url": "redis://localhost:1/0"}
    )
    async for c in _make_client(settings):
        yield c


# --- imported-data preview + confirm ----------------------------------------


async def test_preview_and_confirm_imported_data(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "imp")
    account_id = await _seed_account(user_id)

    preview = await dev_client.post(
        f"/privacy/imported-data/{account_id}/preview", headers=CSRF_HEADERS
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["confirmation_phrase"] == "DELETE IMPORTED DATA"
    assert body["preview_counts"]["source_items"] == 1
    assert body["state"] == "previewed"
    # No stored content leaks into the preview response.
    assert SECRET_SUBJECT not in preview.text and SECRET_BODY not in preview.text

    confirm = await dev_client.post(
        f"/privacy/deletion-operations/{body['operation_id']}/confirm",
        json={"expected_version": body["version"], "confirmation_phrase": "DELETE IMPORTED DATA"},
        headers=CSRF_HEADERS,
    )
    assert confirm.status_code == 200
    assert confirm.json()["state"] == "pending"  # queued; worker drains it


async def test_confirm_wrong_phrase_422(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "wp")
    account_id = await _seed_account(user_id)
    preview = (
        await dev_client.post(f"/privacy/imported-data/{account_id}/preview", headers=CSRF_HEADERS)
    ).json()
    resp = await dev_client.post(
        f"/privacy/deletion-operations/{preview['operation_id']}/confirm",
        json={
            "expected_version": preview["version"],
            "confirmation_phrase": "delete imported data",
        },
        headers=CSRF_HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_confirmation"


async def _seed_affected_proposal(user_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """A connected account + a source item + an unapproved proposal that
    references it (so a state change alters the deletion plan). Returns
    (account_id, proposal_id)."""
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as s:
            account = ConnectedAccount(user_id=user_id, provider="google", granted_scopes=[])
            s.add(account)
            await s.flush()
            ext = f"em-{uuid.uuid4()}"
            s.add(
                SourceItem(
                    user_id=user_id,
                    source_type="email",
                    external_id=ext,
                    source_account_id=account.id,
                    title="t",
                    sender_or_organiser="x@example.com",
                    occurred_at=datetime.now(UTC),
                    content_fingerprint="fp",
                )
            )
            proposal = ActionProposal(
                user_id=user_id,
                origin_fingerprint=f"f-{uuid.uuid4()}",
                action_type="create_gmail_draft",
                rationale="r",
                source_refs=[ext],
                payload_json={"body": SECRET_BODY},
                payload_hash="h",
                risk_level="medium",
                confidence=0.9,
                status="proposed",
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
            s.add(proposal)
            await s.flush()
            await s.commit()
            return account.id, proposal.id
    finally:
        await engine.dispose()


async def _approve_proposal(proposal_id: uuid.UUID) -> None:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as s:
            proposal = await s.get(ActionProposal, proposal_id)
            assert proposal is not None
            proposal.status = "approved"
            proposal.approved_at = datetime.now(UTC)
            await s.commit()
    finally:
        await engine.dispose()


async def test_confirm_after_plan_change_returns_preview_changed_then_succeeds(
    dev_client: AsyncClient,
) -> None:
    user_id = await _login(dev_client, "pc")
    account_id, proposal_id = await _seed_affected_proposal(user_id)
    preview = (
        await dev_client.post(f"/privacy/imported-data/{account_id}/preview", headers=CSRF_HEADERS)
    ).json()

    # The plan changes after review: the referenced proposal is approved.
    await _approve_proposal(proposal_id)

    changed = await dev_client.post(
        f"/privacy/deletion-operations/{preview['operation_id']}/confirm",
        json={
            "expected_version": preview["version"],
            "confirmation_phrase": "DELETE IMPORTED DATA",
        },
        headers=CSRF_HEADERS,
    )
    assert changed.status_code == 409
    body = changed.json()
    assert body["error"]["code"] == "preview_changed"
    # The refreshed preview (new version) is returned so the client can re-review.
    assert body["state"] == "previewed"
    assert body["version"] == preview["version"] + 1
    assert SECRET_BODY not in changed.text

    # Re-confirming the refreshed plan succeeds.
    ok = await dev_client.post(
        f"/privacy/deletion-operations/{preview['operation_id']}/confirm",
        json={"expected_version": body["version"], "confirmation_phrase": "DELETE IMPORTED DATA"},
        headers=CSRF_HEADERS,
    )
    assert ok.status_code == 200
    assert ok.json()["state"] == "pending"


async def test_confirm_stale_version_409(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "sv")
    account_id = await _seed_account(user_id)
    preview = (
        await dev_client.post(f"/privacy/imported-data/{account_id}/preview", headers=CSRF_HEADERS)
    ).json()
    resp = await dev_client.post(
        f"/privacy/deletion-operations/{preview['operation_id']}/confirm",
        json={
            "expected_version": preview["version"] + 9,
            "confirmation_phrase": "DELETE IMPORTED DATA",
        },
        headers=CSRF_HEADERS,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "stale_version"


async def test_preview_unknown_account_404(dev_client: AsyncClient) -> None:
    await _login(dev_client, "uk")
    resp = await dev_client.post(
        f"/privacy/imported-data/{uuid.uuid4()}/preview", headers=CSRF_HEADERS
    )
    assert resp.status_code == 404


async def test_cross_user_operation_is_404(dev_client: AsyncClient) -> None:
    user_a = await _login(dev_client, "a")
    account_id = await _seed_account(user_a)
    preview = (
        await dev_client.post(f"/privacy/imported-data/{account_id}/preview", headers=CSRF_HEADERS)
    ).json()
    operation_id = preview["operation_id"]
    # Switch to a different user in the same client (new dev-login).
    await _login(dev_client, "b")
    resp = await dev_client.get(f"/privacy/deletion-operations/{operation_id}")
    assert resp.status_code == 404


async def test_cancel_pending_operation(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "cx")
    account_id = await _seed_account(user_id)
    preview = (
        await dev_client.post(f"/privacy/imported-data/{account_id}/preview", headers=CSRF_HEADERS)
    ).json()
    confirm = (
        await dev_client.post(
            f"/privacy/deletion-operations/{preview['operation_id']}/confirm",
            json={
                "expected_version": preview["version"],
                "confirmation_phrase": "DELETE IMPORTED DATA",
            },
            headers=CSRF_HEADERS,
        )
    ).json()
    cancel = await dev_client.post(
        f"/privacy/deletion-operations/{confirm['operation_id']}/cancel", headers=CSRF_HEADERS
    )
    assert cancel.status_code == 200
    assert cancel.json()["state"] == "cancelled"


async def test_list_deletion_operations(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "ls")
    account_id = await _seed_account(user_id)
    await dev_client.post(f"/privacy/imported-data/{account_id}/preview", headers=CSRF_HEADERS)
    resp = await dev_client.get("/privacy/deletion-operations")
    assert resp.status_code == 200
    assert len(resp.json()["operations"]) == 1


# --- account deletion + mutation guards + session invalidation --------------


async def test_account_deletion_preview_confirm_blocks_mutations(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "acc")
    await _seed_account(user_id)
    preview = (
        await dev_client.post("/privacy/account-deletion/preview", headers=CSRF_HEADERS)
    ).json()
    assert preview["confirmation_phrase"] == "DELETE MY LIFEFLOW ACCOUNT"
    confirm = await dev_client.post(
        f"/privacy/deletion-operations/{preview['operation_id']}/confirm",
        json={
            "expected_version": preview["version"],
            "confirmation_phrase": "DELETE MY LIFEFLOW ACCOUNT",
        },
        headers=CSRF_HEADERS,
    )
    assert confirm.status_code == 200
    # Mutations are now blocked while deletion is pending (§12).
    gen = await dev_client.post("/briefs/generate", headers=CSRF_HEADERS)
    assert gen.status_code == 409
    # Read-only status stays available so the UI can show progress.
    status = await dev_client.get("/privacy/deletion-operations")
    assert status.status_code == 200


async def test_deleted_account_cannot_authenticate(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "gone")
    # Simulate the worker having completed anonymisation.
    await _set_account_state(user_id, UserAccountState.deleted)
    # The existing session cookie must now be rejected (session invalidation).
    resp = await dev_client.get("/privacy/deletion-operations")
    assert resp.status_code == 401


# --- redis outage does not block preview/confirm ----------------------------


async def test_preview_and_confirm_work_with_redis_down(
    dev_client_unreachable_redis: AsyncClient,
) -> None:
    client = dev_client_unreachable_redis
    user_id = await _login(client, "rd")
    account_id = await _seed_account(user_id)
    preview = (
        await client.post(f"/privacy/imported-data/{account_id}/preview", headers=CSRF_HEADERS)
    ).json()
    confirm = await client.post(
        f"/privacy/deletion-operations/{preview['operation_id']}/confirm",
        json={
            "expected_version": preview["version"],
            "confirmation_phrase": "DELETE IMPORTED DATA",
        },
        headers=CSRF_HEADERS,
    )
    assert confirm.status_code == 200
    assert confirm.json()["state"] == "pending"  # persisted; drained later


async def test_no_pageload_side_effects(dev_client: AsyncClient) -> None:
    """Listing/getting operations never mutates anything (§18 test 95)."""
    user_id = await _login(dev_client, "ro")
    await _seed_account(user_id)
    before = await _proposal_count(user_id)
    await dev_client.get("/privacy/deletion-operations")
    await dev_client.get("/privacy/summary")
    assert await _proposal_count(user_id) == before


async def _proposal_count(user_id: uuid.UUID) -> int:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as s:
            rows = (
                await s.execute(select(ActionProposal).where(ActionProposal.user_id == user_id))
            ).all()
            return len(rows)
    finally:
        await engine.dispose()
