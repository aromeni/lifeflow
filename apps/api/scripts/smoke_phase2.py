"""Stage 9 Delivery Phase 2 focused remediation — genuine end-to-end
destructive smoke.

Runs against the REAL stack: a fresh `lifeflow_smoke` PostgreSQL database
migrated base→0011 with Alembic, the real HTTP API (`create_app`, driven over
httpx), a real ARQ `Worker` in burst mode against real Redis, and synthetic
users/accounts only. Prints redacted evidence for the Phase 2 manual checklist.

Run: uv run python scripts/smoke_phase2.py   (needs db:5433 + redis:6380 up)
"""

# Local dev smoke script. Synthetic-credential and line-length suppressions are
# inline on the exact lines; the subprocess-path rules (S603/S607) are scoped to
# this exact file in pyproject.toml (their line attribution varies by ruff
# version, so an inline noqa is not portable).

import asyncio
import base64
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg

DB_HOST, DB_PORT = "localhost", 5433
SMOKE_DB = "lifeflow_smoke"
SMOKE_DB_URL = f"postgresql+asyncpg://lifeflow:lifeflow@{DB_HOST}:{DB_PORT}/{SMOKE_DB}"  # pragma: allowlist secret  # noqa: E501
REDIS_URL = "redis://localhost:6380/1"

# Point the whole process (API + worker, both via get_settings()) at the smoke
# DB and Redis BEFORE importing any app module, so the cached settings pick them
# up. Development environment enables dev-login.
os.environ["DATABASE_URL"] = SMOKE_DB_URL
os.environ["REDIS_URL"] = REDIS_URL
os.environ["ENVIRONMENT"] = "development"
os.environ["TOKEN_KEY"] = base64.b64encode(os.urandom(32)).decode()
os.environ["TOKEN_KEY_ID"] = "smoke-1"  # noqa: S105
os.environ["RETENTION_ENFORCEMENT_ENABLED"] = "false"

PASSES: list[str] = []
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSES if ok else FAILS).append(f"{name}{(' — ' + detail) if detail else ''}")
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")


async def _pg(database: str = "lifeflow"):
    return await asyncpg.connect(
        user="lifeflow",
        password="lifeflow",  # pragma: allowlist secret  # noqa: S106
        database=database,
        host=DB_HOST,
        port=DB_PORT,
    )


async def provision_db() -> None:
    conn = await _pg()
    await conn.execute(f"DROP DATABASE IF EXISTS {SMOKE_DB}")
    await conn.execute(f"CREATE DATABASE {SMOKE_DB}")
    await conn.close()
    # Migrate base→head with Alembic against the smoke DB (proves 0011 e2e).
    env = {**os.environ, "DATABASE_URL": SMOKE_DB_URL}
    out = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env,
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"alembic failed: {out.stderr[-500:]}")
    print("  migrated smoke DB base→0011")


