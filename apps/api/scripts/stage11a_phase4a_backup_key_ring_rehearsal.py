"""Stage 11A Phase 4A (S11A-P4A-039/040/041) — backup and key-ring
retirement implications.

Extends Phase 3's backup-vs-deletion rehearsal
(`stage11a_phase3_backup_deletion_rehearsal.py`) to the multi-key question
that phase never asked because no rotation capability existed yet: what
happens to a backup once a key it depends on is retired?

Each cycle: seed a synthetic account with a credential still on a "legacy"
key, take a backup, migrate the live database to the active key, restore the
backup into an isolated database, and prove three things directly:

1. the backup preserves key-version metadata and ciphertext untouched — no
   key material ever enters the dump;
2. restoring with the correct key ring (both legacy and active keys
   supplied) can still decrypt the pre-migration synthetic credential;
3. restoring with an *incomplete* key ring (legacy key omitted, as it would
   be after a real retirement) fails safely and explicitly — never silently,
   never by exposing a fallback plaintext path.

This does not contradict F-P3-05 (backups are not retroactively affected by
later deletion) — it extends the same honest limitation to keys: retiring a
live key does not, and structurally cannot, reach into an already-taken
backup. A real deployment must therefore retain every key a still-relevant
backup depends on until that backup itself expires under its own retention
policy — recorded here, not solved, since no production backup
infrastructure exists yet for a real policy to apply to.

Synthetic data only, restricted to `localhost`/`127.0.0.1` and a dedicated
database-name prefix this script owns end to end.

Usage (from the repository root, with `docker compose up -d db` running):
    uv run --project apps/api python3 \\
        apps/api/scripts/stage11a_phase4a_backup_key_ring_rehearsal.py [cycles]
"""

from __future__ import annotations

import asyncio
import base64
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import asyncpg
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lifeflow_api.credential_rotation import rotate_batch
from lifeflow_api.db import Base
from lifeflow_api.models import AccountStatus, ConnectedAccount, User
from lifeflow_api.security.credential_context import (
    ACCESS_TOKEN_FIELD,
    credential_context,
)
from lifeflow_api.security.token_cipher import AesGcmTokenCipher, TokenKeyRing

ADMIN_DSN = "postgresql://lifeflow:lifeflow@localhost:5433/lifeflow"  # pragma: allowlist secret
_ENGINE_DSN_PREFIX = (
    "postgresql+asyncpg://lifeflow:lifeflow@localhost:5433"  # pragma: allowlist secret
)
_ALLOWED_HOSTS = {"localhost", "127.0.0.1"}
_ALLOWED_DB_PREFIX = "lifeflow_phase4a_backup_"
_LEGACY_KEY_ID = "legacy-backup"
_ACTIVE_KEY_ID = "active-backup"
_FORBIDDEN_DUMP_STRINGS = ("TOKEN_KEY", "SESSION_SECRET", "-----BEGIN")


class RehearsalError(AssertionError):
    pass


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


def _engine(db_name: str):
    return create_async_engine(f"{_ENGINE_DSN_PREFIX}/{db_name}")


def _random_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


def _dump(source_db: str, dump_path: Path) -> None:
    """`pg_dump`/`pg_restore` run inside the `db` container (never assumed
    to be installed on the host) — the same `docker compose exec -T db ...`
    pattern `stage11a_phase3_backup_deletion_rehearsal.py` established."""
    _assert_safe_target(source_db)
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


def _scan_dump_for_secrets(dump_path: Path) -> None:
    with dump_path.open("rb") as fh:
        listing = subprocess.run(
            ["docker", "compose", "exec", "-T", "db", "pg_restore", "-l"],
            stdin=fh,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    for forbidden in _FORBIDDEN_DUMP_STRINGS:
        if forbidden in listing:
            raise RehearsalError(f"backup table-of-contents unexpectedly contains {forbidden!r}")


def _restore(dump_path: Path, target_db: str) -> None:
    _assert_safe_target(target_db)
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
                target_db,
            ],
            stdin=fh,
            check=True,
        )


