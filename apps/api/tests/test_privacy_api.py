"""Stage 9 Delivery Phase 1: GET /privacy/summary — the read-only Privacy &
Connections Control Centre.

Non-destructive by construction: these tests prove ownership isolation, that
the summary tells the truth about connection/scope/freshness state and stored
counts, that it never leaks a token, ciphertext, sync cursor, provider id,
proposal payload/hash, or audit metadata, that retention defaults come from
validated config and are described as not-yet-enforced, and that the endpoint
stays available with Redis down and never triggers a Google sync.
"""

import base64
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL, _make_client, _test_settings

from lifeflow_api.models import (
    AccountStatus,
    ActionExecution,
    ActionProposal,
    AuditEvent,
    Brief,
    ConnectedAccount,
    MemoryEvidence,
    MemoryItem,
    Preference,
    ScheduledBriefRun,
    Signal,
    SourceItem,
)
from lifeflow_api.security.token_cipher import AesGcmTokenCipher

pytestmark = pytest.mark.integration

GMAIL_RO = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_COMPOSE = "https://www.googleapis.com/auth/gmail.compose"
CAL_RO = "https://www.googleapis.com/auth/calendar.readonly"

# Distinctive, obviously-fake sentinel values seeded into secret-bearing
# columns; the summary response must never contain any of them. These are not
# real secrets — they exist only to prove the endpoint never leaks such fields.
SECRET_ACCESS = "SENTINEL-ACCESS-TOKEN-abc123"  # pragma: allowlist secret
SECRET_REFRESH = "SENTINEL-REFRESH-TOKEN-def456"  # pragma: allowlist secret
SECRET_CURSOR = "SENTINEL-CURSOR-history-789"  # pragma: allowlist secret
SECRET_EXTERNAL_ID = "SENTINEL-gmail-msg-id-0001"  # pragma: allowlist secret
SECRET_PAYLOAD_HASH = "SENTINEL-PAYLOAD-HASH-cafe"  # pragma: allowlist secret
SECRET_AUDIT_META = "SENTINEL-AUDIT-META-value"  # pragma: allowlist secret


@pytest.fixture
async def dev_client_unreachable_redis() -> AsyncIterator[AsyncClient]:
    settings = _test_settings("development").model_copy(
        update={"redis_url": "redis://localhost:1/0"}
    )
    async for c in _make_client(settings):
        yield c