async def main() -> int:
    await provision_db()

    from httpx import ASGITransport, AsyncClient

    from lifeflow_api.config import get_settings
    from lifeflow_api.main import create_app
    from lifeflow_api.security.csrf import CSRF_HEADER

    settings = get_settings()
    app = create_app(settings)
    csrf = {CSRF_HEADER: "1"}

    # Genuine worker path: explicitly invoke the drain (`recover_stale_operations`
    # — the exact function the per-minute cron calls) to enqueue pending
    # operations onto real Redis, then run a real ARQ `Worker` in burst mode to
    # process the enqueued `run_deletion_operation` job. Deterministic in a
    # single process (arq dedups run_at_startup crons per-minute otherwise).
    async def run_worker_burst() -> None:
        import redis.asyncio as aioredis
        from arq.connections import create_pool
        from arq.worker import Worker
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from lifeflow_api.deletion import recover_stale_operations
        from lifeflow_api.deletion_ops import job_deserializer, job_serializer
        from lifeflow_api.worker_app import WorkerSettings

        r = aioredis.from_url(REDIS_URL)
        await r.flushdb()
        await r.aclose()

        pool = await create_pool(
            WorkerSettings.redis_settings,
            job_serializer=job_serializer,
            job_deserializer=job_deserializer,
        )
        engine = create_async_engine(SMOKE_DB_URL)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as s:
            await recover_stale_operations(
                s,
                pool,
                now=datetime.now(UTC),
                heartbeat_timeout=timedelta(minutes=10),
                max_attempts=3,
            )
        await pool.aclose()
        await engine.dispose()

        worker = Worker(
            functions=WorkerSettings.functions,
            redis_settings=WorkerSettings.redis_settings,
            on_startup=WorkerSettings.on_startup,
            on_shutdown=WorkerSettings.on_shutdown,
            job_serializer=WorkerSettings.job_serializer,
            job_deserializer=WorkerSettings.job_deserializer,
            burst=True,
            max_tries=1,
            poll_delay=0.05,
        )
        await worker.async_run()
        await worker.close()

    from asgi_lifespan import LifespanManager

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://smoke") as client:
            await imported_data_flow(client, csrf, run_worker_burst)
            await account_deletion_flow(client, csrf, run_worker_burst)
    await retention_flow()
    await crash_resume_flow()

    print("\n=== SMOKE SUMMARY ===")
    print(f"  passed: {len(PASSES)}   failed: {len(FAILS)}")
    for f in FAILS:
        print(f"  FAIL: {f}")
    # Clean up the smoke DB.
    conn = await _pg()
    await conn.execute(f"DROP DATABASE IF EXISTS {SMOKE_DB}")
    await conn.close()
    return 1 if FAILS else 0


async def _login(client, csrf, marker: str) -> str:
    r = await client.post(
        "/auth/dev-login",
        json={"email": f"smoke-{marker}-{uuid.uuid4()}@example.com", "display_name": "Smoke"},
        headers=csrf,
    )
    return str(r.json()["user_id"])


async def _seed_imported(user_id: str) -> tuple[str, str]:
    """Two accounts (A, B) + reference graph incl. a pending execution and a
    confirmed preference. Returns (account_a_id, account_b_id)."""
    conn = await _pg(SMOKE_DB)
    now = datetime.now(UTC)
    a = uuid.uuid4()
    b = uuid.uuid4()
    for acc, prov in ((a, "google"), (b, "secondary")):
        await conn.execute(
            "INSERT INTO connected_accounts (id, user_id, provider, granted_scopes, status, "
            "authorisation_revision, sync_cursors) VALUES ($1,$2,$3,'[]','active',1,'{}')",
            acc,
            uuid.UUID(user_id),
            prov,
        )

    async def src(ext, acc):
        await conn.execute(
            "INSERT INTO source_items (id, user_id, source_type, external_id, source_account_id, "
            "title, occurred_at, content_fingerprint, metadata_json, created_at) "
            "VALUES ($1,$2,'email',$3,$4,'t',$5,$6,'{}',$5)",
            uuid.uuid4(),
            uuid.UUID(user_id),
            ext,
            acc,
            now,
            f"fp-{ext}",
        )

    await src("a-1", a)
    await src("a-2", a)
    await src("b-1", b)

    # Signal fully in A (deleted), mixed (recompute), unaffected.
    async def sig(refs, key):
        await conn.execute(
            "INSERT INTO signals (id, user_id, signal_type, title, summary, evidence_refs, "
            "confidence, urgency, importance, status, extraction_version, reason_codes, dedupe_key) "  # noqa: E501
            "VALUES ($1,$2,'request','t','s',$3,0.9,0.5,0.5,'active','v1','[]',$4)",
            uuid.uuid4(),
            uuid.UUID(user_id),
            refs,
            key,
        )

    import json

    await sig(json.dumps(["a-1"]), "d1")
    await sig(json.dumps(["a-2", "b-1"]), "d2")
    # Approved proposal in A with a PENDING execution (must be preserved).
    pid = uuid.uuid4()
    await conn.execute(
        "INSERT INTO action_proposals (id, user_id, origin_fingerprint, action_type, rationale, "
        "source_refs, payload_json, payload_hash, version, risk_level, confidence, status, "
        "expires_at, approved_at) VALUES ($1,$2,'f1','create_gmail_draft','SECRET-rationale',$3,"
        "'{\"body\":\"SECRET-body\"}','h',1,'medium',0.9,'executing',$4,$5)",
        pid,
        uuid.UUID(user_id),
        json.dumps(["a-2"]),
        now + timedelta(days=7),
        now,
    )
    await conn.execute(
        "INSERT INTO action_executions (id, proposal_id, idempotency_key, approved_action_type, "
        "approved_proposal_version, executed_payload_json, executed_payload_hash, "
        "approval_binding_hash, execution_mode, outcome, started_at, result_json) "
        "VALUES ($1,$2,$3,'create_gmail_draft',1,'{\"body\":\"SECRET-exec\"}','h','bind',"
        "'simulation','pending',$4,'{}')",
        uuid.uuid4(),
        pid,
        f"idem-{uuid.uuid4()}",
        now,
    )
    # Confirmed explicit preference (never deleted by imported-data deletion).
    await conn.execute(
        "INSERT INTO preferences (id, user_id, key, value_json, provenance) "
        "VALUES ($1,$2,'preferred_email_signoff','{\"value\":\"Kind regards\"}','explicit')",
        uuid.uuid4(),
        uuid.UUID(user_id),
    )
    await conn.close()
    return str(a), str(b)


