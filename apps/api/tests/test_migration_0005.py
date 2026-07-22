"""Migration 0005 upgrade/downgrade behaviour with populated Stage 6 records.

Runs Alembic against a dedicated scratch database (never lifeflow or
lifeflow_test) so the cycle is exercised with real rows: legacy rows are
backfilled on upgrade, survive a downgrade, and are re-backfilled on the
next upgrade.
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest

pytestmark = pytest.mark.integration

API_ROOT = Path(__file__).resolve().parents[1]
MIG_DB = "lifeflow_migration_test"
MIG_URL = (
    f"postgresql+asyncpg://lifeflow:lifeflow@localhost:5433/{MIG_DB}"  # pragma: allowlist secret
)
ADMIN = {
    "user": "lifeflow",
    "password": "lifeflow",  # pragma: allowlist secret
    "host": "localhost",
    "port": 5433,
}


def _alembic(*args: str) -> None:
    result = subprocess.run(  # noqa: S603 — fixed argv, test-only
        [sys.executable, "-m", "alembic", *args],
        cwd=API_ROOT,
        env={**os.environ, "DATABASE_URL": MIG_URL},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stderr}"


async def _columns(conn: asyncpg.Connection, table: str) -> set[str]:
    rows = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = $1", table
    )
    return {row["column_name"] for row in rows}


async def test_migration_0005_backfills_and_downgrades_with_populated_records() -> None:
    admin = await asyncpg.connect(database="lifeflow", **ADMIN)
    await admin.execute(f"DROP DATABASE IF EXISTS {MIG_DB} WITH (FORCE)")
    await admin.execute(f"CREATE DATABASE {MIG_DB}")
    await admin.close()
    try:
        _alembic("upgrade", "0004")

        user_id, proposal_id, execution_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        payload = {"title": "Legacy task", "notes": "Pre-0005 row", "due_at": None}
        conn = await asyncpg.connect(database=MIG_DB, **ADMIN)
        await conn.execute(
            "INSERT INTO users (id, email, display_name, timezone, locale, onboarding_state) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            user_id,
            "legacy@example.test",
            "Legacy",
            "Europe/London",
            "en-GB",
            "complete",
        )
        await conn.execute(
            "INSERT INTO action_proposals (id, user_id, action_type, rationale, source_refs, "
            "payload_json, risk_level, confidence, status, expires_at) "
            "VALUES ($1, $2, $3, $4, $5::json, $6::json, $7, $8, $9, NULL)",
            proposal_id,
            user_id,
            "create_task",
            "Legacy rationale",
            json.dumps(["em-001"]),
            json.dumps(payload),
            "low",
            0.9,
            "proposed",
        )
        await conn.execute(
            "INSERT INTO action_executions (id, proposal_id, idempotency_key, result_json) "
            "VALUES ($1, $2, $3, $4::json)",
            execution_id,
            proposal_id,
            "legacy-key",
            json.dumps({"status": "simulated"}),
        )
        await conn.close()

        # Upgrade with data: legacy rows must be backfilled before the new
        # NOT NULL constraints activate.
        _alembic("upgrade", "0005")
        conn = await asyncpg.connect(database=MIG_DB, **ADMIN)
        proposal = await conn.fetchrow(
            "SELECT origin_fingerprint, payload_hash, version, expires_at "
            "FROM action_proposals WHERE id = $1",
            proposal_id,
        )
        assert proposal is not None
        assert len(proposal["origin_fingerprint"]) == 64
        assert len(proposal["payload_hash"]) == 64
        assert proposal["version"] == 1
        assert proposal["expires_at"] is not None
        execution = await conn.fetchrow(
            "SELECT approved_action_type, approved_proposal_version, executed_payload_json, "
            "executed_payload_hash, approval_binding_hash FROM action_executions WHERE id = $1",
            execution_id,
        )
        assert execution is not None
        assert execution["approved_action_type"] == "create_task"
        assert execution["approved_proposal_version"] == 1
        assert json.loads(execution["executed_payload_json"]) == payload
        assert execution["executed_payload_hash"] == proposal["payload_hash"]
        assert len(execution["approval_binding_hash"]) == 64
        await conn.close()

        # Downgrade with data: columns and constraints go, the rows stay.
        _alembic("downgrade", "0004")
        conn = await asyncpg.connect(database=MIG_DB, **ADMIN)
        proposal_columns = await _columns(conn, "action_proposals")
        assert "origin_fingerprint" not in proposal_columns
        assert "approved_payload_json" not in proposal_columns
        execution_columns = await _columns(conn, "action_executions")
        assert "executed_payload_json" not in execution_columns
        assert await conn.fetchval("SELECT count(*) FROM action_proposals") == 1
        assert await conn.fetchval("SELECT count(*) FROM action_executions") == 1
        await conn.close()

        # A second upgrade re-backfills the (now legacy-shaped) rows.
        _alembic("upgrade", "0005")
        conn = await asyncpg.connect(database=MIG_DB, **ADMIN)
        refilled = await conn.fetchrow(
            "SELECT origin_fingerprint, version FROM action_proposals WHERE id = $1", proposal_id
        )
        assert refilled is not None
        assert len(refilled["origin_fingerprint"]) == 64 and refilled["version"] == 1
        await conn.close()
    finally:
        admin = await asyncpg.connect(database="lifeflow", **ADMIN)
        await admin.execute(f"DROP DATABASE IF EXISTS {MIG_DB} WITH (FORCE)")
        await admin.close()
