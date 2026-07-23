# Stage 9 Delivery Phase 2 Completion Report

**Branch:** `stage-9-deletion-retention` (base `49f121a`). **Date:** 2026-07-23.
**Scope:** the durable deletion engine — imported-data deletion, retention
enforcement, and account deletion (anonymise-and-minimise) — behind one model,
one planner, and one worker. Not committed, tagged, or pushed. Delivery Phase 3
not begun.

## Executive verdict

**APPROVE DELIVERY PHASE 2 FOR REVIEW.**

Every capability in §1 of the brief is implemented against the ratified policy,
with accurate previews, typed confirmation, durable/bounded/resumable execution,
explicit derived-data handling, preserved pending/uncertain evidence, retention
enforcement using the same planner, and privacy-minimised account tombstones.
All existing tests pass, 35 focused backend tests and 6 focused frontend tests
were added, and every automated gate that this environment can run is green.
Two honest limitations are documented below (real provider *revoke* during
account deletion is wired as a no-op in demo/CI; the Playwright/eval suites are
listed with their run status) — neither is a defect in the shipped behaviour.

## Ratified policy implementation

ADR 0005 was extended with concrete decisions **D66–D72** before implementation.
Disconnect (unchanged) keeps imported data; delete-imported-data removes
LifeFlow's copy only; delete-memory stays the existing separate control; account
deletion anonymises-and-minimises; retention uses validated global env settings
(no table). All confirmed in `docs/architecture/adr/0005-stage9-privacy-hardening.md`.

## Migration and durable model

`alembic/versions/0011_data_deletion_operations.py` (additive; upgrade →
downgrade → re-upgrade verified; single head `0011`):

- `data_deletion_operations` — one content-free row per operation
  (`lifeflow_api.models.DataDeletionOperation`): closed `operation_type`
  (imported_data/retention/account_deletion) and `state`
  (previewed/pending/running/succeeded/partially_failed/failed/cancelled)
  enums; `scope_key`, `snapshot_cutoff`, `preview_expires_at`,
  `preview/preserved/deleted_counts_json`, `resume_cursor_json`,
  `attempt_count`, `heartbeat_at`, safe error code/message, `version`.
- Partial unique index `uq_data_deletion_operations_active_scope` — at most one
  *active* operation per (user, type, scope).
- `users`: `account_state` (active/deletion_pending/deleted), `deleted_at`,
  unique `deletion_subject_id` (retained-user anonymisation, D67).
- `source_items.created_at` — the snapshot boundary column (D68), plus retention
  support indexes on terminal timestamps.

## Preview architecture

`deletion_planner.count_imported_data_plan` and
`account_deletion.count_account_deletion_plan` are mutation-free and use the
exact scoping queries the worker uses, so counts equal what happens. A preview is
a durable `previewed` operation with a snapshot cutoff, per-category
`preview_counts`, disposition `preserved_counts`
(minimised-history, preserved-pending/uncertain, recomputed, source-reference-
removed), typed-confirmation phrase, and expiry. Tests assert preview counts
equal direct DB counts (`test_imported_preview_counts_match_database`) and that
no content or identifiers appear (`test_preview_is_owner_scoped_and_no_content`).

## Confirmation and idempotency

`deletion.confirm_operation`: exact phrase (422), expected version (409 stale),
non-expired preview (409), idempotent re-confirm; account confirm also sets
`deletion_pending` immediately. Two equivalent previews reuse the active
operation (`test_repeated_preview_reuses_active_operation`); the partial unique
index is the DB-level backstop. `claim_operation` is an atomic conditional
`UPDATE … RETURNING` (`test_claim_is_atomic` — second claimer gets `None`).

## Imported-data deletion semantics

`deletion_planner`: a `Signal`/`ActionProposal` references `SourceItem`s by
`external_id`. Fully-unsupported signals are deleted; mixed-source signals are
retained with deleted refs pruned; unapproved-unsupported proposals are deleted;
approved/executed proposals are minimised to content-free tombstones;
pending/uncertain executions are always preserved (proposal minimised). Proven
end-to-end by `test_imported_deletion_semantics` (account A gone, B intact, s1
deleted / s2 pruned / s3 untouched, p1 deleted / p2 minimised / p3 preserved /
p4 untouched, confirmed preference kept, memory evidence ref nulled).

## Derived-data planner

`apply_derived_decisions` is the single shared implementation used by both
imported-data (account scope) and retention (age scope) — `test 47` semantics
are guaranteed identical by construction. `minimise_proposal`/`minimise_execution`
clear payloads, rationale, approved payloads, recipients, and result JSON.

## Retained execution tombstones

