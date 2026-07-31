# Stage 11A Phase 2 — Acceptance Matrix

**Status:** In progress · **Date:** 2026-07-31

Companion: [../../../../delivery/stage-11a-phase-2-plan.md](../../../../delivery/stage-11a-phase-2-plan.md) · [failure-scenario-inventory.md](failure-scenario-inventory.md) · [defect-register.md](defect-register.md)

Built before editing, per the governing task instruction. Every row records: failure introduced, timing, expected user-visible/DB/Redis state, expected provider-call count, recovery mechanism, prohibited behaviour, repetitions, evidence, result. "Existing evidence, re-run" means the cited file already existed before this phase and was re-executed fresh as part of this phase's verification, not merely cited from memory. "New" means built in this phase.

## API restart

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-001 | Idle API restart: stop while no operation active, verify `/health`+`/ready` degrade truthfully then recover, no durable data loss | 3 | Existing: `journey-d-dependency-health.spec.ts` (health/ready semantics) + manual `docker compose restart`/API kill-restart during this phase; DB row counts compared before/after | PASS |
| S11A-P2-002 | API restart during synthetic Gmail/Calendar ingestion: terminate mid-`import_sources`, restart, resume safely, zero duplicate `SourceItem` rows | 3 | Existing: `test_demo_start_twice_does_not_duplicate` (idempotent re-import contract) re-run; new manual kill-mid-import rehearsal this phase, row counts compared | PASS |
| S11A-P2-003 | API restart before the provider receives a write: durable `pending` `ActionExecution` row exists before any provider call | 3 | Existing: `action_proposal_service.py::execute()` docstring/commit-before-call contract (lines 764-769) + `test_execution_durability.py` re-run | PASS |
| S11A-P2-004 | API restart after the provider accepts a write but before confirmation is received (uncertain): zero automatic replay, at most one synthetic provider object, restart never re-invokes the executor | 10 per action type (Gmail draft, Calendar event) | New: `apps/api/tests/test_stage11a_phase2_uncertain_write_repeatability.py` (20 total cycles) + existing `journey-b-uncertain-write.spec.ts` (real OS-level process restart, 1 run, re-run 3× this phase) | PASS |

## Web-process restart

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-005 | Web process restart while viewing Today/Approvals/Connections/Audit History/Settings: safe error state, no blank/false-success state, reload recovers, pending approvals durable, no duplicate mutation on reconnect | 3 | New: manual owner walkthrough (`manual-walkthrough.md`) driving `pnpm dev` kill/restart against each of the 5 screens; existing `stage10-outage-notice-fixture.spec.ts`/`stage10-uncertain-execution-fixture.spec.ts` re-run for the notice-rendering half of this claim | PASS |

## Worker crash

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-006 | Worker crash before claiming a job: job remains claimable, no loss | 3 | Existing: `journey-c-worker-outage-recovery.spec.ts` (no worker started at all — the strictest form of "before claiming") re-run 3× | PASS |
| S11A-P2-007 | Worker crash with two competing workers: atomic `claim_operation` UPDATE prevents duplicate ownership, operation completes exactly once | 3 | Existing: `journey-c-worker-outage-recovery.spec.ts` (spawns 2 real worker processes) re-run 3× | PASS |
| S11A-P2-008 | Worker crash after durable pending execution but before provider write, and immediately after provider write: uncertain outcome, never replayed | 10 per action type (shared evidence with S11A-P2-004 — the durability checkpoint is process-agnostic: a fresh `ActionProposalService` instance standing in for a post-restart worker hits the identical DB-row short-circuit) | New: `test_stage11a_phase2_uncertain_write_repeatability.py` | PASS |
| S11A-P2-009 | Worker crash during deletion batching: resumes from `resume_cursor_json`, not from scratch | 3 | Existing: `deletion.py::run_operation`/`_run_imported_data_batch` checkpoint contract + `test_stage11a_phase1_reset_repeatability.py` (10 full cycles through the real worker body) re-run 3× this phase | PASS |
| S11A-P2-010 | Worker crash during scheduled brief generation: no duplicate brief | 3 | Existing: `Brief` unique `(user_id, local_brief_date)` constraint + deterministic job id (ADR 0004 D48/D49) — `test_scheduled_briefs_enqueue_resilience.py` re-run 3× | PASS |
| S11A-P2-011 | Worker restart drains recoverable backlog; no job silently lost | 3 | Existing: `recover_stale_operations`/`recover_stale_pending_executions` cron sweeps + `test_execution_recovery_sweep.py` re-run 3× | PASS |

## Scheduler interruption

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-012 | Scheduler (arq cron loop) stopped before/during daily brief scheduling, stale-execution recovery, pending-deletion drainage, pending-scheduled-brief drainage: no duplicate entry, bounded recovery, uncertain writes never replayed | 3 each | Existing: `docs/delivery/runbooks/worker-recovery.md`'s documented arq in-progress-key TTL self-heal, independently re-verified this phase against the installed `arq==0.28.0` source (`worker.py:450-465,690-698`, `cron.py`/`worker.py:758` job-id format `f'{name}:{next_run_ms}'`) — see method note below; plus 3 re-runs each of `test_scheduled_briefs_enqueue_resilience.py`, `test_deletion_engine_enqueue_resilience.py`, `test_execution_recovery_sweep.py` | PASS |

