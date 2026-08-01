"""Stage 11A Phase 4A (F-P3-03) — the operator command that runs credential
key rotation against a real deployment's database.

Deliberately a local/operator CLI, never a public API route (the governing
task requires no user-facing rotation endpoint and no way for a
user-controlled identifier to direct rotation): only someone with direct
process/database access to the deployment can invoke this.

Reads `TOKEN_KEY`/`TOKEN_KEY_ID`/`TOKEN_KEY_LEGACY_JSON` from the same
environment the API/worker processes use (`config.py`) — it never accepts
key material as a command-line argument or accepts any per-row identifier
from outside the process's own configuration and database.

Usage (from apps/api):
    uv run python3 scripts/rotate_credential_keys.py --dry-run
    uv run python3 scripts/rotate_credential_keys.py --batch-size 100
    uv run python3 scripts/rotate_credential_keys.py --verify-retirement <key_id>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy.ext.asyncio import async_sessionmaker

from lifeflow_api.config import get_settings
from lifeflow_api.credential_rotation import (
    dry_run_inventory,
    rotate_batch,
    verify_key_retirement_safe,
)
from lifeflow_api.db import create_engine
from lifeflow_api.security.token_cipher import TokenCipherError, build_key_ring


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report counts only, change nothing")
    parser.add_argument("--batch-size", type=int, default=50, help="rows per migration batch")
    parser.add_argument(
        "--verify-retirement",
        metavar="KEY_ID",
        help="exit 0 if zero rows reference KEY_ID (safe to retire), else exit 1",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.token_key:
        print("TOKEN_KEY is not configured; nothing to rotate.", file=sys.stderr)
        return 1
    try:
        key_ring = build_key_ring(
            settings.token_key, settings.token_key_id, settings.token_key_legacy_json
        )
    except TokenCipherError as exc:
        print(f"Invalid TOKEN_KEY configuration: {exc}", file=sys.stderr)
        return 1

    engine = create_engine(settings.database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        if args.verify_retirement:
            async with maker() as session:
                safe = await verify_key_retirement_safe(session, args.verify_retirement)
            print(f"key_id={args.verify_retirement} safe_to_retire={safe}")
            return 0 if safe else 1

        async with maker() as session:
            inventory = await dry_run_inventory(session, key_ring)
        if not inventory:
            print("Nothing needs rotation; every row is on the active key.")
            return 0
        print(f"Rows needing rotation, by current key id: {inventory}")
        if args.dry_run:
            return 0

        total_migrated = total_blocked = 0
        while True:
            async with maker() as session:
                result = await rotate_batch(session, key_ring, batch_size=args.batch_size)
                await session.commit()
            total_migrated += result.migrated
            total_blocked += result.blocked
            print(
                f"batch: migrated={result.migrated} skipped_current={result.skipped_current} "
                f"blocked={result.blocked}"
            )
            if result.processed == 0:
                break
        print(f"Done. migrated={total_migrated} blocked={total_blocked}")
        return 1 if total_blocked else 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
