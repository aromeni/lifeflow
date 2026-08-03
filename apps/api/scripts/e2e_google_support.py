"""Playwright E2E support for the Stage 9 Delivery Phase 5 resilience
journeys (§20).

Seeds a `ConnectedAccount(provider="google")` row directly, bypassing the
real OAuth browser consent flow entirely — the journeys below are about
Google *transport* resilience (timeouts/retries/uncertain writes), not
OAuth, so there is nothing to gain from driving a real consent screen, and
doing so would require a much larger, riskier piece of test infrastructure.
The encrypted access token is a synthetic, obviously-fake string; the fake
Google server (`lifeflow_api.testing.fake_google_server`) never validates it
at all. Follows the exact same safety pattern as
`e2e_deletion_support.py`: an explicit `LIFEFLOW_E2E=1` marker plus a strict
local-host + known-dev/test-database allowlist, so this can never touch a
production or staging database.

`seed-draft-source` additionally seeds one `SourceItem` (email, inbox, a
strong explicit-request cue, no scheduling/deadline cue) referencing that
same Google account, deterministically producing exactly one
`create_gmail_draft` `ActionProposal` in `real` execution mode the next time
a brief is generated — the exact recipe `demo/data/v1/emails.json`'s
`em-001` fixture already proves deterministically produces this action
type (`detectors.py::detect_requests`, `proposal_composition.py::_draft_candidates`).

Usage:
    uv run python scripts/e2e_google_support.py seed-account <user_id>
    uv run python scripts/e2e_google_support.py seed-draft-source <user_id>
    uv run python scripts/e2e_google_support.py cleanup-accounts
"""

import asyncio
import base64
import hashlib
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lifeflow_api.google_scopes import CONNECTOR_SCOPES
from lifeflow_api.security.token_cipher import AesGcmTokenCipher

_DEFAULT_DSN = "postgresql://lifeflow:lifeflow@localhost:5433/lifeflow"  # pragma: allowlist secret
DSN = os.environ.get("DATABASE_URL", _DEFAULT_DSN).replace("+asyncpg", "")

_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1", "db", "postgres"}
_ALLOWED_DB_NAMES = {"lifeflow", "lifeflow_test", "lifeflow_e2e"}

# A fixed, obviously-fictional 32-byte key, base64-encoded — never a real
# secret. Must match TOKEN_KEY on the dedicated resilience-journey API
# process (see playwright.resilience.config.ts) so it can decrypt what this
# script encrypts.
_FAKE_TOKEN_KEY = base64.b64encode(
    b"e2e-resilience-fake-token-key-32"
).decode()  # pragma: allowlist secret
_FAKE_TOKEN_KEY_ID = "e2e-resilience-1"  # noqa: S105 -- key *identifier*, not a secret
_FAKE_ACCESS_TOKEN = "fake-access-token-never-a-real-google-credential"  # noqa: S105 -- synthetic fixture


def _assert_safe_target() -> None:
    if os.environ.get("LIFEFLOW_E2E") != "1":
        raise SystemExit(
            "refusing to run: LIFEFLOW_E2E=1 is required (this seeds test fixtures only)"
        )
    parsed = urlparse(DSN)
    host = (parsed.hostname or "").lower()
    name = (parsed.path or "").lstrip("/").lower()
    if host not in _ALLOWED_HOSTS:
        raise SystemExit(f"refusing non-local database host {host!r}")
    if name not in _ALLOWED_DB_NAMES:
        raise SystemExit(f"refusing unknown database {name!r} (not a known dev/test database)")


async def _connect() -> asyncpg.Connection:
    _assert_safe_target()
    return await asyncpg.connect(dsn=DSN)


