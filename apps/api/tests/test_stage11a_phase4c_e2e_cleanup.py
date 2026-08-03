"""Phase 4C regression: fake-provider E2E credentials never survive a run."""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from scripts import e2e_google_support
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL

from lifeflow_api.models import ConnectedAccount, User

pytestmark = pytest.mark.integration


async def test_resilience_fixture_cleanup_removes_only_its_dedicated_key_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIFEFLOW_E2E", "1")
    monkeypatch.setattr(e2e_google_support, "DSN", TEST_DB_URL.replace("+asyncpg", ""))

    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        fixture_user = User(email=f"fixture-{uuid.uuid4()}@example.com", display_name="Fixture")
        unrelated_user = User(
            email=f"unrelated-{uuid.uuid4()}@example.com", display_name="Unrelated"
        )
        session.add_all([fixture_user, unrelated_user])
        await session.flush()
        unrelated = ConnectedAccount(
            user_id=unrelated_user.id,
            provider="google",
            encrypted_access_token="unrelated-synthetic-envelope",
            access_token_key_id="another-test-key",
        )
        session.add(unrelated)
        await session.commit()
        fixture_user_id = fixture_user.id
        unrelated_user_id = unrelated_user.id
        unrelated_account_id = unrelated.id
    await engine.dispose()

    fixture_account_id = await e2e_google_support.seed_account(fixture_user_id)
    assert await e2e_google_support.cleanup_accounts() == 1

    conn = await asyncpg.connect(dsn=TEST_DB_URL.replace("+asyncpg", ""))
    try:
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM connected_accounts WHERE id = $1",
                fixture_account_id,
            )
            == 0
        )
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM connected_accounts WHERE id = $1",
                unrelated_account_id,
            )
            == 1
        )
    finally:
        await conn.execute(
            "DELETE FROM connected_accounts WHERE id = ANY($1::uuid[])",
            [fixture_account_id, unrelated_account_id],
        )
        await conn.execute(
            "DELETE FROM users WHERE id = ANY($1::uuid[])",
            [fixture_user_id, unrelated_user_id],
        )
        await conn.close()