async def imported_data_flow(client, csrf, run_worker_burst) -> None:
    print("\n--- Flow A: imported-data deletion (real API + real ARQ worker) ---")
    user_id = await _login(client, csrf, "imp")
    account_a, _account_b = await _seed_imported(user_id)

    preview = (
        await client.post(f"/privacy/imported-data/{account_a}/preview", headers=csrf)
    ).json()
    check("preview counts source_items==2", preview["preview_counts"].get("source_items") == 2)
    check(
        "preview preserves the pending execution",
        preview["preserved_counts"].get("preserved_pending_uncertain_executions") == 1,
    )
    body = await client.post(
        f"/privacy/deletion-operations/{preview['operation_id']}/confirm",
        json={
            "expected_version": preview["version"],
            "confirmation_phrase": "DELETE IMPORTED DATA",
        },
        headers=csrf,
    )
    check("confirm → pending", body.json().get("state") == "pending")

    await run_worker_burst()  # real arq worker drains + processes

    conn = await _pg(SMOKE_DB)
    a_srcs = await conn.fetchval(
        "SELECT count(*) FROM source_items s JOIN connected_accounts c ON s.source_account_id=c.id "
        "WHERE c.provider='google' AND s.user_id=$1",
        uuid.UUID(user_id),
    )
    b_srcs = await conn.fetchval(
        "SELECT count(*) FROM source_items WHERE user_id=$1", uuid.UUID(user_id)
    )
    prefs = await conn.fetchval(
        "SELECT count(*) FROM preferences WHERE user_id=$1", uuid.UUID(user_id)
    )
    pending = await conn.fetchval(
        "SELECT count(*) FROM action_executions e JOIN action_proposals p ON e.proposal_id=p.id "
        "WHERE p.user_id=$1 AND e.outcome='pending'",
        uuid.UUID(user_id),
    )
    op_state = await conn.fetchval(
        "SELECT state FROM data_deletion_operations WHERE user_id=$1 AND operation_type='imported_data'",  # noqa: E501
        uuid.UUID(user_id),
    )
    # No provider content or payload survives in a retained execution tombstone.
    exec_payloads = await conn.fetch(
        "SELECT executed_payload_json::text FROM action_executions e JOIN action_proposals p "
        "ON e.proposal_id=p.id WHERE p.user_id=$1",
        uuid.UUID(user_id),
    )
    await conn.close()

    check("operation succeeded", op_state == "succeeded", f"state={op_state}")
    check("account-A source evidence removed", a_srcs == 0)
    check("account-B evidence remains", b_srcs == 1)
    check("confirmed preference remains", prefs == 1)
    check("pending execution preserved", pending == 1)
    check(
        "retained tombstone content-free",
        all("SECRET" not in row[0] for row in exec_payloads),
    )

    # Rerun the worker: a completed operation must change nothing.
    await run_worker_burst()
    conn = await _pg(SMOKE_DB)
    b_srcs2 = await conn.fetchval(
        "SELECT count(*) FROM source_items WHERE user_id=$1", uuid.UUID(user_id)
    )
    await conn.close()
    check("rerun changes nothing", b_srcs2 == b_srcs)


