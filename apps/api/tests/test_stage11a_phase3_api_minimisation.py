"""Stage 11A Phase 3 (S11A-P3-026) — API response field-name minimisation.

Every response in this codebase is already built through an explicit
Pydantic `response_model=`, so an encrypted-token field structurally cannot
serialise by accident (FastAPI filters to the declared schema). The Phase 3
audit found this was never asserted directly, though — this test seeds a
connected account with real encrypted ciphertext and a distinctive sentinel
plaintext, then inspects the *raw* JSON text of every route that could
plausibly touch a `ConnectedAccount` row, asserting the encrypted-column
field names never appear by name and the sentinel plaintext never appears
by value."""

import base64
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL

from lifeflow_api.accounts import ConnectedAccountService
from lifeflow_api.security.token_cipher import AesGcmTokenCipher

pytestmark = pytest.mark.integration

_FORBIDDEN_FIELD_NAMES = (
    "encrypted_access_token",
    "encrypted_refresh_token",
    "access_token",
    "refresh_token",
)


async def _login(client: AsyncClient, marker: str) -> uuid.UUID:
    response = await client.post(
        "/auth/dev-login",
        json={
            "email": f"api-minimisation-{marker}-{uuid.uuid4()}@example.com",
            "display_name": "API Minimisation",
        },
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200
    return uuid.UUID(response.json()["user_id"])


async def test_connected_accounts_response_never_exposes_token_fields_or_values(
    dev_client: AsyncClient,
) -> None:
    user_id = await _login(dev_client, "accounts")
    sentinel_access = f"SENTINEL-API-MIN-ACCESS-{uuid.uuid4()}"  # pragma: allowlist secret
    sentinel_refresh = f"SENTINEL-API-MIN-REFRESH-{uuid.uuid4()}"  # pragma: allowlist secret

    cipher = AesGcmTokenCipher(base64.b64encode(os.urandom(32)).decode(), "test-1")
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            await ConnectedAccountService(session, user_id, cipher).store_tokens(
                provider="google",
                access_token=sentinel_access,
                refresh_token=sentinel_refresh,
                granted_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            await session.commit()
    finally:
        await engine.dispose()

    response = await dev_client.get("/connected-accounts")
    assert response.status_code == 200
    raw_text = response.text

    for field_name in _FORBIDDEN_FIELD_NAMES:
        assert field_name not in raw_text, f"{field_name!r} leaked into /connected-accounts"
    assert sentinel_access not in raw_text
    assert sentinel_refresh not in raw_text

    body = response.json()
    assert body["accounts"][0]["provider"] == "google"
    assert set(body["accounts"][0].keys()) == {
        "provider",
        "status",
        "granted_scopes",
        "last_sync_at",
    }


async def test_privacy_summary_never_exposes_token_fields_or_values(
    dev_client: AsyncClient,
) -> None:
    user_id = await _login(dev_client, "privacy-summary")
    sentinel_access = f"SENTINEL-API-MIN-SUMMARY-ACCESS-{uuid.uuid4()}"  # pragma: allowlist secret

    cipher = AesGcmTokenCipher(base64.b64encode(os.urandom(32)).decode(), "test-1")
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            await ConnectedAccountService(session, user_id, cipher).store_tokens(
                provider="google",
                access_token=sentinel_access,
                refresh_token="refresh-sentinel",  # pragma: allowlist secret
                granted_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            await session.commit()
    finally:
        await engine.dispose()

    response = await dev_client.get("/privacy/summary")
    assert response.status_code == 200
    raw_text = response.text

    for field_name in _FORBIDDEN_FIELD_NAMES:
        assert field_name not in raw_text, f"{field_name!r} leaked into /privacy/summary"
    assert sentinel_access not in raw_text
    assert "authorisation_revision" not in raw_text
