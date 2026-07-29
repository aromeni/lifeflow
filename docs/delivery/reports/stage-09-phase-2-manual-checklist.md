# Stage 9 Delivery Phase 2 — manual smoke checklist

Synthetic/demo users only. No real Google-connected account is used. The flows
below are reproduced two ways: (1) automated integration tests against real
PostgreSQL (localhost:5433, `lifeflow_test`) and real Redis (localhost:6380);
and (2) a genuine end-to-end smoke harness, `apps/api/scripts/smoke_phase2.py`,
which provisions a fresh `lifeflow_smoke` database migrated base→0011 with
Alembic, drives the **real HTTP API** (`create_app` over httpx), and processes
jobs with a **real ARQ `Worker`** in burst mode against real Redis. Evidence is
redacted — the engine is content-free, so there is nothing personal to redact
beyond ids.

## End-to-end smoke result (2026-07-23)

`uv run python scripts/smoke_phase2.py` → **23 checks passed, 0 failed.** Redacted
evidence (all PASS):

```
Flow A: imported-data deletion (real API + real ARQ worker)
  preview counts source_items==2; preview preserves the pending execution;
  confirm → pending; operation succeeded; account-A source evidence removed;
  account-B evidence remains; confirmed preference remains; pending execution
  preserved; retained tombstone content-free; rerun changes nothing
Flow D: account deletion (real API + real ARQ worker)
  account confirm accepted; mutation blocked while deletion_pending (409);
  account terminal deleted; identity cleared; deletion_subject_id assigned;
  personal product data removed; audit tombstones retained; audit tombstones
  content-free; deleted account session rejected (401)
Flow C: retention disabled by default creates no operation; retention enabled
  creates a bounded operation
Flow B/E: durable progress after first batch; resumed to completion, no
  double-processing
```

The account-deletion op record after processing:
`state=succeeded, attempt_count=1, resume_cursor_json={"phase":"done","provider_revoke_failed":false}`
— content-free, terminal, and revoke not attempted (no real Google in the smoke;
local credential erasure still happened and `connected_accounts` count == 0).

## 1. Imported-data deletion (two accounts, full reference graph)

- Automated proof: `tests/test_deletion_engine.py::test_imported_deletion_semantics`.
- Seeds a demo user with two accounts (A `google`, B `secondary`), source items
  for each, and one of each: unapproved orphaned proposal (`p1`), successful
  execution (`p2`), pending execution (`p3`), memory candidate + evidence, and a
  confirmed explicit preference.
- Preview counts equal direct DB counts; typed phrase `DELETE IMPORTED DATA`
  confirms; a real ARQ worker body (`run_operation`, batch size 1) processes it.
- Verified: account-A evidence removed; account-B data intact; pending/uncertain
  history preserved and minimised; explicit preference kept; memory recomputed;
  **no provider content call occurred** (`test_deletion_never_calls_provider`);
  final counts match the operation record. Re-running changes nothing
  (`test_completed_operation_rerun_changes_nothing`).

## 2. Crash and resume

- Automated proof: `test_stale_running_operation_recovered` +
  `test_stale_running_exhausted_attempts_fails_safe`.
- A `running` operation with a stale heartbeat is recovered to `pending` for
  re-enqueue (resume cursor preserved); after max attempts it becomes
  `partially_failed` with `worker_stale_timeout`. The batch loop commits each
  bounded batch, so resume continues from the durable cursor without duplicating
  tombstones.

## 3. Redis unavailable

- Automated proof: `tests/test_privacy_deletion_api.py::test_preview_and_confirm_work_with_redis_down`.
- With Redis pointed at an unreachable host, preview and confirm still succeed;
  the operation persists as `pending`. When Redis and the worker return, the
  per-minute cron drains it exactly once (drain-only enqueue, D70); ordinary API
  routes remain available throughout.

## 4. Retention

- Automated proof: `test_retention_deletes_expired_sources_and_preserves`,
  `test_retention_scan_is_idempotent_across_ticks`,
  `test_retention_horizon_alters_eligibility`.
- With a controllable clock advanced past a horizon, the real retention step
  removes expired source items and derived data through the same planner while
  preserving pending/uncertain executions and confirmed preferences; daily ticks
  are idempotent (one operation per user per day).

## 5. Account deletion