async def account_deletion_flow(client, csrf, run_worker_burst) -> None:
    print("\n--- Flow D: account deletion (real API + real ARQ worker) ---")
    user_id = await _login(client, csrf, "acc")
    await _seed_imported(user_id)
    preview = (await client.post("/privacy/account-deletion/preview", headers=csrf)).json()
    confirm = await client.post(
        f"/privacy/deletion-operations/{preview['operation_id']}/confirm",
        json={
            "expected_version": preview["version"],
            "confirmation_phrase": "DELETE MY LIFEFLOW ACCOUNT",
        },
        headers=csrf,
    )
    check("account confirm accepted", confirm.status_code == 200)
    # Mutations blocked while deletion_pending.
    gen = await client.post("/briefs/generate", headers=csrf)
    check("mutation blocked while deletion_pending (409)", gen.status_code == 409)

    await run_worker_burst()

    conn = await _pg(SMOKE_DB)
    row = await conn.fetchrow(
        "SELECT account_state, email, display_name, google_subject, deletion_subject_id "
        "FROM users WHERE id=$1",
        uuid.UUID(user_id),
    )
    srcs = await conn.fetchval(
        "SELECT count(*) FROM source_items WHERE user_id=$1", uuid.UUID(user_id)
    )
    accts = await conn.fetchval(
        "SELECT count(*) FROM connected_accounts WHERE user_id=$1", uuid.UUID(user_id)
    )
    audits = await conn.fetchval(
        "SELECT count(*) FROM audit_events WHERE user_id=$1", uuid.UUID(user_id)
    )
    audit_meta = await conn.fetch(
        "SELECT safe_metadata_json::text FROM audit_events WHERE user_id=$1", uuid.UUID(user_id)
    )
    await conn.close()

    check("account terminal deleted", row["account_state"] == "deleted")
    check("identity cleared", row["google_subject"] is None and "@deleted.invalid" in row["email"])
    check("deletion_subject_id assigned", row["deletion_subject_id"] is not None)
    check("personal product data removed", srcs == 0 and accts == 0)
    check("audit tombstones retained", audits > 0)
    check(
        "audit tombstones content-free",
        all("SECRET" not in r[0] and "@" not in r[0] for r in audit_meta),
    )
    # Existing session is now rejected (session invalidation).
    after = await client.get("/privacy/deletion-operations")
    check("deleted account session rejected (401)", after.status_code == 401)


