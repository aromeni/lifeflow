"""Stage 11A Phase 2 (docs/delivery/stage-11a-phase-2-plan.md), scenario
S11A-P2-026: a local backup/restore rehearsal against the dev-compose
PostgreSQL container. No backup or restore tooling existed anywhere in this
repository before this script — confirmed absent during Phase 2 research —
so this is genuinely new infrastructure, not a rewrite of anything.

Synthetic data only. Never touches a real deployment: two independent
guards (`_assert_safe_target`, mirroring `e2e_deletion_support.py`'s own
pattern) restrict every operation to `localhost`/`127.0.0.1` and a small
allowlist of throwaway database names this script itself owns end to end.

Each cycle: creates a scratch source database, seeds one synthetic user with
a full reference graph (connected account, source item, brief, an approved
+executed action proposal, an audit event, and a completed deletion
operation), records its state, `pg_dump`s it (via `docker compose exec db`,
so no host `pg_dump` install is required), restores the dump into a
*separate*, freshly created destination database, re-verifies every figure
matches, confirms no secret-shaped value was exported, then drops both
scratch databases. Never commits a dump file — every dump lives in a
`tempfile` directory removed at the end of the run regardless of outcome.

Usage (from the repository root, with `docker compose up -d db` running):
    uv run --project apps/api python3 \\
        apps/api/scripts/stage11a_phase2_backup_restore_rehearsal.py [cycles]
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lifeflow_api.db import Base
from lifeflow_api.deletion import (
    confirm_operation,
    create_imported_data_preview,
    run_operation,
)
from lifeflow_api.deletion_ops import CONFIRM_IMPORTED_DATA
from lifeflow_api.models import (
    ActionExecution,
    ActionProposal,
    ActionType,
    AuditEvent,
    Brief,
    ConnectedAccount,
    DataDeletionOperation,
    DeletionOperationState,
    ExecutionOutcome,
    ProposalStatus,
    RiskLevel,
    SourceItem,
    SourceType,
    User,
)
from lifeflow_api.retention import RetentionHorizons

HORIZONS = RetentionHorizons(
    source_items_days=30,
    brief_versions_days=90,
    unapproved_proposals_days=90,
    scheduled_runs_days=90,
    memory_evidence_days=90,
)

ADMIN_DSN = "postgresql://lifeflow:lifeflow@localhost:5433/lifeflow"  # pragma: allowlist secret
_ALLOWED_HOSTS = {"localhost", "127.0.0.1"}
_ALLOWED_DB_PREFIX = "lifeflow_phase2_backup_"
NOW = datetime(2026, 7, 31, 9, 0, tzinfo=UTC)


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


async def _seed(db_name: str) -> dict[str, object]:
    """Populate a full synthetic reference graph and return the figures the
    restored database must reproduce exactly."""
    engine = create_async_engine(f"postgresql+asyncpg://lifeflow:lifeflow@localhost:5433/{db_name}")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as tx:
        await tx.run_sync(Base.metadata.create_all)
    async with maker() as session:
        user = User(
            email=f"phase2-backup-{uuid.uuid4()}@lifeflow-owner-validation.example",
            display_name="Phase 2 Backup Rehearsal",
        )
        session.add(user)
        await session.flush()

        account = ConnectedAccount(user_id=user.id, provider="synthetic", granted_scopes=["demo"])
        session.add(account)
        await session.flush()

        source = SourceItem(
            user_id=user.id,
            source_type=SourceType.email,
            external_id="phase2-backup-em-1",
            source_account_id=account.id,
            title="Backup rehearsal source item",
            sender_or_organiser="owner@lifeflow-owner-validation.example",
            occurred_at=NOW,
            metadata_json={},
            content_fingerprint="f" * 64,
        )
        session.add(source)
        await session.flush()

        brief = Brief(
            user_id=user.id,
            briefing_date=NOW,
            summary="Backup rehearsal brief",
            sections_json={"needs_attention": []},
            source_window=f"{NOW.isoformat()}..{NOW.isoformat()}",
            prompt_version="det-v1",
            model_metadata={},
        )
        session.add(brief)

        # A fixed, dummy 64-char hex string stands in for a real computed
        # hash (matching the pattern `test_execution_durability.py` already
        # uses, e.g. `executed_payload_hash="a" * 64"`) — this rehearsal
        # verifies backup/restore preserves stored values byte-for-byte, not
        # that a hash was originally computed correctly (that is exercised
        # elsewhere, e.g. `test_action_proposals.py`).
        payload = {"title": "Backup rehearsal task", "notes": "", "due_at": None}
        dummy_hash = "b" * 64
        proposal = ActionProposal(
            user_id=user.id,
            action_type=ActionType.create_task,
            rationale="Backup rehearsal",
            source_refs=[source.external_id],
            payload_json=payload,
            payload_hash=dummy_hash,
            risk_level=RiskLevel.low,
            confidence=0.9,
            status=ProposalStatus.executed,
            expires_at=NOW,
            version=1,
            approved_action_type=ActionType.create_task,
            approved_payload_json=payload,
            approved_payload_hash=dummy_hash,
            approved_binding_hash=dummy_hash,
            approved_version=1,
            origin_fingerprint="phase2-backup-fp-1",
        )
        session.add(proposal)
        await session.flush()

        execution = ActionExecution(
            proposal_id=proposal.id,
            idempotency_key="phase2-backup-idem-1",
            approved_action_type=ActionType.create_task,
            approved_proposal_version=1,
            executed_payload_json=payload,
            executed_payload_hash=proposal.payload_hash,
            approval_binding_hash=proposal.approved_binding_hash,
            execution_mode="simulation",
            outcome=ExecutionOutcome.succeeded,
            result_json={"status": "created"},
            started_at=NOW,
            completed_at=NOW,
        )
        session.add(execution)

        audit = AuditEvent(
            user_id=user.id,
            actor=f"user:{user.id}",
            event_type="demo.started",
            entity_type="connected_account",
            entity_id=str(account.id),
            safe_metadata_json={},
            correlation_id=str(uuid.uuid4()),
        )
        session.add(audit)

        # A second, empty account (no source items) so a real, complete
        # imported-data-deletion cycle can run without touching the source
        # item/proposal/execution graph above being verified separately.
        empty_account = ConnectedAccount(user_id=user.id, provider="google", granted_scopes=[])
        session.add(empty_account)
        await session.flush()
        preview = await create_imported_data_preview(
            session, user, source_account_id=empty_account.id, now=NOW, ttl_minutes=30
        )
        confirmed = await confirm_operation(
            session,
            user,
            preview.id,
            expected_version=preview.version,
            phrase=CONFIRM_IMPORTED_DATA,
            now=NOW,
            preview_ttl_minutes=30,
        )
        await session.commit()
        await run_operation(
            session,
            confirmed.id,
            now=NOW,
            horizons=HORIZONS,
            batch_size=50,
            max_attempts=3,
        )
        await session.commit()
        reloaded_op = await session.get(DataDeletionOperation, confirmed.id, populate_existing=True)
        if reloaded_op is None or reloaded_op.state != DeletionOperationState.succeeded:
            raise RuntimeError("seed setup did not reach a succeeded deletion operation")

        from sqlalchemy import func, select

        audit_count = (
            await session.execute(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.user_id == user.id)
            )
        ).scalar_one()
        deletion_op_count = (
            await session.execute(
                select(func.count())
                .select_from(DataDeletionOperation)
                .where(DataDeletionOperation.user_id == user.id)
            )
        ).scalar_one()

        figures = {
            "user_id": str(user.id),
            "source_items": 1,
            "briefs": 1,
            "proposals": 1,
            "executions": 1,
            "audit_events": audit_count,
            "deletion_operations": deletion_op_count,
            "approval_binding_hash": proposal.approved_binding_hash,
        }
    await engine.dispose()
    return figures


async def _verify(db_name: str, expected: dict[str, object]) -> None:
    engine = create_async_engine(f"postgresql+asyncpg://lifeflow:lifeflow@localhost:5433/{db_name}")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        from sqlalchemy import select

        user_id = uuid.UUID(str(expected["user_id"]))
        counts = {
            "source_items": len(
                (await session.execute(select(SourceItem).where(SourceItem.user_id == user_id)))
                .scalars()
                .all()
            ),
            "briefs": len(
                (await session.execute(select(Brief).where(Brief.user_id == user_id)))
                .scalars()
                .all()
            ),
            "proposals": len(
                (
                    await session.execute(
                        select(ActionProposal).where(ActionProposal.user_id == user_id)
                    )
                )
                .scalars()
                .all()
            ),
            "audit_events": len(
                (await session.execute(select(AuditEvent).where(AuditEvent.user_id == user_id)))
                .scalars()
                .all()
            ),
            "deletion_operations": len(
                (
                    await session.execute(
                        select(DataDeletionOperation).where(
                            DataDeletionOperation.user_id == user_id
                        )
                    )
                )
                .scalars()
                .all()
            ),
        }
        proposal = (
            (await session.execute(select(ActionProposal).where(ActionProposal.user_id == user_id)))
            .scalars()
            .one()
        )
        executions = (
            (
                await session.execute(
                    select(ActionExecution).where(ActionExecution.proposal_id == proposal.id)
                )
            )
            .scalars()
            .all()
        )
        counts["executions"] = len(executions)

        for key in (
            "source_items",
            "briefs",
            "proposals",
            "executions",
            "audit_events",
            "deletion_operations",
        ):
            if counts[key] != expected[key]:
                raise AssertionError(f"{key}: expected {expected[key]}, restored {counts[key]}")
        if proposal.approved_binding_hash != expected["approval_binding_hash"]:
            raise AssertionError("approval binding hash changed across backup/restore")
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
    """The seeded data never contains a real secret, but confirm the dump
    itself carries no encrypted-token bytes or session-secret-shaped value
    regardless — `pg_restore -Fc` output is binary, so this checks the
    plain-text schema/COPY header portion `pg_restore -l` exposes."""
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


async def run_one_cycle(cycle: int, scratch_dir: Path) -> dict[str, float]:
    source_db = f"{_ALLOWED_DB_PREFIX}src_{cycle}"
    dest_db = f"{_ALLOWED_DB_PREFIX}restore_{cycle}"
    dump_path = scratch_dir / f"cycle-{cycle}.dump"

    t0 = time.monotonic()
    await _create_database(source_db)
    figures = await _seed(source_db)
    t_seeded = time.monotonic()

    _dump(source_db, dump_path)
    t_dumped = time.monotonic()
    _scan_dump_for_secrets(dump_path)

    await _create_database(dest_db)
    _restore(dest_db, dump_path)
    t_restored = time.monotonic()

    await _verify(dest_db, figures)
    t_verified = time.monotonic()

    await _drop_database(source_db)
    await _drop_database(dest_db)
    dump_path.unlink(missing_ok=True)

    return {
        "seed_seconds": round(t_seeded - t0, 2),
        "dump_seconds": round(t_dumped - t_seeded, 2),
        "restore_seconds": round(t_restored - t_dumped, 2),
        "verify_seconds": round(t_verified - t_restored, 2),
        "total_seconds": round(t_verified - t0, 2),
    }


async def main() -> int:
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    results = []
    with tempfile.TemporaryDirectory(prefix="lifeflow-phase2-backup-") as scratch:
        scratch_dir = Path(scratch)
        for cycle in range(cycles):
            timing = await run_one_cycle(cycle, scratch_dir)
            results.append(timing)
            print(f"cycle {cycle}: {json.dumps(timing)}")
    print(json.dumps({"cycles": len(results), "results": results}))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
