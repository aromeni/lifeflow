"""Stage 11A Phase 2 (docs/delivery/stage-11a-phase-2-plan.md): extends
`test_google_token_service.py::test_concurrent_refresh_is_serialised_by_the_row_lock`
(one round, two callers) to the contract's required 10 concurrency rounds of
5 simultaneous callers each — real PostgreSQL row lock, stub OAuth transport
(never real network), a fresh account per round so no round can interfere
with another.
"""

import asyncio
import base64
import os
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL
from tests.test_google_token_service import NOW, _seed_google_account, _StubOAuthClient

from lifeflow_api.accounts import GoogleTokenService
from lifeflow_api.google.oauth import GoogleTokenResponse
from lifeflow_api.security.token_cipher import AesGcmTokenCipher

pytestmark = pytest.mark.integration

CONCURRENT_CALLERS = 5
ROUNDS = 10


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


@pytest.fixture
def cipher() -> AesGcmTokenCipher:
    return AesGcmTokenCipher(base64.b64encode(os.urandom(32)).decode(), "test-1")


async def _one_round(session: AsyncSession, cipher_: AesGcmTokenCipher, round_index: int) -> None:
    user = await _seed_google_account(
        session, cipher_, expires_at=NOW + timedelta(seconds=30), refresh_token=f"r-{round_index}"
    )
    await session.commit()

    call_counter = {"n": 0}
    tokens_seen: list[str] = []

    async def refresh_once() -> None:
        engine = create_async_engine(TEST_DB_URL)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as racing:
                oauth = _StubOAuthClient(
                    GoogleTokenResponse(
                        access_token=f"access-round{round_index}",
                        refresh_token=None,
                        expires_in=3600,
                        scope="a",
                        id_token=None,
                    )
                )
                service = GoogleTokenService(
                    racing,
                    user.id,
                    cipher_,
                    oauth,
                    client_id="cid",
                    client_secret="secret",  # pragma: allowlist secret
                    now_factory=lambda: NOW,
                )
                token = await service.get_valid_access_token("google")
                call_counter["n"] += oauth.calls
                tokens_seen.append(token)
                await racing.commit()
        finally:
            await engine.dispose()

    await asyncio.gather(*(refresh_once() for _ in range(CONCURRENT_CALLERS)))

    assert call_counter["n"] == 1, (
        f"round {round_index}: exactly one refresh must win, got {call_counter['n']}"
    )
    assert len(set(tokens_seen)) == 1, f"round {round_index}: every caller must see the same token"


async def test_ten_rounds_of_five_concurrent_refreshes_never_double_refresh(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    for round_index in range(ROUNDS):
        await _one_round(session, cipher, round_index)
