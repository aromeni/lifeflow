"""Stage 11A Phase 3 (S11A-P3-014) — token sentinel lifecycle search.

Existing coverage already proves plaintext never reaches the database
column (`test_no_plaintext_token_reaches_the_database`) and that the
ciphertext envelope round-trips correctly (`test_token_cipher.py`). What
the Phase 3 audit found missing is an end-to-end search: a distinctive,
never-reused sentinel token value is created, refreshed, disconnected and
the owning account deleted, and — after every stage — every storage
surface (every content-bearing DB table, the real Redis instance, and
captured structured logs) is searched for the raw sentinel. It must never
appear anywhere except inside the one encrypted-envelope column, and even
there only until disconnect/deletion clears it.

Run for 5 lifecycle cycles (the required repetition count), each with a
fresh, unique sentinel pair so no cycle's assertions can be satisfied by
another cycle's leftover state.
"""

import io
import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL

from lifeflow_api.accounts import ConnectedAccountService, GoogleTokenService
from lifeflow_api.deletion import confirm_operation, create_account_deletion_preview, run_operation
from lifeflow_api.deletion_ops import CONFIRM_ACCOUNT
from lifeflow_api.google.oauth import GoogleTokenResponse
from lifeflow_api.logging_setup import JsonFormatter
from lifeflow_api.models import User
from lifeflow_api.retention import RetentionHorizons
from lifeflow_api.security.token_cipher import AesGcmTokenCipher

pytestmark = pytest.mark.integration

REDIS_URL = "redis://localhost:6380/0"
_TEXT_SEARCH_TABLES = ("connected_accounts", "audit_events", "users")
_HORIZONS = RetentionHorizons(
    source_items_days=30,
    brief_versions_days=90,
    unapproved_proposals_days=90,
    scheduled_runs_days=90,
    memory_evidence_days=90,
)


@pytest.fixture
def cipher() -> AesGcmTokenCipher:
    import base64
    import os

    return AesGcmTokenCipher(base64.b64encode(os.urandom(32)).decode(), "test-1")


class _StubOAuthClient:
    def __init__(self, response: GoogleTokenResponse) -> None:
        self.calls = 0
        self._response = response

    async def refresh_access_token(
        self, *, client_id: str, client_secret: str, refresh_token: str
    ) -> GoogleTokenResponse:
        self.calls += 1
        return self._response

    async def revoke_token(self, *, token: str) -> bool:
        return True


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


async def _assert_sentinel_absent_from_database(session: AsyncSession, sentinel: str) -> None:
    for table in _TEXT_SEARCH_TABLES:
        result = await session.execute(
            text(f"SELECT count(*) FROM {table} WHERE to_jsonb({table}.*)::text ILIKE :pattern"),
            {"pattern": f"%{sentinel}%"},
        )
        count = result.scalar_one()
        assert count == 0, f"sentinel leaked into {table}"


async def _assert_sentinel_absent_from_redis(sentinel: str) -> None:
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        async for key in client.scan_iter(match="*", count=200):
            key_type = await client.type(key)
            if key_type == "string":
                value = await client.get(key)
            elif key_type == "hash":
                value = json.dumps(await client.hgetall(key))
            else:
                continue
            assert sentinel not in (value or ""), f"sentinel leaked into redis key {key!r}"
    finally:
        await client.aclose()


def _assert_sentinel_absent_from_logs(captured: str, sentinel: str) -> None:
    assert sentinel not in captured, "sentinel leaked into structured logs"


@pytest.mark.parametrize("cycle", range(5))
async def test_token_sentinel_never_leaks_across_full_credential_lifecycle(
    session: AsyncSession, cipher: AesGcmTokenCipher, cycle: int
) -> None:
    sentinel_access = f"SENTINEL-ACCESS-TOKEN-{uuid.uuid4()}"  # pragma: allowlist secret
    sentinel_refresh = f"SENTINEL-REFRESH-TOKEN-{uuid.uuid4()}"  # pragma: allowlist secret
    sentinel_refreshed_access = (
        f"SENTINEL-REFRESHED-ACCESS-{uuid.uuid4()}"  # pragma: allowlist secret
    )

    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    previous_level = root_logger.level
    root_logger.setLevel(logging.DEBUG)

    try:
        user = User(email=f"sentinel-{uuid.uuid4()}@example.com", display_name="Sentinel")
        session.add(user)
        await session.flush()

        # Stage 1: create.
        await ConnectedAccountService(session, user.id, cipher).store_tokens(
            provider="google",
            access_token=sentinel_access,
            refresh_token=sentinel_refresh,
            granted_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            expires_at=datetime.now(UTC) - timedelta(minutes=1),  # already expired
        )
        await session.flush()
        await _assert_sentinel_absent_from_database(session, sentinel_access)
        await _assert_sentinel_absent_from_database(session, sentinel_refresh)
        await _assert_sentinel_absent_from_redis(sentinel_access)
        await _assert_sentinel_absent_from_redis(sentinel_refresh)

        # Stage 2: refresh (the expired token forces a real refresh call).
        stub = _StubOAuthClient(
            GoogleTokenResponse(
                access_token=sentinel_refreshed_access,
                refresh_token=None,
                expires_in=3600,
                scope="https://www.googleapis.com/auth/gmail.readonly",
                id_token=None,
            )
        )
        token_service = GoogleTokenService(
            session,
            user.id,
            cipher,
            stub,
            client_id="client",
            client_secret="secret",  # pragma: allowlist secret
        )
        returned = await token_service.get_valid_access_token("google")
        assert returned == sentinel_refreshed_access
        assert stub.calls == 1
        await _assert_sentinel_absent_from_database(session, sentinel_refreshed_access)
        await _assert_sentinel_absent_from_redis(sentinel_refreshed_access)

        # Stage 3: disconnect.
        await ConnectedAccountService(session, user.id, cipher).disconnect("google")
        await session.flush()
        await _assert_sentinel_absent_from_database(session, sentinel_refreshed_access)

        # Stage 4: full account deletion.
        op = await create_account_deletion_preview(
            session, user, now=datetime.now(UTC), ttl_minutes=30
        )
        confirmed = await confirm_operation(
            session,
            user,
            op.id,
            expected_version=op.version,
            phrase=CONFIRM_ACCOUNT,
            now=datetime.now(UTC),
            preview_ttl_minutes=30,
        )
        await session.commit()
        await run_operation(
            session,
            confirmed.id,
            now=datetime.now(UTC),
            horizons=_HORIZONS,
            batch_size=10,
            max_attempts=3,
        )
        await session.commit()

        for sentinel in (sentinel_access, sentinel_refresh, sentinel_refreshed_access):
            await _assert_sentinel_absent_from_database(session, sentinel)
            await _assert_sentinel_absent_from_redis(sentinel)
    finally:
        root_logger.removeHandler(handler)
        root_logger.setLevel(previous_level)
        captured_logs = log_capture.getvalue()
        for sentinel in (sentinel_access, sentinel_refresh, sentinel_refreshed_access):
            _assert_sentinel_absent_from_logs(captured_logs, sentinel)