**Method note (S11A-P2-012):** the in-progress-key TTL self-heal is `arq` library-internal behaviour (`worker.py::_start_job`), not LifeFlow application code — LifeFlow only supplies the cron function list. Rather than write a fragile unit test against a third-party library's private scheduling internals (a low-value, high-maintenance test of code this project does not own or control), this phase independently re-read and confirmed the exact mechanism against the pinned, installed `arq==0.28.0` source, cross-checked line-for-line against the runbook's existing description. LifeFlow's own duplicate-prevention layer on top of this (DB unique constraint + deterministic job id, ADR 0004 D48/D49) *is* application code and *is* covered by the re-run tests above.

## Redis outage and recovery

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-013 | Redis failure during ordinary read traffic, rate limiting, worker enqueue, deletion enqueue, scheduled-brief enqueue, readiness checks: `/health` independent, `/ready` reports `degraded_dependencies`, fail-open only for rate limiting, DB guards remain the source of truth, no raw identifier exposed | 5 | Existing: `journey-d-dependency-health.spec.ts` (real `docker compose stop/start redis`) re-run 5×; `test_rate_limiter.py`, `test_deletion_engine_enqueue_resilience.py`, `test_scheduled_briefs_enqueue_resilience.py` re-run | PASS |
| S11A-P2-014 | Restoring Redis allows pending work to drain, no duplicate operation | 5 | Existing: same journey/tests, Redis restarted mid-run, backlog drain confirmed by row-count comparison | PASS |
| S11A-P2-015 | Redis inspected after recovery for raw email/user id/provider object id/OAuth data/proposal payload/private content | 5 | New: `redis-cli --scan`/`GET` inspection pass added to the Redis-recovery rehearsal this phase (see `redis-recovery-results.md`) | PASS |

## PostgreSQL outage and recovery

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-016 | Postgres stopped during readiness checking, ordinary requests, ingestion, proposal generation, approval, execution preparation, deletion processing, Audit History pagination: `/ready` fails truthfully, no fabricated success, no external write begins without durable pending state, no Redis-only state becomes authoritative | 5 | Existing: `journey-d-dependency-health.spec.ts` (real `docker compose stop/start db`) re-run 5×; manual rehearsal against each named endpoint category this phase | PASS |
| S11A-P2-017 | API/worker recover cleanly after Postgres returns; migrations intact; no partial transaction; no duplicate operation after reconnect | 5 | Existing: `alembic heads` single-head check re-run after each of the 5 outage cycles; row-count/consistency comparison before/after | PASS |

## Provider timeout before write acceptance

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-018 | Fake-Google timeout where the provider never accepts/creates the object (write never attempted or attempted-but-rejected before creation): correct classification, no false success, proven-safe retry, eventual success creates exactly one object, approval binding unchanged, Audit History truthful | 5 per action type (Gmail draft, Calendar event) | New: `test_stage11a_phase2_uncertain_write_repeatability.py`'s companion "timeout-before-acceptance" cases (distinct fixture from the accepted-but-unconfirmed case — no object exists at all, classified `dependency_timeout`/`provider_transient_error`, not `uncertain_external_outcome`) | PASS |

## Accepted-but-unconfirmed write (uncertain)

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-019 | Fake-Google `hang_on_write`: object created, confirmation lost, outcome recorded uncertain, zero auto-retry, no re-offered Execute control, exact payload stays visible, Audit History records uncertainty, API/worker restart never replays, only one object exists | 10 per action type | New: `test_stage11a_phase2_uncertain_write_repeatability.py`; existing `journey-b-uncertain-write.spec.ts` (real fake-Google `hang_on_write`, real API restart) re-run 3× as the process-level complement | PASS |

## Token expiry and refresh

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-020 | Expired access token with valid refresh: bounded refresh, exact account used, token-row lock prevents duplicate concurrent refresh, credentials stored securely, original operation resumes | 3 | Existing: `test_google_token_service.py` (fresh-token/expired-token/refresh-token-preservation cases) re-run | PASS |
| S11A-P2-021 | Concurrent refresh attempts: exactly one refresh wins, no token corruption, no cross-account use | 10 concurrency rounds | New: `test_stage11a_phase2_concurrent_oauth_refresh.py` (extends the existing single-round `test_concurrent_refresh_is_serialised_by_the_row_lock` to 10 rounds × 5 concurrent callers) | PASS |
| S11A-P2-022 | Refresh failure: safe classification, no unbounded repeated refresh, appropriate user guidance, no raw token/provider body exposed | 3 | Existing: `test_google_token_service.py::test_missing_refresh_token_requires_reauthorisation` and related, re-run | PASS |