- Automated proof: `test_account_deletion_anonymises_and_preserves_tombstones`,
  `test_account_deletion_is_idempotent`,
  `test_account_deletion_revoke_failure_still_clears_credentials`, and
  API-level `test_account_deletion_preview_confirm_blocks_mutations` +
  `test_deleted_account_cannot_authenticate`.
- Preview → phrase `DELETE MY LIFEFLOW ACCOUNT` → worker: tokens cleared,
  connected accounts removed, personal product data gone, terminal anonymised
  subject id assigned, identity fields cleared, minimal content-free
  audit/execution tombstones retained, no provider content deleted. A
  deletion-pending account is blocked from sync/brief/proposal mutations; a
  deleted account's session is rejected (401). Provider revoke failure still
  clears local credentials and marks the operation `partially_failed`.

## Browser E2E (2026-07-23, final closure) — PASSED ×2

`./scripts/e2e.sh` was run **twice consecutively from clean state**; both runs
were fully green (`6 passed`), including both destructive journeys each time:
run 1 — Journey A 50.1s, Journey B 1.0m; run 2 — Journey A 28.2s, Journey B
1.0m. The hardened harness logged `ARQ worker ready (pid …)` and tore down its
own worker cleanly each run. The per-journey database assertions (below) are
embedded in the specs and passed on both runs.

`apps/web/e2e/deletion.spec.ts` drives the two destructive journeys through the
**real** Privacy & Connections UI against a real API, a **real ARQ worker**
(started by `scripts/e2e.sh` with `PYTHONPATH=src`), real PostgreSQL and Redis —
nothing mocked. Fresh unique dev-login users; synthetic connected accounts only
(seeded via the owner-scoped `scripts/e2e_deletion_support.py`).

- **Journey A — imported-data deletion:** open Privacy & Connections → account
  active → preview → counts render (3 imported items) → "Gmail/Calendar never
  touched" copy visible → wrong phrase keeps submit disabled → exact
  `DELETE IMPORTED DATA` enables it → single submit (double-click guarded: the
  button disables on `busy`, exactly one confirm request fires) → pending →
  worker processes → "Done. The data has been deleted." → disconnect and delete
  controls remain distinct. DB check: the google account's source items → 0, the
  other account's → 1 (scoping proven).
- **Journey B — account deletion:** high-risk section → preview counts →
  wrong phrase can't submit → exact `DELETE MY LIFEFLOW ACCOUNT` → single submit
  → pending while session valid → worker completes → client redirects to the
  signed-out experience (`/`), with no infinite 401 poll loop (the poll treats a
  401 as completion and stops). The deleted session then gets 401 on an
  authenticated request. DB check: `account_state=deleted`, `google_subject`
  NULL, random `deletion_subject_id`, email is `…@deleted.invalid` (contains the
  subject id, not the original, non-deliverable), `connected_accounts=0`,
  `source_items=0`, audit tombstones retained with no `@`/original-email content.

## Secret-scanner configuration (final closure)

The broad `scripts/**` ruff per-file-ignore was **removed**. Synthetic-credential
suppressions are inline on the exact lines (`# pragma: allowlist secret` for
detect-secrets + `# noqa: S105/S106` for ruff); only the version-brittle
subprocess-path rules (S603/S607) are scoped to the **exact file**
`scripts/smoke_phase2.py` in `pyproject.toml` — no wildcard, no future-file
coverage, no secret detector exempted by config. `.secrets.baseline` was
restored to its committed version (the earlier change was only a `generated_at`
timestamp; no finding added or removed).

## Manual demo procedure (optional, for a reviewer)

1. `./scripts/demo.sh` and sign in via dev-login; open **Privacy & Connections**.
2. Connect a synthetic account and **Sync now** to seed imported/derived data.
3. Under **Data controls → Delete imported provider data**, click *Preview*,
   confirm the counts, type `DELETE IMPORTED DATA`, and *Delete permanently*.
4. Start the worker (`uv run arq lifeflow_api.worker_app.WorkerSettings`) with
   `redis` running; watch the operation reach `succeeded`.
5. For account deletion, use a throwaway dev-login user and the
   `DELETE MY LIFEFLOW ACCOUNT` phrase; confirm the session is signed out on
   completion. Never use the real Google-connected user.