async def seed_account(user_id: uuid.UUID) -> uuid.UUID:
    cipher = AesGcmTokenCipher(_FAKE_TOKEN_KEY, _FAKE_TOKEN_KEY_ID)
    account_id = uuid.uuid4()
    # Stage 11A Phase 4A: encryption context binds this envelope to this
    # exact account/user/provider/field — must match what the app itself
    # would derive (security/credential_context.py) or a real decrypt of
    # this fixture through the application would fail authentication.
    context = f"{account_id}:{user_id}:google:access_token"
    encrypted_access_token = cipher.encrypt(_FAKE_ACCESS_TOKEN, context=context)
    conn = await _connect()
    try:
        await conn.execute(
            "INSERT INTO connected_accounts "
            "(id, user_id, provider, encrypted_access_token, encrypted_refresh_token, "
            "granted_scopes, expires_at, status, authorisation_revision, sync_cursors, "
            "last_sync_at, access_token_key_id, refresh_token_key_id) "
            "VALUES ($1, $2, 'google', $3, NULL, $4, $5, 'active', 1, '{}', NULL, $6, NULL)",
            account_id,
            user_id,
            encrypted_access_token,
            json.dumps(list(CONNECTOR_SCOPES)),
            datetime.now(UTC) + timedelta(days=365),
            _FAKE_TOKEN_KEY_ID,
        )
    finally:
        await conn.close()
    return account_id


async def seed_draft_source(user_id: uuid.UUID) -> None:
    conn = await _connect()
    try:
        account_id = await conn.fetchval(
            "SELECT id FROM connected_accounts WHERE user_id = $1 AND provider = 'google'",
            user_id,
        )
        if account_id is None:
            raise SystemExit("no google connected_accounts row for this user — seed-account first")
        body_preview = (
            "Hi, could you confirm the final numbers for the Q3 report by Friday? Thanks, Dana."
        )
        metadata = {
            "folder": "inbox",
            "sender_name": "Dana Whitfield",
            "recipients": ["demo@lifeflow.local"],
            "thread_id": "t-seed-thread",
            "body_preview": body_preview,
            "list_unsubscribe": None,
        }
        external_id = f"seed-gmail-draft-{uuid.uuid4()}"
        await conn.execute(
            "INSERT INTO source_items "
            "(id, user_id, source_type, external_id, source_account_id, title, "
            "sender_or_organiser, occurred_at, metadata_json, content_fingerprint, created_at) "
            "VALUES ($1, $2, 'email', $3, $4, $5, $6, $7, $8, $9, $7)",
            uuid.uuid4(),
            user_id,
            external_id,
            account_id,
            "Q3 report — can you confirm by Friday?",
            "dana@northgate-consulting.example",
            datetime.now(UTC) - timedelta(days=1),
            json.dumps(metadata),
            hashlib.sha256(external_id.encode()).hexdigest(),
        )
    finally:
        await conn.close()


async def cleanup_accounts() -> int:
    """Delete only credential rows created with the fixed resilience-test key.

    The resilience suite uses the shared local development database so its
    browser journeys can exercise real process restarts and dependency
    outages. Leaving its encrypted fixture rows behind makes the real
    preconnection gate correctly fail on an unknown key after the suite.
    Selecting by the dedicated, non-secret fixture key id keeps cleanup
    closed to rows this helper created; foreign keys minimise or cascade
    test references according to the application's existing schema.
    """

    conn = await _connect()
    try:
        result = await conn.execute(
            "DELETE FROM connected_accounts "
            "WHERE access_token_key_id = $1 OR refresh_token_key_id = $1",
            _FAKE_TOKEN_KEY_ID,
        )
    finally:
        await conn.close()
    return int(result.rsplit(" ", 1)[-1])


async def _main() -> None:
    command = sys.argv[1]
    if command == "cleanup-accounts" and len(sys.argv) == 2:
        cleaned = await cleanup_accounts()
        print(f"cleaned synthetic resilience accounts: {cleaned}")
        return
    if len(sys.argv) != 3:
        raise SystemExit("seed commands require exactly one user id")
    user_id = uuid.UUID(sys.argv[2])
    if command == "seed-account":
        await seed_account(user_id)
    elif command == "seed-draft-source":
        await seed_draft_source(user_id)
    else:
        raise SystemExit(f"unknown command {command!r}")


if __name__ == "__main__":
    asyncio.run(_main())
