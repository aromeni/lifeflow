"""Playwright E2E support for the Stage 9 Delivery Phase 2 destructive journeys.

Invoked from the browser spec via child_process to (a) seed a synthetic
connected account + imported data for a dev-login user, and (b) read back
owner-scoped database facts for post-journey verification — the API and worker
are never mocked in those journeys, only the test *fixtures* are seeded here.
Synthetic data only; never the real Google-connected account.

Usage:
    uv run python scripts/e2e_deletion_support.py seed-imported <user_id>
    uv run python scripts/e2e_deletion_support.py seed-account  <user_id>
    uv run python scripts/e2e_deletion_support.py counts        <user_id>   (JSON)
    uv run python scripts/e2e_deletion_support.py user-state    <user_id>   (JSON)
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

import asyncpg

# The synthetic local dev database (same value as config.py's default and
# docker-compose); overridable via DATABASE_URL. asyncpg wants a plain DSN.
_DEFAULT_DSN = "postgresql://lifeflow:lifeflow@localhost:5433/lifeflow"  # pragma: allowlist secret
DSN = os.environ.get("DATABASE_URL", _DEFAULT_DSN).replace("+asyncpg", "")

GMAIL_RO = "https://www.googleapis.com/auth/gmail.readonly"

# This script writes and reads test fixtures; it must never touch a production
# or staging database. Two independent guards enforce that: an explicit E2E
# environment marker, and a strict local-host + known-dev/test-name allowlist.
_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1", "db", "postgres"}
_ALLOWED_DB_NAMES = {"lifeflow", "lifeflow_test", "lifeflow_e2e"}


def _assert_safe_target() -> None:
    if os.environ.get("LIFEFLOW_E2E") != "1":
        raise SystemExit(
            "refusing to run: LIFEFLOW_E2E=1 is required (this seeds/reads test fixtures only)"
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


async def _account(conn: asyncpg.Connection, user_id: uuid.UUID, provider: str) -> uuid.UUID:
    account_id = uuid.uuid4()
    scopes = json.dumps([GMAIL_RO]) if provider == "google" else "[]"
    await conn.execute(
        "INSERT INTO connected_accounts "
        "(id, user_id, provider, granted_scopes, status, authorisation_revision, "
        "sync_cursors, last_sync_at) "
        "VALUES ($1, $2, $3, $4, 'active', 1, '{}', $5)",
        account_id,
        user_id,
        provider,
        scopes,
        datetime.now(UTC),
    )
    return account_id


async def _source(
    conn: asyncpg.Connection, user_id: uuid.UUID, account_id: uuid.UUID, ext: str
) -> None:
    now = datetime.now(UTC)
    await conn.execute(
        "INSERT INTO source_items "
        "(id, user_id, source_type, external_id, source_account_id, title, "
        "occurred_at, content_fingerprint, metadata_json, created_at) "
        "VALUES ($1, $2, 'email', $3, $4, 't', $5, $6, '{}', $5)",
        uuid.uuid4(),
        user_id,
        ext,
        account_id,
        now,
        f"fp-{ext}",
    )


async def seed_imported(user_id: uuid.UUID) -> None:
    conn = await _connect()
    try:
        google = await _account(conn, user_id, "google")
        secondary = await _account(conn, user_id, "secondary")
        for ext in ("g-1", "g-2", "g-3"):
            await _source(conn, user_id, google, ext)
        await _source(conn, user_id, secondary, "s-1")
    finally:
        await conn.close()


async def seed_account(user_id: uuid.UUID) -> None:
    conn = await _connect()
    try:
        google = await _account(conn, user_id, "google")
        for ext in ("a-1", "a-2"):
            await _source(conn, user_id, google, ext)
    finally:
        await conn.close()


async def counts(user_id: uuid.UUID) -> dict[str, int]:
    conn = await _connect()
    try:
        google_sources = await conn.fetchval(
            "SELECT count(*) FROM source_items s "
            "JOIN connected_accounts c ON s.source_account_id = c.id "
            "WHERE c.provider = 'google' AND s.user_id = $1",
            user_id,
        )
        secondary_sources = await conn.fetchval(
            "SELECT count(*) FROM source_items s "
            "JOIN connected_accounts c ON s.source_account_id = c.id "
            "WHERE c.provider = 'secondary' AND s.user_id = $1",
            user_id,
        )
        return {"google_sources": google_sources, "secondary_sources": secondary_sources}
    finally:
        await conn.close()


async def user_state(user_id: uuid.UUID) -> dict[str, object]:
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            "SELECT account_state, email, display_name, google_subject, "
            "deletion_subject_id FROM users WHERE id = $1",
            user_id,
        )
        source_items = await conn.fetchval(
            "SELECT count(*) FROM source_items WHERE user_id = $1", user_id
        )
        connected = await conn.fetchval(
            "SELECT count(*) FROM connected_accounts WHERE user_id = $1", user_id
        )
        audits = await conn.fetchval(
            "SELECT count(*) FROM audit_events WHERE user_id = $1", user_id
        )
        meta = await conn.fetch(
            "SELECT safe_metadata_json::text AS m FROM audit_events WHERE user_id = $1", user_id
        )
        return {
            "account_state": row["account_state"],
            "email": row["email"],
            "display_name": row["display_name"],
            "google_subject": row["google_subject"],
            "deletion_subject_id": str(row["deletion_subject_id"])
            if row["deletion_subject_id"]
            else None,
            "source_items": source_items,
            "connected_accounts": connected,
            "audit_events": audits,
            "audit_metadata_blob": " ".join(r["m"] for r in meta),
        }
    finally:
        await conn.close()


async def _main() -> None:
    command, raw_user_id = sys.argv[1], sys.argv[2]
    user_id = uuid.UUID(raw_user_id)
    if command == "seed-imported":
        await seed_imported(user_id)
    elif command == "seed-account":
        await seed_account(user_id)
    elif command == "counts":
        print(json.dumps(await counts(user_id)))
    elif command == "user-state":
        print(json.dumps(await user_state(user_id)))
    else:
        raise SystemExit(f"unknown command {command!r}")


if __name__ == "__main__":
    asyncio.run(_main())
