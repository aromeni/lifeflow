# Stage 11A Phase 2 — Controlled Failure and Recovery Validation Plan

**Status:** Execution in progress · **Date:** 2026-07-31

Companion: [stage-11a-phase-1-plan.md](stage-11a-phase-1-plan.md) · [stage-11a-owner-validation-plan.md](stage-11a-owner-validation-plan.md) §D · [docs/evaluation/stage-11/owner-validation/phase-2/](../evaluation/stage-11/owner-validation/phase-2/)

## Objective

Prove that LifeFlow remains safe, truthful, recoverable, and free from duplicate external effects when its application processes, dependencies, provider connections, and infrastructure fail at controlled points — extending Stage 11A Phase 1's synthetic-acceptance proof (the happy path is safe) to the failure/recovery path (the unhappy path is also safe).

## Scope

Owner-only, no participant involved. Uses only: local Docker Postgres/Redis, deterministic synthetic data, the existing fake-Google test server (`apps/api/src/lifeflow_api/testing/fake_google_server.py`), isolated Docker containers/volumes, synthetic credentials, owner-operated validation, and automated failure-injection tests (unit/integration pytest plus the existing Playwright resilience suite).

## Exclusions

Does not: connect a real Gmail/Calendar account, create or connect a Google test account, use any personal inbox/Calendar data, start the 14–30 day soak period, recruit or contact any participant, provision paid infrastructure, begin Stage 12, or create a Stage 11 completion tag.

## Method note: reuse before rebuild

A thorough codebase audit (recorded in the acceptance matrix's "evidence" column) found that most of the failure/recovery machinery this phase must verify **already exists and is already tested**, built across Stages 7–9:

- **Fake Google server** (`testing/fake_google_server.py`) — closed `Scenario` enum (`healthy`, `transient_then_recover`, `permanent_failure`, `auth_expired`, `hang_on_write`) plus a control API, purpose-built for exactly this phase's provider-failure scenarios.
- **Four existing resilience E2E journeys** (`apps/web/e2e-resilience/`) already exercise, at the real-process level: transient provider read outage recovering within the retry budget (Journey A), an uncertain Gmail draft write surviving a real API-process restart with zero duplicate dispatch (Journey B), a durable deletion operation surviving a worker outage and two competing workers never double-completing it (Journey C), and truthful `/health`/`/ready` degradation across a real Redis and a real PostgreSQL container stop/start (Journey D).
- **Worker/scheduler durability**: atomic row-claim (`deletion.py::claim_operation`), stale-execution recovery cron sweeps, a DB unique constraint plus a deterministic arq job id preventing duplicate scheduled briefs (ADR 0004 D48/D49), and arq's own documented in-progress-key TTL self-heal (`docs/delivery/runbooks/worker-recovery.md`; independently re-verified against the installed `arq==0.28.0` source in this session, `worker.py:450-465,690-698`).
- **Rate limiter fail-open** (`rate_limiter.py::RateLimiter.check`) — any Redis failure returns `degraded=True, allowed=True` by design (ADR 0005 D64), already tested.
- **OAuth refresh locking and revocation classification** (`accounts.py::GoogleTokenService`) — row-locked concurrent refresh, `InvalidGrantError` → `AccountStatus.revoked`, already tested.
- **Deletion engine checkpointing** — `resume_cursor_json`/`heartbeat_at`/`attempt_count` on `DataDeletionOperation` make every batch resumable from durable state, already tested.
- **Action-execution uncertainty** (`action_proposal_service.py::execute()`) — commits a `pending` row before any real write, never re-invokes an executor for an existing execution, cron-sweeps stale `pending` rows to `uncertain`, already tested.
- **Closed failure taxonomy** (`failure_taxonomy.py::FailureCode`/`classify_exception`) plus four operator runbooks (`outage-response.md`, `worker-recovery.md`, `health-readiness.md`, `provider-failure.md`) already codify safe, bounded-cardinality classification for every failure family below.

Phase 2's job is therefore **not** to rebuild any of this. It is to: (1) re-run the existing evidence fresh and cite it precisely per scenario, (2) extend automated coverage to the specific gaps a careful audit found — repetition counts this task's contract requires that no existing test meets (10× uncertain-write per action type, 10 concurrency rounds of OAuth refresh), cross-user isolation framed explicitly around failure conditions, and a storage-pressure classification test — and (3) build the two pieces of infrastructure that genuinely do not exist yet and are explicitly called out as unbuilt in `stage-11a-owner-validation-plan.md` §D: a local backup/restore rehearsal and a local rollback rehearsal. Rebuilding already-proven machinery under a new name would not make the product safer; it would only inflate a test count.

## Failure taxonomy (reconfirmed, not redefined)

The existing closed taxonomy (`failure_taxonomy.py::FailureCode`) already distinguishes every category this phase's brief requires:

| Required distinction | `FailureCode` | Retryable |
|---|---|---|
| Transient provider read failure | `provider_transient_error` | Yes |
| Non-retryable provider authentication failure | `provider_permanent_error` | No |
| Authorisation revoked (distinct from expired) | `authorisation_revoked` | No |
| Timeout before provider write acceptance | `dependency_timeout` (write never attempted) / `provider_transient_error` (attempted, response lost before acceptance) | Yes |
| Timeout after provider write acceptance | `uncertain_external_outcome` | No — never auto-retried |
| Dependency (queue) unavailable | `redis_unavailable` | Yes |
| Database unavailable | `database_unavailable` | Yes |
| Worker unavailable | `worker_unavailable` | Yes (recoverable) |
| Worker delayed | `worker_delayed` | N/A (informational) |
| Scheduler unavailable | covered by `worker_unavailable` + arq's own in-progress-key TTL self-heal (scheduler = the same worker process's cron loop) | Yes |
| Invalid/revoked authorisation | `authentication_expired` (expired) / `authorisation_revoked` (revoked) | Expired: yes. Revoked: no. |
| Resource exhaustion | `database_unavailable` (the only durable-storage boundary this app owns — see §15 scoping note below) | Yes |
| Internal validation failure | `unknown_error` (closed fallback, never a raw exception) | No |
| Uncertain external outcome | `uncertain_external_outcome` | No — never auto-retried |

