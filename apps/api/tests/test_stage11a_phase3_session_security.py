"""Stage 11A Phase 3 (S11A-P3-009/010) — the two session-security edge
cases the Phase 3 audit found missing from `test_auth_api.py`'s existing
tampered-signature coverage: a session-expiry boundary and a malformed
(not merely bit-flipped) cookie value.

Both use a fixed, known `session_secret` (rather than the ephemeral
per-instance secret `_session_secret()` otherwise generates) so the test
can independently construct a validly-signed-but-expired cookie with
`itsdangerous`, matching exactly what `SessionMiddleware` builds internally.
"""

import base64
import json
import os
import uuid
from base64 import b64encode
from collections.abc import AsyncIterator

import itsdangerous
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from tests.conftest import CSRF_HEADERS, TEST_DB_URL

from lifeflow_api.config import Settings
from lifeflow_api.main import create_app

pytestmark = pytest.mark.integration

FIXED_SESSION_SECRET = "stage11a-phase3-fixed-test-session-secret"  # pragma: allowlist secret
SESSION_MAX_AGE_SECONDS = 60 * 60 * 8


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="development",
        log_level="WARNING",
        database_url=TEST_DB_URL,
        token_key=base64.b64encode(os.urandom(32)).decode(),
        token_key_id="test-1",
        session_secret=FIXED_SESSION_SECRET,
    )


@pytest.fixture
async def fixed_secret_client() -> AsyncIterator[AsyncClient]:
    app = create_app(_settings())
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


class _AgedTimestampSigner(itsdangerous.TimestampSigner):
    """Signs with an attacker-uncontrollable, caller-chosen timestamp, to
    deterministically produce an already-expired cookie without waiting or
    patching the process-wide clock."""

    def __init__(self, secret_key: str, *, timestamp: int) -> None:
        super().__init__(secret_key)
        self._fixed_timestamp = timestamp

    def get_timestamp(self) -> int:
        return self._fixed_timestamp


def _signed_session_cookie(*, user_id: uuid.UUID, timestamp: int) -> str:
    payload = b64encode(json.dumps({"user_id": str(user_id)}).encode("utf-8"))
    signer = _AgedTimestampSigner(FIXED_SESSION_SECRET, timestamp=timestamp)
    return signer.sign(payload).decode("utf-8")


async def test_session_expiry_boundary(fixed_secret_client: AsyncClient) -> None:
    """S11A-P3-010: a session signed one second before the 8h boundary is
    still valid; a session signed one second past it is not — proving the
    server enforces `max_age`, not merely trusting an unexpired-looking
    signature forever."""
    login = await fixed_secret_client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
    assert login.status_code == 200
    user_id = uuid.UUID(login.json()["user_id"])

    now = int(itsdangerous.TimestampSigner(FIXED_SESSION_SECRET).get_timestamp())

    still_valid_cookie = _signed_session_cookie(
        user_id=user_id, timestamp=now - (SESSION_MAX_AGE_SECONDS - 1)
    )
    fixed_secret_client.cookies.set("lifeflow_session", still_valid_cookie)
    still_valid = await fixed_secret_client.get("/me")
    assert still_valid.status_code == 200

    expired_cookie = _signed_session_cookie(
        user_id=user_id, timestamp=now - (SESSION_MAX_AGE_SECONDS + 1)
    )
    fixed_secret_client.cookies.set("lifeflow_session", expired_cookie)
    expired = await fixed_secret_client.get("/me")
    assert expired.status_code == 401
    assert expired.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize(
    "garbage_value",
    [
        "not-a-valid-itsdangerous-cookie-at-all",
        "",
        "....",
        "a" * 500,
        "\x00\x01\x02binary-garbage",
        "'; DROP TABLE users; --",
    ],
)
async def test_malformed_non_tampered_cookie_is_rejected_safely(
    dev_client: AsyncClient, garbage_value: str
) -> None:
    """S11A-P3-009: a cookie that was never a validly-signed value in the
    first place (not a bit-flip of a real one) must be rejected the same
    way an expired/tampered one is — 401, no 500, no internals disclosed —
    across 5 distinct malformed shapes including empty, oversized, binary,
    and SQL-injection-shaped content."""
    dev_client.cookies.set("lifeflow_session", garbage_value)
    response = await dev_client.get("/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
    # No stack trace or internal exception detail anywhere in the body.
    assert "Traceback" not in response.text
    assert "itsdangerous" not in response.text