async def _run_cycle(cycle: int, tmp_dir: Path) -> None:
    live_db = f"{_ALLOWED_DB_PREFIX}live_{cycle}_{uuid.uuid4().hex[:8]}"
    restored_db = f"{_ALLOWED_DB_PREFIX}restored_{cycle}_{uuid.uuid4().hex[:8]}"
    await _create_database(live_db)
    await _create_database(restored_db)
    live_engine = _engine(live_db)
    try:
        async with live_engine.begin() as tx:
            await tx.run_sync(Base.metadata.create_all)

        legacy_cipher = AesGcmTokenCipher(_random_key(), _LEGACY_KEY_ID)
        active_cipher = AesGcmTokenCipher(_random_key(), _ACTIVE_KEY_ID)

        maker = async_sessionmaker(live_engine, expire_on_commit=False)
        async with maker() as session:
            user = User(
                email=f"phase4a-backup-{uuid.uuid4()}@lifeflow-owner-validation.example",
                display_name="Phase 4A Backup Rehearsal",
            )
            session.add(user)
            await session.flush()
            account = ConnectedAccount(
                user_id=user.id,
                provider="google",
                status=AccountStatus.active,
                granted_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            )
            session.add(account)
            await session.flush()
            context = credential_context(
                connected_account_id=account.id,
                user_id=user.id,
                provider="google",
                field=ACCESS_TOKEN_FIELD,
            )
            envelope = legacy_cipher.encrypt(f"synthetic-{uuid.uuid4()}", context=context)
            account.encrypted_access_token = envelope
            account.access_token_key_id = _LEGACY_KEY_ID
            await session.commit()
            user_id, account_id = user.id, account.id

        # 1. Backup preserves key-version metadata and ciphertext, no key material.
        dump_path = tmp_dir / f"cycle-{cycle}.dump"
        _dump(live_db, dump_path)
        _scan_dump_for_secrets(dump_path)

        # Migrate the LIVE database to the active key after the backup was taken.
        dual_ring = TokenKeyRing(active_cipher, [legacy_cipher])
        async with maker() as session:
            await rotate_batch(session, dual_ring, batch_size=10)
            await session.commit()
        async with maker() as session:
            live_account = await session.get(ConnectedAccount, account_id, populate_existing=True)
            if live_account is None or live_account.access_token_key_id != _ACTIVE_KEY_ID:
                raise RehearsalError("live database did not migrate to the active key")

        # 2. Restore with the CORRECT (full) key ring can still decrypt the
        # pre-migration synthetic credential exactly as it was backed up.
        _restore(dump_path, restored_db)
        restored_engine = _engine(restored_db)
        try:
            restored_maker = async_sessionmaker(restored_engine, expire_on_commit=False)
            async with restored_maker() as session:
                restored_account = await session.get(ConnectedAccount, account_id)
                if restored_account is None:
                    raise RehearsalError("restored backup is missing the seeded account")
                if restored_account.access_token_key_id != _LEGACY_KEY_ID:
                    raise RehearsalError(
                        "restored backup shows the migrated key — migration leaked into the backup"
                    )
                full_ring = TokenKeyRing(active_cipher, [legacy_cipher])
                context = credential_context(
                    connected_account_id=account_id,
                    user_id=user_id,
                    provider="google",
                    field=ACCESS_TOKEN_FIELD,
                )
                plaintext = full_ring.decrypt(
                    restored_account.encrypted_access_token, context=context
                )
                if not plaintext.startswith("synthetic-"):
                    raise RehearsalError(
                        "restored credential did not decrypt to the expected value"
                    )

                # 3. Restore with an INCOMPLETE key ring (legacy key omitted,
                # as it would be after a real retirement) fails safely.
                incomplete_ring = TokenKeyRing(active_cipher)
                try:
                    incomplete_ring.decrypt(
                        restored_account.encrypted_access_token, context=context
                    )
                except Exception as exc:  # the documented safe-failure path
                    if "No key available" not in str(exc):
                        raise RehearsalError(
                            f"incomplete-key-ring restore failed with an unexpected error: {exc!r}"
                        ) from exc
                else:
                    raise RehearsalError(
                        "restoring with an incomplete key ring decrypted successfully "
                        "— expected a safe failure"
                    )
        finally:
            await restored_engine.dispose()
    finally:
        await live_engine.dispose()
        await _drop_database(live_db)
        await _drop_database(restored_db)


async def main(cycles: int) -> None:
    with tempfile.TemporaryDirectory(prefix="lifeflow-phase4a-backup-") as tmp:
        tmp_dir = Path(tmp)
        for cycle in range(cycles):
            await _run_cycle(cycle, tmp_dir)
            print(f"cycle {cycle + 1}/{cycles}: PASS")
    print(f"All {cycles} backup/key-ring rehearsal cycles passed.")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    asyncio.run(main(n))
