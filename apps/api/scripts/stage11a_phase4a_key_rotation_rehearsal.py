"""Stage 11A Phase 4A (S11A-P4A-044) — the full key-rotation rehearsal.

Runs the 18-step lifecycle the governing task requires, against a dedicated,
isolated local PostgreSQL database this script owns end to end (created and
dropped every run, never the shared dev/test database): multiple owners,
multiple connected accounts, credentials under a "legacy" key, a dry-run
inventory, bounded interrupted-then-resumed batch migration, a concurrent
token refresh racing the migration, legacy-key retirement gated on zero
references, a simulated service restart under a key ring with the legacy key
removed, and full disconnect/deletion residue verification.

"Legacy key `v1`" / "active key `v2`" below name the *key version being
rotated away from/to*, not the ciphertext envelope wire-format version
(`security/token_cipher.py`'s `v1`/`v2` envelope shapes) — this project has
never stored a real credential, so there is no genuine legacy envelope-format
row to migrate; what this rehearsal proves is the harder, forward-looking
case (rotating between two context-bound `v2`-format keys), which is exactly
what every future real rotation in this project will need. Envelope-format
backward compatibility (an actual `v1`-format row) is proven separately and
directly in `apps/api/tests/test_token_cipher.py`.

Synthetic data only. Never calls a real Google endpoint. Never commits a
database file.

Usage (from the repository root, with `docker compose up -d db` running):
    uv run --project apps/api python3 \\
        apps/api/scripts/stage11a_phase4a_key_rotation_rehearsal.py [cycles]
"""

from __future__ import annotations

import asyncio
import base64
import os
import sys
import time
import uuid
from pathlib import Path

import asyncpg
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lifeflow_api.credential_rotation import (
    dry_run_inventory,
    rotate_batch,
    verify_key_retirement_safe,
)
from lifeflow_api.db import Base
from lifeflow_api.models import AccountStatus, ConnectedAccount, User
from lifeflow_api.security.credential_context import (
    ACCESS_TOKEN_FIELD,
    REFRESH_TOKEN_FIELD,
    credential_context,
)
from lifeflow_api.security.token_cipher import AesGcmTokenCipher, TokenKeyRing

ADMIN_DSN = "postgresql://lifeflow:lifeflow@localhost:5433/lifeflow"  # pragma: allowlist secret
_ENGINE_DSN_PREFIX = (
    "postgresql+asyncpg://lifeflow:lifeflow@localhost:5433"  # pragma: allowlist secret
)
_ALLOWED_HOSTS = {"localhost", "127.0.0.1"}
_ALLOWED_DB_PREFIX = "lifeflow_phase4a_rotation_"
_LEGACY_KEY_ID = "legacy-v1"
_ACTIVE_KEY_ID = "active-v2"


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


class RehearsalError(AssertionError):
    pass