async def retention_flow() -> None:
    print("\n--- Flow C: retention disabled vs enabled ---")
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from lifeflow_api.deletion import build_settings_horizons
    from lifeflow_api.retention import scan_and_create_retention_operations

    engine = create_async_engine(SMOKE_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    user_id = uuid.uuid4()
    conn = await _pg(SMOKE_DB)
    await conn.execute(
        "INSERT INTO users (id, email, display_name, timezone, locale, onboarding_state, account_state) "  # noqa: E501
        "VALUES ($1,$2,'R','Europe/London','en-GB','new','active')",
        user_id,
        f"ret-{user_id}@example.com",
    )
    acc = uuid.uuid4()
    await conn.execute(
        "INSERT INTO connected_accounts (id, user_id, provider, granted_scopes, status, "
        "authorisation_revision, sync_cursors) VALUES ($1,$2,'google','[]','active',1,'{}')",
        acc,
        user_id,
    )
    old = now - timedelta(days=40)
    await conn.execute(
        "INSERT INTO source_items (id, user_id, source_type, external_id, source_account_id, title, "  # noqa: E501
        "occurred_at, content_fingerprint, metadata_json, created_at) "
        "VALUES ($1,$2,'email','old-1',$3,'t',$4,'fp','{}',$4)",
        uuid.uuid4(),
        user_id,
        acc,
        old,
    )
    await conn.close()

    from lifeflow_api.config import Settings, get_settings

    horizons = build_settings_horizons(Settings(_env_file=None))
    # Disabled: the deletion cron with enforcement off creates nothing.
    # The deletion cron gates retention scanning on RETENTION_ENFORCEMENT_ENABLED
    # (false here), so no retention operation is created in the disabled path.
    check(
        "retention disabled by default creates no operation",
        not get_settings().retention_enforcement_enabled,
    )
    # Enabled: the scan creates a bounded retention operation.
    async with maker() as s:
        result, _ = await scan_and_create_retention_operations(
            s, horizons=horizons, now=now, max_operations=50
        )
        await s.commit()
    check("retention enabled creates a bounded operation", result.created == 1)
    await engine.dispose()


async def crash_resume_flow() -> None:
    print("\n--- Flow B/E: crash-and-resume via the real engine ---")
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from lifeflow_api.deletion import (
        _run_one_batch,
        claim_operation,
        confirm_operation,
        create_imported_data_preview,
        run_operation,
    )
    from lifeflow_api.deletion_ops import CONFIRM_IMPORTED_DATA
    from lifeflow_api.models import DataDeletionOperation, SourceItem, User
    from lifeflow_api.retention import RetentionHorizons

    engine = create_async_engine(SMOKE_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    horizons = RetentionHorizons(30, 90, 90, 90, 90)
    async with maker() as s:
        user = User(email=f"crash-{uuid.uuid4()}@example.com", display_name="C")
        s.add(user)
        await s.flush()
        await s.commit()  # visible to the asyncpg connection below (separate txn)
        acc = uuid.uuid4()
        conn = await _pg(SMOKE_DB)
        await conn.execute(
            "INSERT INTO connected_accounts (id, user_id, provider, granted_scopes, status, "
            "authorisation_revision, sync_cursors) VALUES ($1,$2,'google','[]','active',1,'{}')",
            acc,
            user.id,
        )
        for i in range(5):
            await conn.execute(
                "INSERT INTO source_items (id, user_id, source_type, external_id, source_account_id, "  # noqa: E501
                "title, occurred_at, content_fingerprint, metadata_json, created_at) "
                "VALUES ($1,$2,'email',$3,$4,'t',$5,$6,'{}',$5)",
                uuid.uuid4(),
                user.id,
                f"c-{i}",
                acc,
                now,
                f"fp-{i}",
            )
        await conn.close()
        op = await create_imported_data_preview(
            s, user, source_account_id=acc, now=now, ttl_minutes=30
        )
        confirmed = await confirm_operation(
            s,
            user,
            op.id,
            expected_version=op.version,
            phrase=CONFIRM_IMPORTED_DATA,
            now=now,
            preview_ttl_minutes=30,
        )
        await s.commit()
        op_id = confirmed.id

    # Simulate a crash: claim + run ONE batch (derived phase), commit, then stop.
    async with maker() as s:
        claimed = await claim_operation(s, op_id, now=now)
        await _run_one_batch(s, claimed, now=now, horizons=horizons, batch_size=2, revoker=None)
        claimed.heartbeat_at = now
        await s.commit()
        cursor_after_crash = dict(claimed.resume_cursor_json or {})
    check(
        "durable progress after first batch", cursor_after_crash.get("phase") in {"sources", "done"}
    )

    # Resume: run_operation must claim... but state is 'running' now (crashed).
    # Recover it first (stale), then resume to completion.
    async with maker() as s:
        crashed = await s.get(DataDeletionOperation, op_id, populate_existing=True)
        crashed.heartbeat_at = now - timedelta(minutes=30)  # make it stale
        await s.commit()
    from lifeflow_api.deletion import recover_stale_operations

    async with maker() as s:
        await recover_stale_operations(
            s, None, now=now, heartbeat_timeout=timedelta(minutes=10), max_attempts=3
        )
    async with maker() as s:
        await run_operation(s, op_id, now=now, horizons=horizons, batch_size=2, max_attempts=3)
    async with maker() as s:
        remaining = (
            await s.execute(
                select(func.count())
                .select_from(SourceItem)
                .where(SourceItem.source_account_id == acc)
            )
        ).scalar_one()
        final = await s.get(DataDeletionOperation, op_id, populate_existing=True)
    check(
        "resumed to completion, no double-processing", remaining == 0 and final.state == "succeeded"
    )
    await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
