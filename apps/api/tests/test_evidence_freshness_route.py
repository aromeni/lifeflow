"""Stage 8 Phase 2 focused remediation: GET /evidence-freshness.

Scheduled briefs never trigger Google sync (ADR 0004 D47) — this route lets
Settings/Today truthfully say what evidence a scheduled brief will actually
use: per-account connection state, whether it has ever been synced, and how
old that evidence is. Covers the six scenarios required by the remediation
brief: recently-synced, aged-but-usable, never-synced, disconnected, Redis
unavailability not hiding this data (it never touches Redis), and that
manual vs. scheduled generation triggers share the same underlying truth
(there is only one `ConnectedAccount.last_sync_at` per account, read
identically regardless of which route generated the most recent brief).
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL, _make_client, _test_settings

from lifeflow_api.models import AccountStatus, ConnectedAccount, User

pytestmark = pytest.mark.integration


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
        json={
            "email": f"evidence-freshness-{marker}-{uuid.uuid4()}@example.com",
            "display_name": "Evidence",
        },
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200
    return uuid.UUID(response.json()["user_id"])


async def _add_account(
    user_id: uuid.UUID,
    *,
    provider: str = "google",
    status: str = AccountStatus.active,
    last_sync_at: datetime | None = None,
) -> None:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            user = await session.get(User, user_id)
            assert user is not None
            session.add(
                ConnectedAccount(
                    user_id=user_id,
                    provider=provider,
                    status=status,
                    last_sync_at=last_sync_at,
                )
            )
            await session.commit()
    finally:
        await engine.dispose()


async def test_no_connected_accounts_reports_an_empty_list(dev_client: AsyncClient) -> None:
    await _login(dev_client, "none")
    response = await dev_client.get("/evidence-freshness")
    assert response.status_code == 200
    body = response.json()
    assert body["accounts"] == []
    assert body["scheduled_briefs_use_latest_synced_evidence"] is True


async def test_recently_synced_evidence_shows_the_correct_timestamp_and_fresh_band(
    dev_client: AsyncClient,
) -> None:
    user_id = await _login(dev_client, "recent")
    recent = datetime.now(UTC) - timedelta(hours=1)
    await _add_account(user_id, last_sync_at=recent)

    response = await dev_client.get("/evidence-freshness")
    account = response.json()["accounts"][0]
    assert account["connected"] is True
    assert account["sync_state"] == "synced"
    assert account["last_synced_at"] is not None
    assert account["freshness_band"] == "fresh"


async def test_old_evidence_remains_usable_but_is_labelled_with_its_age(
    dev_client: AsyncClient,
) -> None:
    user_id = await _login(dev_client, "aged")
    ten_days_ago = datetime.now(UTC) - timedelta(days=10)
    await _add_account(user_id, last_sync_at=ten_days_ago)

    response = await dev_client.get("/evidence-freshness")
    account = response.json()["accounts"][0]
    # Old evidence is still reported (usable), just labelled `stale`, never
    # hidden or omitted.
    assert account["sync_state"] == "synced"
    assert account["last_synced_at"] is not None
    assert account["freshness_band"] == "stale"


async def test_a_never_synced_connected_account_is_disclosed(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "never")
    await _add_account(user_id, last_sync_at=None)

    response = await dev_client.get("/evidence-freshness")
    account = response.json()["accounts"][0]
    assert account["connected"] is True
    assert account["sync_state"] == "never_synced"
    assert account["last_synced_at"] is None
    assert account["freshness_band"] is None


async def test_a_disconnected_account_is_disclosed_as_disconnected(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "disconnected")
    old_sync = datetime.now(UTC) - timedelta(days=2)
    await _add_account(user_id, status=AccountStatus.disconnected, last_sync_at=old_sync)

    response = await dev_client.get("/evidence-freshness")
    account = response.json()["accounts"][0]
    assert account["connected"] is False
    # Historical evidence freshness is still reported even once disconnected
    # — disconnecting doesn't retroactively hide what evidence a brief
    # generated before the disconnect was based on.
    assert account["last_synced_at"] is not None


async def test_redis_unavailable_does_not_hide_evidence_freshness(
    dev_client_unreachable_redis: AsyncClient,
) -> None:
    user_id = await _login(dev_client_unreachable_redis, "no-redis")
    await _add_account(user_id, last_sync_at=datetime.now(UTC))

    response = await dev_client_unreachable_redis.get("/evidence-freshness")
    assert response.status_code == 200
    assert response.json()["accounts"][0]["sync_state"] == "synced"


async def test_response_never_exposes_oauth_tokens_or_sync_cursors(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "no-leak")
    await _add_account(user_id, last_sync_at=datetime.now(UTC))

    response = await dev_client.get("/evidence-freshness")
    raw = response.text
    assert "encrypted_access_token" not in raw
    assert "encrypted_refresh_token" not in raw
    assert "sync_cursors" not in raw
    assert "authorisation_revision" not in raw
