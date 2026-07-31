"""Stage 11A Phase 3 (S11A-P3-017/018/019/021) — secret rotation rehearsal.

The threat model documented encryption-key rotation as "manual procedure in
MVP, automated rotation post-MVP" but no tooling or test had ever actually
exercised what that manual procedure requires. This is genuinely new
coverage the Phase 3 audit found missing entirely. Each secret is
rehearsed against real application code (never a real production secret,
never a live provider) and its rotation capability is classified honestly:

- `SESSION_SECRET` — restart-only, forced invalidation. Rotating it and
  restarting (a fresh `create_app()` instance, in-process here) makes every
  session signed under the old secret unverifiable; new sessions issue
  correctly under the new one. No dual-key grace period exists or is
  needed — sessions are short-lived and re-issued by simply logging in
  again.
- `TOKEN_KEY`/`TOKEN_KEY_ID` — **no rotation capability exists today.**
  `AesGcmTokenCipher` holds exactly one active key; `decrypt()` raises
  `TokenCipherError` for any envelope whose `key_id` does not match the
  instance's own. Application wiring (`main.py`, `worker_app.py`)
  constructs exactly one cipher instance from settings — there is no
  dual-key registry that would let a caller decrypt-under-old,
  re-encrypt-under-new. This test proves that gap directly rather than
  asserting a capability that does not exist; see defect-register.md.
- `RATE_LIMIT_KEY_SECRET` — rotation is safe by construction: a new secret
  simply produces a new HMAC digest for the same raw subject, which is
  indistinguishable from a normal bucket expiring. No stored state becomes
  unreadable or corrupted; the fail-open behaviour is completely unaffected.
"""

import base64
import os
import uuid
from collections.abc import AsyncIterator

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from tests.conftest import CSRF_HEADERS, TEST_DB_URL

from lifeflow_api.config import Settings
from lifeflow_api.main import create_app
from lifeflow_api.rate_limit_policy import RateLimitSubjectType
from lifeflow_api.rate_limiter import hash_subject
from lifeflow_api.security.token_cipher import AesGcmTokenCipher, TokenCipherError

pytestmark = pytest.mark.integration


def _settings(*, session_secret: str) -> Settings:
    return Settings(
        _env_file=None,
        environment="development",
        log_level="WARNING",
        database_url=TEST_DB_URL,
        token_key=base64.b64encode(os.urandom(32)).decode(),
        token_key_id="test-1",
        session_secret=session_secret,
    )


async def _client_for(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_session_secret_rotation_invalidates_old_sessions_and_issues_new_ones() -> None:
    old_secret = "stage11a-phase3-old-session-secret"  # pragma: allowlist secret
    new_secret = "stage11a-phase3-new-session-secret"  # pragma: allowlist secret

    old_client: AsyncClient | None = None
    async for c in _client_for(_settings(session_secret=old_secret)):
        old_client = c
        login = await c.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
        assert login.status_code == 200
        old_cookie = c.cookies.get("lifeflow_session")
        break
    assert old_client is not None
    assert old_cookie is not None

    # Rotation + restart, modelled as a fresh app instance under the new
    # secret — the same signer configuration a real process restart with a
    # changed SESSION_SECRET would produce.
    async for c in _client_for(_settings(session_secret=new_secret)):
        c.cookies.set("lifeflow_session", old_cookie)
        rejected = await c.get("/me")
        assert rejected.status_code == 401, "old-secret session must not survive rotation"

        fresh_login = await c.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
        assert fresh_login.status_code == 200
        accepted = await c.get("/me")
        assert accepted.status_code == 200, (
            "a freshly issued session must work under the new secret"
        )
        break


def test_token_cipher_key_rotation_has_no_dual_key_migration_path() -> None:
    """Honest gap, not a silent acceptance: encrypting under an old key and
    attempting to decrypt with a cipher configured only with the new key
    fails outright. There is no dual-key read path anywhere in the
    codebase for a caller to fall back to. A real rotation today would
    require a dedicated, currently-unbuilt re-encryption migration that
    decrypts every row under the old key before the old key is discarded."""
    old_key = base64.b64encode(os.urandom(32)).decode()
    new_key = base64.b64encode(os.urandom(32)).decode()

    old_cipher = AesGcmTokenCipher(old_key, "key-v1")
    new_cipher = AesGcmTokenCipher(new_key, "key-v2")

    sentinel = f"SENTINEL-ROTATION-TOKEN-{uuid.uuid4()}"  # pragma: allowlist secret
    envelope = old_cipher.encrypt(sentinel)

    with pytest.raises(TokenCipherError, match="No key available"):
        new_cipher.decrypt(envelope)

    # The only currently-correct rotation procedure: keep the old cipher
    # instance alive until every row has been re-encrypted under the new
    # one. This must be a deliberate migration step, never implicit.
    assert old_cipher.decrypt(envelope) == sentinel
    reencrypted = new_cipher.encrypt(old_cipher.decrypt(envelope))
    assert new_cipher.decrypt(reencrypted) == sentinel


def test_rate_limit_secret_rotation_only_changes_the_bucket_key_deterministically() -> None:
    """Rotating RATE_LIMIT_KEY_SECRET is safe by construction: the same
    raw subject simply maps to a new, unrelated digest — equivalent to a
    bucket expiring naturally, never a corruption or a cross-secret
    collision."""
    old_secret = "stage11a-phase3-old-rate-limit-secret"  # pragma: allowlist secret
    new_secret = "stage11a-phase3-new-rate-limit-secret"  # pragma: allowlist secret
    subject = "user-12345"

    old_digest = hash_subject(old_secret, RateLimitSubjectType.authenticated_user, subject)
    new_digest = hash_subject(new_secret, RateLimitSubjectType.authenticated_user, subject)

    assert old_digest != new_digest
    # Deterministic under a fixed secret — rotation is the only thing that
    # changes the digest, never nondeterminism in the hash itself.
    assert hash_subject(old_secret, RateLimitSubjectType.authenticated_user, subject) == old_digest