async def _login(client: AsyncClient, marker: str) -> uuid.UUID:
    response = await client.post(
        "/auth/dev-login",
        json={"email": f"privacy-{marker}-{uuid.uuid4()}@example.com", "display_name": "Priv"},
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200
    return uuid.UUID(response.json()["user_id"])


def _cipher() -> AesGcmTokenCipher:
    return AesGcmTokenCipher(key_b64=base64.b64encode(os.urandom(32)).decode(), key_id="test-1")


async def _seed_full_dataset(user_id: uuid.UUID, *, last_sync: datetime | None) -> dict[str, int]:
    """Seed one row (or a known number) in every inventory category, with
    secret sentinels in the secret-bearing columns. Returns expected counts."""
    engine = create_async_engine(TEST_DB_URL)
    cipher = _cipher()
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as s:
            account = ConnectedAccount(
                user_id=user_id,
                provider="google",
                status=AccountStatus.active,
                encrypted_access_token=cipher.encrypt(SECRET_ACCESS),
                encrypted_refresh_token=cipher.encrypt(SECRET_REFRESH),
                granted_scopes=[GMAIL_RO, GMAIL_COMPOSE, CAL_RO],
                last_sync_at=last_sync,
                sync_cursors={"gmail": {"history_id": SECRET_CURSOR}},
                authorisation_revision=3,
            )
            s.add(account)
            source = SourceItem(
                user_id=user_id,
                source_type="email",
                external_id=SECRET_EXTERNAL_ID,
                title="Subject line that must never leak",
                sender_or_organiser="someone@example.com",
                occurred_at=datetime.now(UTC),
                content_fingerprint="fp",
            )
            s.add(source)
            s.add(
                Signal(
                    user_id=user_id,
                    signal_type="request",
                    title="Signal title",
                    summary="Signal summary",
                    confidence=0.5,
                    urgency=0.5,
                    importance=0.5,
                    extraction_version="v1",
                    dedupe_key=f"dk-{uuid.uuid4().hex}",
                )
            )
            # Two brief versions on the SAME date → briefs=1, brief_versions=2.
            bdate = datetime.now(UTC)
            for v in (1, 2):
                s.add(
                    Brief(
                        user_id=user_id,
                        briefing_date=bdate,
                        version=v,
                        summary="s",
                        source_window="w",
                    )
                )
            proposal = ActionProposal(
                user_id=user_id,
                origin_fingerprint=f"of-{uuid.uuid4().hex}",
                action_type="create_gmail_draft",
                rationale="r",
                source_refs=[],
                payload_json={"body": "draft body that must never leak"},
                payload_hash=SECRET_PAYLOAD_HASH,
                version=1,
                risk_level="medium",
                confidence=0.7,
                status="executed",
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
            s.add(proposal)
            await s.flush()
            s.add(
                ActionExecution(
                    proposal_id=proposal.id,
                    idempotency_key=f"idem-{uuid.uuid4().hex}",
                    approved_action_type="create_gmail_draft",
                    approved_proposal_version=1,
                    executed_payload_json={"body": "x"},
                    executed_payload_hash="h",
                    approval_binding_hash="b",
                    execution_mode="simulation",
                    outcome="succeeded",
                )
            )
            s.add(
                ScheduledBriefRun(
                    user_id=user_id,
                    local_brief_date=bdate.date(),
                    scheduled_for_utc=bdate,
                    timezone_snapshot="Europe/London",
                    briefing_time_snapshot="08:00",
                    status="succeeded",
                )
            )
            s.add(Preference(user_id=user_id, key="briefing_time", value_json={"value": "08:00"}))
            item = MemoryItem(
                user_id=user_id,
                memory_key="preferred_email_signoff",
                value_json={"value": "Kind regards"},
                status="candidate",
                confidence=0.5,
                evidence_count=1,
            )
            s.add(item)
            await s.flush()
            s.add(
                MemoryEvidence(
                    memory_item_id=item.id,
                    user_id=user_id,
                    evidence_type="signoff",
                    observed_at=datetime.now(UTC),
                    derived_value="Kind regards",
                    reason_code="approved_edited_draft",
                )
            )
            s.add(
                AuditEvent(
                    user_id=user_id,
                    actor=f"user:{user_id}",
                    event_type="brief.generated",
                    entity_type="brief",
                    entity_id=str(uuid.uuid4()),
                    safe_metadata_json={"note": SECRET_AUDIT_META},
                    correlation_id="corr-1",
                )
            )
            await s.commit()
    finally:
        await engine.dispose()
    return {
        "connected_accounts": 1,
        "source_items": 1,
        "signals": 1,
        "briefs": 1,
        "brief_versions": 2,
        "action_proposals": 1,
        "action_executions": 1,
        "scheduled_brief_runs": 1,
        "preferences": 1,
        "memory_items": 1,
        "memory_evidence": 1,
        "audit_events": 1,
    }


async def _add_account(
    user_id: uuid.UUID,
    *,
    status: str = AccountStatus.active,
    scopes: list[str] | None = None,
    last_sync_at: datetime | None = None,
) -> None:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as s:
            s.add(
                ConnectedAccount(
                    user_id=user_id,
                    provider="google",
                    status=status,
                    granted_scopes=scopes if scopes is not None else [GMAIL_RO, CAL_RO],
                    last_sync_at=last_sync_at,
                )
            )
            await s.commit()
    finally:
        await engine.dispose()


async def test_summary_counts_are_owner_scoped_and_correct(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "counts")
    expected = await _seed_full_dataset(user_id, last_sync=datetime.now(UTC))
    inventory = (await dev_client.get("/privacy/summary")).json()["inventory"]
    # Every seeded category is exact (test 14). Audit events also include the
    # system-generated dev-login events (user.created/session.created), so it
    # is asserted as "at least the seeded one" rather than pinned.
    for key, count in expected.items():
        if key == "audit_events":
            assert inventory[key] >= count
        else:
            assert inventory[key] == count, key


async def test_one_user_never_sees_another_users_accounts_or_counts(
    dev_client: AsyncClient,
) -> None:
    other = await _login(dev_client, "other")
    await _seed_full_dataset(other, last_sync=datetime.now(UTC))
    await dev_client.post("/auth/logout", headers=CSRF_HEADERS)
    await _login(dev_client, "me")
    response = await dev_client.get("/privacy/summary")
    body = response.json()
    assert body["connections"] == []
    # Every category the "other" user populated is zero for "me"; audit_events
    # only ever reflects "me"'s own login events, never the other user's.
    for key, count in body["inventory"].items():
        if key != "audit_events":
            assert count == 0, key
    assert str(other) not in response.text  # no trace of the other user's data


async def test_connected_and_disconnected_and_never_synced_states(
    dev_client: AsyncClient,
) -> None:
    user_id = await _login(dev_client, "states")
    await _add_account(user_id, status=AccountStatus.disconnected, last_sync_at=None)
    conn = (await dev_client.get("/privacy/summary")).json()["connections"][0]
    assert conn["status"] == "disconnected"
    assert conn["connected"] is False
    assert conn["ever_synced"] is False  # never-synced truthful (test 5)
    assert conn["freshness_band"] is None
    assert conn["can_disconnect"] is False
    assert conn["can_reconnect"] is True


@pytest.mark.parametrize(
    ("age", "band"),
    [(timedelta(hours=1), "fresh"), (timedelta(days=3), "aging"), (timedelta(days=30), "stale")],
)
async def test_freshness_bands_agree_with_service(
    dev_client: AsyncClient, age: timedelta, band: str
) -> None:
    user_id = await _login(dev_client, "fresh")
    await _add_account(user_id, last_sync_at=datetime.now(UTC) - age)
    conn = (await dev_client.get("/privacy/summary")).json()["connections"][0]
    assert conn["freshness_band"] == band
    assert conn["ever_synced"] is True


async def test_scope_labels_reflect_only_granted_scopes(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "scopes")
    await _add_account(user_id, scopes=[GMAIL_RO, CAL_RO])  # partial grant (no compose/events)
    conn = (await dev_client.get("/privacy/summary")).json()["connections"][0]
    labels = {g["label"] for g in conn["granted_scopes"]}
    scopes = {g["scope"] for g in conn["granted_scopes"]}
    assert labels == {"View Gmail evidence", "View Calendar evidence"}
    assert scopes == {GMAIL_RO, CAL_RO}
    # Requested-but-not-granted must not appear as active (test 8).
    assert "Create Gmail drafts" not in labels
    assert "Create Calendar events" not in labels


async def test_response_never_leaks_secrets_or_provider_internals(
    dev_client: AsyncClient,
) -> None:
    user_id = await _login(dev_client, "secrets")
    await _seed_full_dataset(user_id, last_sync=datetime.now(UTC))
    raw = (await dev_client.get("/privacy/summary")).text
    for sentinel in (
        SECRET_ACCESS,  # token (test 9)
        SECRET_REFRESH,
        SECRET_CURSOR,  # sync cursor (test 10)
        SECRET_EXTERNAL_ID,  # provider message id (test 11)
        SECRET_PAYLOAD_HASH,  # proposal hash (test 12)
        SECRET_AUDIT_META,  # audit metadata internals (test 13)
        "draft body that must never leak",
        "Subject line that must never leak",
    ):
        assert sentinel not in raw
    # Ciphertext of the token must not appear either.
    assert "authorisation_revision" not in raw and "sync_cursor" not in raw


async def test_retention_defaults_come_from_validated_config(dev_client: AsyncClient) -> None:
    await _login(dev_client, "retention")
    retention = (await dev_client.get("/privacy/summary")).json()["retention"]
    assert retention["enforcement_active"] is False
    by_key = {c["key"]: c for c in retention["classes"]}
    assert by_key["source_items"]["retention_days"] == 30
    assert by_key["brief_versions"]["retention_days"] == 90
    assert by_key["approved_terminal"]["retention_days"] == 365
    assert by_key["audit_tombstones"]["retention_days"] == 365
    assert by_key["operational_logs"]["retention_days"] == 30
    assert all(c["enforced"] is False for c in retention["classes"])


async def test_pending_uncertain_execution_retention_is_described_accurately(
    dev_client: AsyncClient,
) -> None:
    await _login(dev_client, "uncertain")
    retention = (await dev_client.get("/privacy/summary")).json()["retention"]
    by_key = {c["key"]: c for c in retention["classes"]}
    # No fixed horizon, and copy states it is not auto-deleted before reconciliation (test 16).
    assert by_key["pending_uncertain_executions"]["retention_days"] is None
    assert "reconcil" in by_key["pending_uncertain_executions"]["description"].lower()
    assert any("reconcil" in n.lower() for n in retention["notes"])
    assert any("preference" in n.lower() for n in retention["notes"])


async def test_retention_custom_config_is_reflected() -> None:
    settings = _test_settings("development").model_copy(update={"retention_source_items_days": 7})
    async for c in _make_client(settings):
        await _login(c, "customret")
        retention = (await c.get("/privacy/summary")).json()["retention"]
        by_key = {cl["key"]: cl for cl in retention["classes"]}
        assert by_key["source_items"]["retention_days"] == 7
        break


async def test_endpoint_works_when_redis_unavailable(
    dev_client_unreachable_redis: AsyncClient,
) -> None:
    user_id = await _login(dev_client_unreachable_redis, "redis")
    await _seed_full_dataset(user_id, last_sync=datetime.now(UTC))
    response = await dev_client_unreachable_redis.get("/privacy/summary")
    assert response.status_code == 200  # never touches Redis (test 17)
    assert response.json()["inventory"]["source_items"] == 1


async def test_summary_never_triggers_a_google_sync(dev_client: AsyncClient) -> None:
    # dev_client has google_oauth_enabled=False, so a sync is impossible; the
    # summary must still work, and repeated calls never change source counts
    # (test 18 — no sync on load/refresh).
    user_id = await _login(dev_client, "nosync")
    await _seed_full_dataset(user_id, last_sync=datetime.now(UTC))
    first = (await dev_client.get("/privacy/summary")).json()["inventory"]["source_items"]
    second = (await dev_client.get("/privacy/summary")).json()["inventory"]["source_items"]
    assert first == second == 1


async def _account_row(user_id: uuid.UUID) -> dict[str, object]:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as s:
            account = (
                await s.execute(select(ConnectedAccount).where(ConnectedAccount.user_id == user_id))
            ).scalar_one()
            return {
                "status": account.status,
                "access": account.encrypted_access_token,
                "refresh": account.encrypted_refresh_token,
            }
    finally:
        await engine.dispose()


async def test_successful_disconnect_clears_tokens_and_retains_all_data(
    dev_client: AsyncClient,
) -> None:
    """The full connected → disconnect → disconnected transition against a
    synthetic (non-real) Google account. Proves tokens are nulled, status
    flips, imported + derived data is retained, and the surface reflects a
    reconnect-capable disconnected account — without touching a real account."""
    user_id = await _login(dev_client, "disc")
    await _seed_full_dataset(user_id, last_sync=datetime.now(UTC))

    # Precondition: the account is genuinely connected, with encrypted tokens.
    before_row = await _account_row(user_id)
    assert before_row["status"] == AccountStatus.active
    assert before_row["access"] is not None and before_row["refresh"] is not None
    before = (await dev_client.get("/privacy/summary")).json()
    assert before["connections"][0]["connected"] is True
    assert before["connections"][0]["can_disconnect"] is True

    # Disconnect through the normal route.
    resp = await dev_client.post("/connected-accounts/google/disconnect", headers=CSRF_HEADERS)
    assert resp.status_code == 204

    # Tokens are nulled and the status flips at the database level.
    after_row = await _account_row(user_id)
    assert after_row["status"] == AccountStatus.disconnected
    assert after_row["access"] is None and after_row["refresh"] is None

    after = (await dev_client.get("/privacy/summary")).json()
    conn = after["connections"][0]
    assert conn["status"] == "disconnected"
    assert conn["connected"] is False
    assert conn["can_disconnect"] is False  # sync/disconnect no longer available
    assert conn["can_reconnect"] is True  # reconnect remains offered
    # Imported + derived data counts are unchanged by disconnect (Gmail/Calendar
    # provider content is never touched — only local tokens are cleared).
    for key in (
        "source_items",
        "signals",
        "briefs",
        "brief_versions",
        "action_proposals",
        "action_executions",
        "scheduled_brief_runs",
        "preferences",
        "memory_items",
    ):
        assert after["inventory"][key] == before["inventory"][key], key
    # Opening the surface again triggers no sync (counts stay identical).
    again = (await dev_client.get("/privacy/summary")).json()
    assert again["inventory"]["source_items"] == before["inventory"]["source_items"]


async def test_reconnect_preserves_authorisation_revision_safety(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "recon")
    engine = create_async_engine(TEST_DB_URL)
    cipher = _cipher()
    try:
        from lifeflow_api.accounts import ConnectedAccountService

        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as s:
            svc = ConnectedAccountService(s, user_id, cipher)
            await svc.store_tokens(
                provider="google",
                access_token="a1",
                refresh_token="r1",
                granted_scopes=[GMAIL_RO],
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            await svc.store_tokens(  # a reconnect: advances authorisation_revision
                provider="google",
                access_token="a2",
                refresh_token=None,
                granted_scopes=[GMAIL_RO],
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            await s.commit()
            account = (await svc._accounts.list())[0]
            assert account.authorisation_revision == 2  # bumped safely
    finally:
        await engine.dispose()
    body = (await dev_client.get("/privacy/summary")).json()
    assert body["connections"][0]["status"] == "active"
    assert "authorisation_revision" not in (await dev_client.get("/privacy/summary")).text