Pending/uncertain executions are never deleted by any path
(`test_retention_deletes_expired_sources_and_preserves`,
`test_imported_deletion_semantics`); retained terminal executions are minimised
(`executed_payload_json == {}`, `result_json == {}`).

## Worker batching and recovery

`run_operation` claims, loops bounded batches (committing each, updating cursor +
deleted counts + heartbeat), and finalises with a safe terminal state and a
content-free audit tombstone. Recovery: `recover_stale_operations` requeues stale
`running` operations (`test_stale_running_operation_recovered`) or fails them
safe after max attempts (`test_stale_running_exhausted_attempts_fails_safe`), and
drains never-enqueued `pending` operations. Re-running a completed operation is a
no-op (`test_completed_operation_rerun_changes_nothing`).

## Retention enforcement

`retention.run_retention_step` (controllable clock, bounded batches) reuses
`apply_derived_decisions` for expired source evidence plus age-based deletion of
brief versions, unapproved proposals, terminal scheduled runs, and
expired/dismissed memory candidates — never pending/uncertain executions or
confirmed preferences. `scan_and_create_retention_operations` is idempotent per
day (`test_retention_scan_is_idempotent_across_ticks`) and horizon-sensitive
(`test_retention_horizon_alters_eligibility`); opt-in via
`RETENTION_ENFORCEMENT_ENABLED`.

## Account anonymisation and deletion

`account_deletion.run_account_deletion_step` (phase machine): revoke best-effort
+ clear local credentials + delete connected accounts → delete personal product
data (bounded) → minimise retained proposal/execution tombstones → anonymise the
terminal user row (random `deletion_subject_id`, cleared identity,
`account_state='deleted'`). `get_current_user` rejects a deleted account (session
invalidation). Proven by `test_account_deletion_anonymises_and_preserves_tombstones`,
`test_account_deletion_is_idempotent`, and
`test_account_deletion_revoke_failure_still_clears_credentials`.

## API and frontend

Routes (`privacy_deletion.py`): `POST /privacy/imported-data/{account_id}/preview`,
`POST /privacy/account-deletion/preview`,
`POST /privacy/deletion-operations/{id}/confirm|cancel`,
`GET /privacy/deletion-operations[/{id}]`. Content-free responses; 404 without
ownership leakage; 409 for invalid transition/stale version; 422 for bad
confirmation. Frontend: `connections/DeletionControls.tsx` — preview → exact-
phrase confirmation (double-click and wrong-phrase both blocked) → durable
progress polling; account deletion is a visually distinct high-risk control that
resets the client on success. Mutations are blocked while `deletion_pending`.

## Privacy and leakage review

Operation responses, audit metadata, logs, and the Redis payload carry only ids,
counts, states, and safe codes — never tokens, payloads, recipients, subjects,
provider ids, or the confirmation phrase. Sentinel/no-content assertions in
`test_preview_is_owner_scoped_and_no_content`,
`test_preview_and_confirm_imported_data` (response text has no seeded secrets),
and the id-only queue payload test (`test_deletion_queue`). No provider client is
imported by the deletion engine (`test_deletion_never_calls_provider`).

## Tests added

- Backend (35): `tests/test_deletion_engine.py` (22 — planner semantics,
  lifecycle, idempotency/recovery, retention, account deletion, snapshot),
  `tests/test_privacy_deletion_api.py` (11 — API preview/confirm/cancel/list/get,
  ownership 404, 422/409, mutation guard, session invalidation, Redis-down),
  `tests/test_deletion_queue.py` (2 — real-Redis drain, id-only payload, run to
  completion). `tests/test_worker_app.py` updated for the new cron/job.
- Frontend (6 new, 17 total in the connections suite): preview counts render,
  exact-phrase gating, wrong-phrase blocks submit, provider-not-deleted copy,
  distinct account control + stronger phrase, retention stays not-enforced, no
  audit timeline, no page-load side effects.

## Full verification results

