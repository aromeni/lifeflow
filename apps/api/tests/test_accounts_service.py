"""ConnectedAccountService: tokens are encrypted before storage (T1)."""

import base64
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL

from lifeflow_api.accounts import ConnectedAccountService
from lifeflow_api.models import AccountStatus, User
from lifeflow_api.security.token_cipher import AesGcmTokenCipher

pytestmark = pytest.mark.integration

ACCESS_TOKEN = "ya29.plaintext-access-token"  # pragma: allowlist secret
REFRESH_TOKEN = "1//plaintext-refresh-token"  # pragma: allowlist secret


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.commit()
    await engine.dispose()


@pytest.fixture
def cipher() -> AesGcmTokenCipher:
    return AesGcmTokenCipher(base64.b64encode(os.urandom(32)).decode(), "test-1")


@pytest.fixture
async def service(session: AsyncSession, cipher: AesGcmTokenCipher) -> ConnectedAccountService:
    user = User(email="carol@example.test", display_name="Carol")
    session.add(user)
    await session.flush()
    return ConnectedAccountService(session, user.id, cipher)


async def _store(service: ConnectedAccountService) -> None:
    await service.store_tokens(
        provider="google",
        access_token=ACCESS_TOKEN,
        refresh_token=REFRESH_TOKEN,
        granted_scopes=["gmail.readonly"],
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


async def test_no_plaintext_token_reaches_the_database(
    session: AsyncSession, service: ConnectedAccountService
) -> None:
    await _store(service)
    row = (await session.execute(text("SELECT * FROM connected_accounts"))).mappings().one()
    row_dump = str(dict(row))
    assert ACCESS_TOKEN not in row_dump
    assert REFRESH_TOKEN not in row_dump
    assert row["encrypted_access_token"].startswith("v2:test-1:")


async def test_tokens_round_trip_through_the_cipher(service: ConnectedAccountService) -> None:
    await _store(service)
    assert await service.get_access_token("google") == ACCESS_TOKEN


async def test_storing_again_updates_rather_than_duplicates(
    session: AsyncSession, service: ConnectedAccountService
) -> None:
    await _store(service)
    await _store(service)
    count = (await session.execute(text("SELECT count(*) FROM connected_accounts"))).scalar()
    assert count == 1


async def test_disconnect_drops_tokens_and_audits(
    session: AsyncSession, service: ConnectedAccountService
) -> None:
    await _store(service)
    assert await service.disconnect("google") is True

    row = (await session.execute(text("SELECT * FROM connected_accounts"))).mappings().one()
    assert row["encrypted_access_token"] is None
    assert row["encrypted_refresh_token"] is None
    assert row["status"] == AccountStatus.disconnected

    events = (await session.execute(text("SELECT event_type FROM audit_events"))).scalars().all()
    assert "account.connected" in events
    assert "account.disconnected" in events
