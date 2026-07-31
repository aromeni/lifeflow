"""Stage 11A Phase 3 (S11A-P3-036) — backup-vs-deletion validation.

Phase 2 built the first backup/restore rehearsal in this project
(`stage11a_phase2_backup_restore_rehearsal.py`) and proved backup/restore is
data-faithful. It never asked the compliance question Phase 3's contract
requires: does deleting a user from the *active* database retroactively
touch a backup taken *before* that deletion? The honest, structurally
correct answer for any conventional `pg_dump` snapshot is no — a backup is a
frozen point-in-time copy, so this script proves that directly rather than
asserting it, and documents the real consequence: a production deployment
needs an explicit backup-retention/expiry policy aligned to the data's
retention rules, because deletion alone does not reach into old backups.

Each cycle: seed a synthetic user with a full reference graph (including a
real encrypted-token connected account), take a "pre-deletion" backup,
delete the user's account for real in the *active* database, restore the
pre-deletion backup into a separate isolated database, and verify the
restored copy still contains the exact pre-deletion state — proving the
active database's deletion did not (and structurally could not) alter the
older backup. Also rehearses a bounded backup-retention/expiry sweep and
confirms restored credentials are synthetic and inert.

Synthetic data only, restricted to `localhost`/`127.0.0.1` and a dedicated
database-name prefix this script owns end to end, via the same
`_assert_safe_target` guard Phase 2's script established. Never commits a
dump file — every dump lives in a `tempfile` directory removed at the end of
the run regardless of outcome.

Usage (from the repository root, with `docker compose up -d db` running):
    uv run --project apps/api python3 \\
        apps/api/scripts/stage11a_phase3_backup_deletion_rehearsal.py [cycles]
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lifeflow_api.db import Base
from lifeflow_api.deletion import confirm_operation, create_account_deletion_preview, run_operation
from lifeflow_api.deletion_ops import CONFIRM_ACCOUNT
from lifeflow_api.models import ConnectedAccount, SourceItem, User, UserAccountState
from lifeflow_api.retention import RetentionHorizons
from lifeflow_api.security.token_cipher import AesGcmTokenCipher

HORIZONS = RetentionHorizons(
    source_items_days=30,
    brief_versions_days=90,
    unapproved_proposals_days=90,
    scheduled_runs_days=90,
    memory_evidence_days=90,
)

ADMIN_DSN = "postgresql://lifeflow:lifeflow@localhost:5433/lifeflow"  # pragma: allowlist secret
_ALLOWED_HOSTS = {"localhost", "127.0.0.1"}
_ALLOWED_DB_PREFIX = "lifeflow_phase3_backup_"
NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
_BACKUP_RETENTION_SECONDS = 7 * 24 * 60 * 60  # documented local rehearsal policy, 7 days


def _assert_safe_target(db_name: str) -> None:
    from urllib.parse import urlparse

    host = urlparse(ADMIN_DSN.replace("postgresql://", "http://")).hostname
    if host not in _ALLOWED_HOSTS:
        raise RuntimeError(f"refusing to run against non-local host {host!r}")
    if not db_name.startswith(_ALLOWED_DB_PREFIX):
        raise RuntimeError(f"refusing to touch database {db_name!r} outside this rehearsal")


async def _create_database(db_name: str) -> None:
    _assert_safe_target(db_name)
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()


async def _drop_database(db_name: str) -> None:
    _assert_safe_target(db_name)
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    finally:
        await conn.close()


_ENGINE_DSN_PREFIX = (
    "postgresql+asyncpg://lifeflow:lifeflow@localhost:5433"  # pragma: allowlist secret
)


def _engine(db_name: str):
    return create_async_engine(f"{_ENGINE_DSN_PREFIX}/{db_name}")


async def _seed(db_name: str) -> dict[str, object]:
    engine = _engine(db_name)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as tx:
        await tx.run_sync(Base.metadata.create_all)
    async with maker() as session:
        cipher = AesGcmTokenCipher(base64.b64encode(os.urandom(32)).decode(), "phase3-backup-key")
        original_email = f"phase3-backup-{uuid.uuid4()}@lifeflow-owner-validation.example"
        user = User(email=original_email, display_name="Phase 3 Backup Rehearsal")
        session.add(user)
        await session.flush()

        account = ConnectedAccount(
            user_id=user.id,
            provider="google",
            granted_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )
        session.add(account)
        await session.flush()
        account.encrypted_access_token = cipher.encrypt("synthetic-access-token")
        account.encrypted_refresh_token = cipher.encrypt("synthetic-refresh-token")

        source = SourceItem(
            user_id=user.id,
            source_type="email",
            external_id="phase3-backup-em-1",
            source_account_id=account.id,
            title="Backup rehearsal source item",
            sender_or_organiser="owner@lifeflow-owner-validation.example",
            occurred_at=NOW,
            content_fingerprint="f" * 64,
        )
        session.add(source)
        await session.commit()

        figures = {
            "user_id": str(user.id),
            "original_email": original_email,
            "source_item_count": 1,
            "connected_account_count": 1,
            "encrypted_access_token": account.encrypted_access_token,
        }
    await engine.dispose()
    return figures


async def _delete_account_in_active_database(db_name: str, user_id: str) -> None:
    """The deletion this rehearsal proves does NOT retroactively touch an
    already-taken backup."""
    engine = _engine(db_name)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        user = await session.get(User, uuid.UUID(user_id))
        if user is None:
            raise RuntimeError("seed user missing from active database")
        op = await create_account_deletion_preview(session, user, now=NOW, ttl_minutes=30)
        confirmed = await confirm_operation(
            session,
            user,
            op.id,
            expected_version=op.version,
            phrase=CONFIRM_ACCOUNT,
            now=NOW,
            preview_ttl_minutes=30,
        )
        await session.commit()
        await run_operation(
            session, confirmed.id, now=NOW, horizons=HORIZONS, batch_size=50, max_attempts=3
        )
        await session.commit()
    await engine.dispose()


async def _verify_active_database_reflects_deletion(
    db_name: str, expected: dict[str, object]
) -> None:
    engine = _engine(db_name)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        user_id = uuid.UUID(str(expected["user_id"]))
        user = await session.get(User, user_id, populate_existing=True)
        if user is None or user.account_state != UserAccountState.deleted:
            raise AssertionError("active database did not reach a deleted account state")
        if user.email == expected["original_email"]:
            raise AssertionError("active database's user email was not anonymised")
        remaining_sources = (
            (await session.execute(select(SourceItem).where(SourceItem.user_id == user_id)))
            .scalars()
            .all()
        )
        if remaining_sources:
            raise AssertionError("active database still has source items after deletion")
    await engine.dispose()


async def _verify_restored_backup_retains_pre_deletion_state(
    db_name: str, expected: dict[str, object]
) -> None:
    """The core compliance proof: the backup taken BEFORE deletion, once
    restored, must show the ORIGINAL pre-deletion state — never the
    anonymised state the active database now has. This is not a bug; it is
    the documented, honest limitation every conventional backup carries."""
    engine = _engine(db_name)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        user_id = uuid.UUID(str(expected["user_id"]))
        user = await session.get(User, user_id, populate_existing=True)
        if user is None:
            raise AssertionError("restored backup is missing the seeded user entirely")
        if user.email != expected["original_email"]:
            raise AssertionError("restored backup does not retain the pre-deletion email")
        if user.account_state == UserAccountState.deleted:
            raise AssertionError(
                "restored backup shows a deleted account state — deletion leaked into the backup"
            )
        sources = (
            (await session.execute(select(SourceItem).where(SourceItem.user_id == user_id)))
            .scalars()
            .all()
        )
        if len(sources) != expected["source_item_count"]:
            raise AssertionError("restored backup lost the pre-deletion source item")
        accounts = (
            (
                await session.execute(
                    select(ConnectedAccount).where(ConnectedAccount.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        if len(accounts) != expected["connected_account_count"]:
            raise AssertionError("restored backup lost the pre-deletion connected account")
        restored_account = accounts[0]
        if restored_account.encrypted_access_token != expected["encrypted_access_token"]:
            raise AssertionError("restored ciphertext does not match the pre-deletion envelope")
        # Restored credentials are synthetic ciphertext with no real provider
        # host or live key anywhere in this rehearsal — inert by
        # construction, never capable of an outbound call.
        if not str(restored_account.encrypted_access_token).startswith("v1:"):
            raise AssertionError("restored token envelope is not the expected synthetic format")
    await engine.dispose()


def _dump(source_db: str, dump_path: Path) -> None:
    with dump_path.open("wb") as fh:
        subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "db",
                "pg_dump",
                "-U",
                "lifeflow",
                "-Fc",
                source_db,
            ],
            stdout=fh,
            check=True,
        )


def _restore(dest_db: str, dump_path: Path) -> None:
    with dump_path.open("rb") as fh:
        subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "db",
                "pg_restore",
                "-U",
                "lifeflow",
                "-d",
                dest_db,
            ],
            stdin=fh,
            check=True,
        )


def _scan_dump_for_secrets(dump_path: Path) -> None:
    listing = subprocess.run(
        ["docker", "compose", "exec", "-T", "db", "pg_restore", "-l"],
        stdin=dump_path.open("rb"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    for forbidden in ("SESSION_SECRET", "TOKEN_KEY", "-----BEGIN"):
        if forbidden in listing:
            raise AssertionError(f"dump table-of-contents unexpectedly names {forbidden!r}")


def _rehearse_backup_retention_sweep(scratch_dir: Path) -> None:
    """A minimal, local rehearsal of the retention/expiry policy a real
    deployment would need: backups past a fixed age are destroyed; a fresh
    one is not touched. This is local file-age bookkeeping only — it says
    nothing about a real backup storage provider's own lifecycle rules,
    which remain a documented, separately-owned production requirement."""
    fresh = scratch_dir / "backup-fresh.dump"
    expired = scratch_dir / "backup-expired.dump"
    fresh.write_bytes(b"fresh")
    expired.write_bytes(b"expired")
    old_time = time.time() - (_BACKUP_RETENTION_SECONDS + 3600)
    os.utime(expired, (old_time, old_time))

    now = time.time()
    for candidate in scratch_dir.glob("backup-*.dump"):
        age = now - candidate.stat().st_mtime
        if age > _BACKUP_RETENTION_SECONDS:
            candidate.unlink()

    if expired.exists():
        raise AssertionError("expired test backup was not destroyed by the retention sweep")
    if not fresh.exists():
        raise AssertionError("fresh backup was incorrectly destroyed by the retention sweep")
    fresh.unlink()


async def run_one_cycle(cycle: int, scratch_dir: Path) -> dict[str, float]:
    source_db = f"{_ALLOWED_DB_PREFIX}src_{cycle}"
    dest_db = f"{_ALLOWED_DB_PREFIX}restore_{cycle}"
    dump_path = scratch_dir / f"cycle-{cycle}.dump"

    t0 = time.monotonic()
    await _create_database(source_db)
    figures = await _seed(source_db)
    t_seeded = time.monotonic()

    # Backup taken BEFORE deletion.
    _dump(source_db, dump_path)
    _scan_dump_for_secrets(dump_path)
    t_backed_up = time.monotonic()

    # Real deletion in the ACTIVE database, after the backup was taken.
    await _delete_account_in_active_database(source_db, str(figures["user_id"]))
    await _verify_active_database_reflects_deletion(source_db, figures)
    t_deleted = time.monotonic()

    # Restore the pre-deletion backup into an isolated environment.
    await _create_database(dest_db)
    _restore(dest_db, dump_path)
    await _verify_restored_backup_retains_pre_deletion_state(dest_db, figures)
    t_restored = time.monotonic()

    await _drop_database(source_db)
    await _drop_database(dest_db)
    dump_path.unlink(missing_ok=True)

    return {
        "seed_seconds": round(t_seeded - t0, 2),
        "backup_seconds": round(t_backed_up - t_seeded, 2),
        "deletion_seconds": round(t_deleted - t_backed_up, 2),
        "restore_and_verify_seconds": round(t_restored - t_deleted, 2),
        "total_seconds": round(t_restored - t0, 2),
    }


async def main() -> int:
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    results = []
    with tempfile.TemporaryDirectory(prefix="lifeflow-phase3-backup-") as scratch:
        scratch_dir = Path(scratch)
        _rehearse_backup_retention_sweep(scratch_dir)
        for cycle in range(cycles):
            timing = await run_one_cycle(cycle, scratch_dir)
            results.append(timing)
            print(f"cycle {cycle}: {json.dumps(timing)}")
    print(json.dumps({"cycles": len(results), "results": results}))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