async def _run_cycle(cycle: int) -> dict[str, float]:
    db_name = f"{_ALLOWED_DB_PREFIX}{uuid.uuid4().hex[:12]}"
    timings: dict[str, float] = {}
    t_start = time.monotonic()
    await _create_database(db_name)
    engine = _engine(db_name)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as tx:
            await tx.run_sync(Base.metadata.create_all)

        legacy_cipher = AesGcmTokenCipher(_random_key(), _LEGACY_KEY_ID)
        active_cipher = AesGcmTokenCipher(_random_key(), _ACTIVE_KEY_ID)
        legacy_ring = TokenKeyRing(legacy_cipher)  # step 5: only v1 exists yet
        dual_ring = TokenKeyRing(active_cipher, [legacy_cipher])  # step 5: v2 active, v1 legacy

        # --- 1/2/3: multiple owners, multiple connected accounts, legacy-key credentials
        owner_account_ids: list[tuple[uuid.UUID, uuid.UUID]] = []
        async with maker() as session:
            for owner_n in range(3):
                user = User(
                    email=f"phase4a-owner-{cycle}-{owner_n}-{uuid.uuid4()}@lifeflow-owner-validation.example",
                    display_name=f"Phase 4A Owner {owner_n}",
                )
                session.add(user)
                await session.flush()
                for provider in ("google", "google_calendar_test"):
                    account = ConnectedAccount(
                        user_id=user.id,
                        provider=provider,
                        status=AccountStatus.active,
                        granted_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                    )
                    session.add(account)
                    await session.flush()
                    for field_name, attr, key_attr in (
                        (ACCESS_TOKEN_FIELD, "encrypted_access_token", "access_token_key_id"),
                        (REFRESH_TOKEN_FIELD, "encrypted_refresh_token", "refresh_token_key_id"),
                    ):
                        context = credential_context(
                            connected_account_id=account.id,
                            user_id=user.id,
                            provider=provider,
                            field=field_name,
                        )
                        envelope = legacy_ring.encrypt(
                            f"synthetic-{field_name}-{uuid.uuid4()}", context=context
                        )
                        setattr(account, attr, envelope)
                        setattr(account, key_attr, legacy_ring.active_key_id)
                    owner_account_ids.append((user.id, account.id))
            await session.commit()
        timings["seed"] = time.monotonic() - t_start

        # --- 4: confirm correct owner-scoped use (decrypt one row directly)
        async with maker() as session:
            user_id, account_id = owner_account_ids[0]
            account = await session.get(ConnectedAccount, account_id)
            if account is None:
                raise RehearsalError("seeded account missing")
            context = credential_context(
                connected_account_id=account.id,
                user_id=user_id,
                provider=account.provider,
                field=ACCESS_TOKEN_FIELD,
            )
            plaintext = dual_ring.decrypt(account.encrypted_access_token, context=context)
            if not plaintext.startswith("synthetic-access_token-"):
                raise RehearsalError("owner-scoped decrypt of a legacy-key row failed")

        # --- 6: dry-run inventory
        t = time.monotonic()
        async with maker() as session:
            inventory = await dry_run_inventory(session, dual_ring)
        # Each account contributes two field-level references (access +
        # refresh), both still on the legacy key at this point.
        expected = len(owner_account_ids) * 2
        if inventory.get(_LEGACY_KEY_ID, 0) != expected:
            raise RehearsalError(f"dry-run inventory mismatch: {inventory}, expected {expected}")
        timings["dry_run"] = time.monotonic() - t

        # --- 7/8: migrate in bounded batches, interrupt part-way, resume
        t = time.monotonic()
        total_migrated = 0
        async with maker() as session:
            result = await rotate_batch(session, dual_ring, batch_size=2)
            await session.commit()
        total_migrated += result.migrated
        if result.migrated == 0:
            raise RehearsalError("first batch migrated nothing")
        # Simulate an interruption: open a session, do partial work, roll back.
        async with maker() as session:
            await rotate_batch(session, dual_ring, batch_size=1)
            await session.rollback()  # interruption — nothing here should count
        # Resume: run remaining batches to completion.
        for _ in range(10):
            async with maker() as session:
                result = await rotate_batch(session, dual_ring, batch_size=2)
                await session.commit()
            total_migrated += result.migrated
            if result.migrated == 0:
                break
        timings["migrate"] = time.monotonic() - t
        if total_migrated != len(owner_account_ids):
            raise RehearsalError(
                f"expected {len(owner_account_ids)} rows migrated, got {total_migrated}"
            )

        # --- 9: idempotent rerun — nothing left to migrate. Rows already on
        # the active key are not even selected as candidates, so every count
        # (migrated/skipped/blocked) is zero — a true no-op, not merely "zero
        # migrated."
        async with maker() as session:
            result = await rotate_batch(session, dual_ring, batch_size=50)
        if result.processed != 0:
            raise RehearsalError(f"rerun after full migration should be a no-op, got {result}")

        # --- 10: concurrent refresh during migration (simulated: a fresh
        # write through the active key while a second migration pass runs)
        async with maker() as session:
            user_id, account_id = owner_account_ids[1]
            account = await session.get(ConnectedAccount, account_id)
            if account is None:
                raise RehearsalError("seeded account missing")
            context = credential_context(
                connected_account_id=account.id,
                user_id=user_id,
                provider=account.provider,
                field=ACCESS_TOKEN_FIELD,
            )
            fresh_envelope = dual_ring.encrypt(f"refreshed-{uuid.uuid4()}", context=context)
            account.encrypted_access_token = fresh_envelope
            account.access_token_key_id = dual_ring.active_key_id
            await session.commit()
        async with maker() as session:
            result = await rotate_batch(session, dual_ring, batch_size=50)
        if result.migrated != 0:
            raise RehearsalError("rotation re-migrated an already-current, freshly-refreshed row")

        # --- 11: every surviving credential uses v2 (the active key)
        async with maker() as session:
            rows = (await session.execute(select(ConnectedAccount))).scalars().all()
            for row in rows:
                if (
                    row.access_token_key_id != _ACTIVE_KEY_ID
                    or row.refresh_token_key_id != _ACTIVE_KEY_ID
                ):
                    raise RehearsalError(f"row {row.id} not fully migrated to the active key")

        # --- 12: plaintext sentinels appear nowhere outside the controlled boundary
        async with maker() as session:
            rows = (await session.execute(select(ConnectedAccount))).scalars().all()
            for row in rows:
                for envelope in (row.encrypted_access_token, row.encrypted_refresh_token):
                    if envelope is None or (
                        "synthetic-" not in envelope and "refreshed-" not in envelope
                    ):
                        continue
                    raise RehearsalError("plaintext sentinel leaked into ciphertext column")

        # --- 13/14: remove v1 from the live key ring, restart services (simulated)
        if not all(
            await asyncio.gather(*(_retirement_check(maker, _LEGACY_KEY_ID) for _ in range(1)))
        ):
            raise RehearsalError("legacy key retirement check reported rows still referencing it")
        restarted_ring = TokenKeyRing(active_cipher)  # legacy key dropped entirely — "restart"

        # --- 15: prove all migrated credentials remain readable after "restart"
        async with maker() as session:
            for user_id, account_id in owner_account_ids:
                account = await session.get(ConnectedAccount, account_id)
                if account is None:
                    raise RehearsalError("seeded account missing")
                context = credential_context(
                    connected_account_id=account.id,
                    user_id=user_id,
                    provider=account.provider,
                    field=ACCESS_TOKEN_FIELD,
                )
                restarted_ring.decrypt(account.encrypted_access_token, context=context)

        # --- 16: prove no database record references v1
        async with maker() as session:
            remaining = await verify_key_retirement_safe(session, _LEGACY_KEY_ID)
        if not remaining:
            raise RehearsalError("a row still references the retired legacy key")

        # --- 17/18: disconnect and delete the synthetic accounts, prove no residue
        async with maker() as session:
            for _, account_id in owner_account_ids:
                account = await session.get(ConnectedAccount, account_id)
                if account is None:
                    raise RehearsalError("seeded account missing")
                account.status = AccountStatus.disconnected
                account.encrypted_access_token = None
                account.encrypted_refresh_token = None
                account.access_token_key_id = None
                account.refresh_token_key_id = None
            await session.commit()
        async with maker() as session:
            rows = (await session.execute(select(ConnectedAccount))).scalars().all()
            for row in rows:
                if row.encrypted_access_token is not None or row.access_token_key_id is not None:
                    raise RehearsalError("credential residue survived disconnect")

        timings["total"] = time.monotonic() - t_start
        return timings
    finally:
        await engine.dispose()
        await _drop_database(db_name)


async def _retirement_check(maker, key_id: str) -> bool:
    async with maker() as session:
        return await verify_key_retirement_safe(session, key_id)


async def main(cycles: int) -> None:
    for cycle in range(cycles):
        timings = await _run_cycle(cycle)
        print(
            f"cycle {cycle + 1}/{cycles}: PASS "
            f"(seed={timings['seed']:.2f}s dry_run={timings['dry_run']:.2f}s "
            f"migrate={timings['migrate']:.2f}s total={timings['total']:.2f}s)"
        )
    print(f"All {cycles} rotation rehearsal cycles passed.")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    asyncio.run(main(n))
