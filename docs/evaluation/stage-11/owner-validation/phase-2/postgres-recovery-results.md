# Stage 11A Phase 2 — PostgreSQL Outage and Recovery Results

**Status:** Complete · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) (S11A-P2-016 to 017)

## Outage and recovery (5 repetitions)

Real `docker compose stop db` / `docker compose start db` against the dev-compose container, exercised via `journey-d-dependency-health.spec.ts` (re-run 5× this phase):

| Context | Result | Evidence |
|---|---|---|
| Readiness checking | PASS — `/ready` returns 503 `{"status":"unavailable"}`; `/health` stays 200 (never touches a dependency) | `journey-d-dependency-health.spec.ts` |
| Ordinary API requests | PASS — request fails with a clean database-unavailable classification, no fabricated success | `classify_exception()` → `database_unavailable`, retryable=True |
| Ingestion / proposal generation / approval / execution preparation / deletion processing | PASS — none of these begin an external provider write without a durable pending row already committed; a DB outage during any of these stages simply fails the request before that row exists, or (if the row already exists) leaves it in a resumable state re-verified by the recovery sweeps | `test_execution_durability.py`, `test_deletion_engine_enqueue_resilience.py` re-run |
| Audit History pagination | PASS — fails cleanly with the same classification, no partial/misleading page | Manual rehearsal against `GET /audit-history` during a stopped-db window |

## Truthfulness

No success response was ever fabricated during any of the 5 outages — every affected request either failed with the closed `database_unavailable` classification or, for reads that don't require a live query (none exist on this path), was unaffected. `/health` never depends on PostgreSQL, confirmed unchanged across all 5 cycles.

## Recovery and consistency

- API and worker processes recovered cleanly after PostgreSQL returned in all 5 cycles — no restart required, confirmed by successful subsequent requests within the existing `docker compose ... --wait` health-check window.
- `uv run alembic heads` re-run after each of the 5 cycles: `0011 (head)` unchanged every time — single head, migrations intact.
- No partially committed transaction: PostgreSQL's own transactional guarantees mean a connection drop mid-transaction rolls back entirely; re-verified by row-count comparison before/after each cycle showing no orphaned partial state.
- No duplicate operation after reconnect: re-ran `test_action_concurrency.py` and the Phase 1 reset-repeatability harness (`test_stage11a_phase1_reset_repeatability.py`) immediately after a DB outage/recovery cycle — identical results to a no-outage baseline.

## No Redis-only state became authoritative

Confirmed by design and by test: every recovery decision (`recover_stale_operations`, `recover_stale_pending_executions`) reads exclusively from PostgreSQL row state (`heartbeat_at`, `attempt_count`, `outcome`) — Redis holds only transient job-queue metadata, never a fact PostgreSQL doesn't also durably record.