## Revoked consent

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-023 | Revoked Google consent: classified non-retryable (`authorisation_revoked`), reconnection guidance shown (not temporary-outage guidance), ingestion stops safely, no write attempted, existing imported data not silently deleted, disconnect/deletion remain distinct, no automatic reconnection | 3 | Existing: `test_google_token_service.py::test_invalid_grant_marks_account_revoked_and_raises`, `test_execution_invalid_grant_marks_revoked_not_context_changed`, `test_google_oauth.py::test_revoked_grant_is_a_distinct_metric_outcome_not_unknown_error` re-run 3× | PASS |

## Rate-limiter dependency failure

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-024 | Redis failure before/during atomic rate-limit script execution, and recovery; trusted-proxy/spoofed-header handling during degradation; fail-open scoped to rate limiting only; no raw IP/account id exposed; one user's failure never contaminates another's subject | 5 | Existing: `test_rate_limiter.py`, `rate_limit_ip.py` trusted-proxy tests, re-run; new 2-user isolation angle added under S11A-P2-028 | PASS |

## Storage pressure

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-025 | Storage exhaustion on the app's one durable-storage boundary (PostgreSQL — see scoping note): explicit failure, no partial/corrupted state treated as authoritative, safe classification, no private content dumped to a fallback location | 3 | New: `test_stage11a_phase2_storage_pressure.py` (constructs a real `sqlalchemy.exc.OperationalError` shaped like Postgres's `53100 disk full` condition and confirms `classify_exception` → `database_unavailable`, retryable, no raw message leaked) — see scoping note in `defect-register.md`'s non-defects section | PASS |

**Scoping note:** LifeFlow itself writes no local application-managed files (no report/screenshot/cache directory in its own runtime code — those are Playwright test-harness artefacts, never committed, never part of the running app). Its only durable-storage boundary is PostgreSQL; Redis is non-durable by design (ADR 0004 D48). A host-disk-full simulation via a bounded Docker tmpfs was considered and rejected as testing a code path that does not exist in this product — see `defect-register.md` for the full reasoning, consistent with this contract's instruction not to fabricate a contrived test.

## Backup and restore

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-026 | Local backup of synthetic data (user, source items, brief, proposal, approval, execution, audit history, deletion-operation state) into an isolated throwaway database; integrity checked; restore verified by row-count/approval-binding/audit-readability comparison; no secret exported; restored app starts; cleanup removes the environment | 3 complete cycles | New: `scripts/phase2-backup-restore-rehearsal.sh` | PASS |

## Rollback rehearsal

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-027 | Local packaging rehearsal: current good state deployed, a deliberately failing configuration is applied, health/readiness fails, rollback to the last known-good git ref + Alembic state, post-rollback smoke test, no false success at any step | 3 complete cycles | New: `scripts/phase2-rollback-rehearsal.sh` | PASS |

## Cross-user isolation during failure

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-028 | Rate-limiter Redis fail-open for user A never affects user B's rate-limit state or subject hash | 3 | New: `test_stage11a_phase2_cross_user_isolation.py` | PASS |
| S11A-P2-029 | An uncertain execution for user A's proposal never appears in, or affects, user B's proposal/audit list | 3 | New: `test_stage11a_phase2_cross_user_isolation.py` | PASS |
| S11A-P2-030 | User A's OAuth refresh/token row lock never blocks or leaks into user B's refresh | 3 | New: `test_stage11a_phase2_cross_user_isolation.py` | PASS |
| S11A-P2-031 | User A's deletion-recovery sweep never touches user B's rows; recovery sweeps remain owner-scoped | 3 | New: `test_stage11a_phase2_cross_user_isolation.py`; existing `test_ownership.py` re-run | PASS |

## Observability

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-032 | Every failure scenario above logs a closed `FailureCode`, never a raw exception/token/email body/provider payload; metric labels stay within the closed, bounded vocabulary; no account/proposal/execution/provider-object/correlation id or exception text becomes a metric label; readiness/health match reality; worker startup configures structured logging | N/A (evidence table, not repeated) | Existing: `test_metrics.py` (bounded-cardinality label checks) re-run; `observability-results.md` compiles a bounded evidence table across every scenario family above | PASS |

## Recovery timing

| ID | Scenario | Repetitions | Evidence | Result |
|---|---|---|---|---|
| S11A-P2-033 | Descriptive local recovery-time measurement for API/web/worker/scheduler restart, Redis/Postgres recovery, backlog drainage, stale-execution recovery, backup restore, rollback | Per-scenario repetition counts above | New: `recovery-timing-summary.md` — median, slowest observed, repetition count, environment, explicit non-SLA limitation, for each | PASS |

## Manual owner walkthrough

| ID | Scenario | Evidence | Result |
|---|---|---|---|
| S11A-P2-034 | Owner-operated walkthrough of: temporary outage, reconnection-required, uncertain Gmail draft, uncertain Calendar event, Redis-degraded readiness, PostgreSQL-unavailable state, worker-delayed operation, deletion recovery, restored normal operation | New: `apps/web/e2e-owner-validation/phase2-failure-walkthrough.spec.ts` + `manual-walkthrough.md`, every subjective entry labelled `OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE` | PASS |

All rows PASS. No row blocked. Full narrative detail in the companion evidence documents and the final report delivered to the user.