No raw infrastructure or provider exception is ever surfaced to a user or a log line — every call site funnels through `classify_exception()` or an equivalent pre-existing narrow classifier (`GoogleTokenService`'s `InvalidGrantError` handling, `action_executors.py`'s uncertain-outcome mapping). No new, unbounded, or user-controlled failure label is introduced by this phase.

## Scenario inventory

See [docs/evaluation/stage-11/owner-validation/phase-2/acceptance-matrix.md](../evaluation/stage-11/owner-validation/phase-2/acceptance-matrix.md) for the full numbered inventory (`S11A-P2-001` onward), each row recording: failure introduced, failure timing, expected user-visible state, expected durable database state, expected Redis state, expected provider-call count, recovery mechanism, prohibited behaviour, repetition count, objective evidence, result, and defect reference.

## Repetition requirements

Per this task's contract, applied exactly:

| Scenario | Required repetitions | How satisfied |
|---|---|---|
| API restart scenarios | 3 each | Existing Journeys A–D re-run 3× each this phase |
| Web restart scenarios | 3 | New manual + automated pass, 3× |
| Worker crash positions | 3 each | Journey C re-run 3×, plus new positional coverage |
| Scheduler interruption scenarios | 3 each | Re-verified via worker-recovery runbook mechanism + 3 re-runs of the dependent cron sweeps |
| Redis outage/recovery | 5 | Journey D re-run 5× |
| PostgreSQL outage/recovery | 5 | Journey D re-run 5× |
| Timeout before write acceptance | 5 per action type | New test, 5× × 2 action types |
| Accepted-but-unconfirmed uncertain write | 10 per action type | New test, 10× × 2 action types (Gmail draft, Calendar event) |
| Concurrent OAuth refresh | 10 concurrency rounds | New test, 10 rounds × 5 concurrent callers |
| Revoked consent | 3 | Existing + re-run 3× |
| Backup and restore | 3 complete cycles | New script, 3 cycles |
| Rollback | 3 complete cycles | New script, 3 cycles |
| Cross-user isolation checks | ≥3 per relevant scenario | New test, ≥3 per scenario across 4 scenario families |

No duplicate provider write is permitted across any repetition. No unexplained durable-state difference is permitted.

## Pass/fail rules

See §26 of the governing task instruction, reproduced in [phase-2-decision.md](../evaluation/stage-11/owner-validation/phase-2/phase-2-decision.md) once recorded. In summary: PASS requires every mandatory scenario verified, zero unresolved P0/P1, zero duplicate external writes, zero automatic replay after uncertainty, successful DB/Redis/worker/scheduler recovery, successful backup/restore and rollback cycles, no cross-user exposure, truthful health/readiness, bounded privacy-safe observability, and a fully green automated suite.

## Recovery-time measurements

Descriptive local measurements only (median, slowest observed, repetition count, environment, explicit limitation) — never a production SLA or availability claim. Recorded in [recovery-timing-summary.md](../evaluation/stage-11/owner-validation/phase-2/recovery-timing-summary.md).

## Durable-state inspection requirements

Every scenario touching PostgreSQL or Redis is inspected post-recovery for: row counts matching expectation, no orphaned `pending`/`running` rows outside documented recovery windows, no duplicate `ActionExecution`/`Brief`/`DataDeletionOperation` rows, and (for Redis) no raw email address, user id, provider object id, OAuth data, proposal payload, or private content — per §8 of the governing instruction.

## Evidence requirements

Every scenario's row in the acceptance matrix cites either a re-run existing automated test/journey (file path + result) or a newly written one. Manual owner observations are separately logged in `manual-walkthrough.md`, each labelled `OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE`.

## Safety invariants

Identical in kind to Phase 1's (`docs/evaluation/stage-11/owner-validation-success-criteria.md`), extended for failure conditions: zero duplicate provider writes under any failure/restart/repetition; zero automatic retry of an uncertain outcome; zero cross-user exposure under any failure condition; truthful `/health`/`/ready` at all times; no raw exception, token, provider payload, or private content ever reaches a log, metric label, or user-facing message; every durable operation is resumable from its own persisted state, never from in-memory or Redis-only state.

## Defect-severity rules

The same closed P0–P3 framework as Phase 1 (`docs/evaluation/stage-11/issue-register-template.md`), with the failure-specific examples listed in the governing task instruction §23: P0 = cross-user exposure, unsafe write replay, secret exposure, corrupted deletion, false successful execution. P1 = unrecoverable core workflow, lost durable operation, restore failure, inability to recover safely. P2 = misleading recovery wording, excessive-but-bounded delay, weak diagnostics. P3 = cosmetic/documentation only. No unresolved P0/P1 is allowed; thresholds are not lowered after observing a failure.

## Exit decision

Recorded in [phase-2-decision.md](../evaluation/stage-11/owner-validation/phase-2/phase-2-decision.md): **PASS — READY FOR PHASE 3**, **CONDITIONAL PASS**, or **FAIL — NOT READY**, per the exact criteria in the governing task instruction §26. Phase 3 (proposed: Security, privacy and residual-data validation) is not authorised by this document and does not itself authorise Google test accounts or the soak period.