| Gate | Result |
|---|---|
| Backend pytest (incl. new + real Redis) | **595 passed, 0 failed** (161s) |
| mypy strict | clean (78 files) |
| Ruff check / format | clean |
| Frontend vitest | **64 passed** (17 in the connections suite) |
| Frontend tsc / eslint / build | pass / pass / pass |
| Playwright e2e | **4 passed** (connections + demo-brief ×2 + demo-approvals) |
| Evals (det, actions) | baseline: precision 1.00, recall 0.94, **0 unsafe / 0 injection / 0 grounding** |
| Alembic 0010→0011→0010→0011 | verified; single head `0011` |
| Generated contracts | regenerate deterministically; only the intended deletion additions |
| detect-secrets (`scan --baseline`) | clean |
| gitleaks (full history, 21 commits) | no leaks found |
| .env.example live-secret validation | passed |
| pre-commit (all hooks) | pass (the detect-secrets hook's "unstaged baseline" notice is a working-tree artifact of uncommitted work, not a leak) |
| Real-Redis queue tests | 2 passed (localhost:6380) |
| Real-PostgreSQL engine/API tests | pass (localhost:5433, lifeflow_test) |

## Manual smoke-test results

See `docs/delivery/reports/stage-09-phase-2-manual-checklist.md`. The imported-
data delete, crash/resume, Redis-unavailable, retention, and account-deletion
flows are all reproduced by the automated integration tests against real
PostgreSQL (and, for the queue, real Redis); the checklist records the redacted
evidence and the demo-user procedure.

## Files changed

New backend: `deletion_ops.py`, `deletion_planner.py`, `account_deletion.py`,
`retention.py`, `deletion.py`, `privacy_deletion.py`,
`alembic/versions/0011_data_deletion_operations.py`. Modified: `models.py`,
`config.py`, `deps.py`, `main.py`, `worker_app.py`, `connected_accounts.py`,
`action_proposals.py`, `briefs.py`. New tests: `test_deletion_engine.py`,
`test_privacy_deletion_api.py`, `test_deletion_queue.py`; updated
`test_worker_app.py`. Frontend: `connections/DeletionControls.tsx`,
`connections/page.tsx`, `connections/page.test.tsx`, `lib/types.ts`,
`packages/contracts/*`. Docs: ADR 0005, this report + manual checklist,
`.env.example`, plus stage-plan/README/assumptions/threat-model/privacy-centre
updates.

## Delivery Phase 3 boundaries (not built here)

Audit-history UI (a read projection over the existing append-only `AuditEvent`),
rate limiting (Phase 4), and outage/telemetry hardening (Phase 5) are **not**
present — no audit timeline, no rate-limit middleware, no export-my-data, no new
connectors/scopes, no Gmail send, no Calendar update/delete, and no automatic
retry of uncertain provider outcomes.

## Focused safety remediation (2026-07-23, ADR 0005 D73–D74)

A post-approval focused round hardened two safety properties and added a genuine
end-to-end smoke (`apps/api/scripts/smoke_phase2.py`, 23/23 pass — see the manual
checklist):

- **D73 — confirmation bound to the reviewed plan.** Each preview persists a
  content-free `plan_fingerprint` (sha256 of affected record ids + planned
  dispositions) and `plan_policy_version`. Confirmation locks the operation row
  `FOR UPDATE`, recomputes the plan against the original snapshot, and refuses to
  run on any material disposition change (proposal approved, execution now
  pending/uncertain, dependency added/removed, mixed signal now fully
  unsupported, or policy bump) — returning **409 `preview_changed`** with a
  refreshed preview that requires a new confirmation. A later out-of-snapshot
  SourceItem that changes no listed disposition does not invalidate. Racers are
  serialised by the row lock, so two confirmers can never confirm different plan
  versions. The fingerprint exposes no content or provider identifiers.
- **D74 — real production provider revocation** is injected at the worker
  composition root (`worker_app.on_startup` → `google_wiring.build_account_revoker`,
  reusing the disconnect path's `revoke_token`). Attempted per account before
  local erasure, recorded as a safe `provider_revocations` count; a failure never
  blocks erasure and yields `partially_failed` (`provider_revoke_failed`); the
  credentials phase never re-runs on resume (no double revoke); no token,
  provider response, or raw exception ever enters logs/audits/state/responses.
  Demo/CI inject `None`; tests inject fake-success/fake-failure adapters. This
  supersedes the earlier "revoke is a no-op" limitation.

Focused-round tests: +9 backend (7 plan-binding in `test_deletion_engine.py`,
1 revoke-success/idempotent, 1 API `preview_changed` in
`test_privacy_deletion_api.py`) and +1 frontend already covered. Full suite:
**604 backend passed**; the deletion suites re-ran green (49) after the change.

## Delivery Phase 3 boundaries (not built here)

Audit-history UI (a read projection over the existing append-only `AuditEvent`),
rate limiting (Phase 4), and outage/telemetry hardening (Phase 5) are **not**
present — no audit timeline, no rate-limit middleware, no export-my-data, no new
connectors/scopes, no Gmail send, no Calendar update/delete, and no automatic
retry of uncertain provider outcomes.

## Commit recommendation

Recommend committing as the Delivery Phase 2 boundary on
`stage-9-deletion-retention` **after review**, in coherent commits (migration +
model; engine; API + guards; worker; frontend; docs/tests). Do not push, tag, or
begin Delivery Phase 3 until explicitly approved.
