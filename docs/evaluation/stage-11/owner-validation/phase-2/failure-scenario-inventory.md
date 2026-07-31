# Stage 11A Phase 2 — Failure Scenario Inventory

**Status:** Complete · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) · [../../../../delivery/stage-11a-phase-2-plan.md](../../../../delivery/stage-11a-phase-2-plan.md)

This inventory confirms the failure taxonomy required by the governing task instruction (§3) is fully covered by the pre-existing, closed `FailureCode` enum (`apps/api/src/lifeflow_api/failure_taxonomy.py`) — reconfirmed, not redefined, by this phase.

| Required distinction | `FailureCode` | Retryable | Where classified |
|---|---|---|---|
| Transient provider read failure | `provider_transient_error` | Yes | `classify_exception()` on `GoogleTransientError` |
| Non-retryable provider authentication failure | `provider_permanent_error` | No | `classify_exception()` on `GoogleClientError` |
| Timeout before provider write acceptance | `dependency_timeout` / `provider_transient_error` | Yes | Write never durably created at the provider; classified before any `ActionExecution` row exists |
| Timeout after provider write acceptance | `uncertain_external_outcome` | No — never auto-retried | `action_proposal_service.py::execute()`'s pending→uncertain path |
| Dependency (queue) unavailable | `redis_unavailable` | Yes | `classify_exception()` on `redis.exceptions.RedisError` |
| Database unavailable | `database_unavailable` | Yes | `classify_exception()` on `sqlalchemy.exc.OperationalError` |
| Queue unavailable | `redis_unavailable` | Yes | Same as dependency-unavailable — LifeFlow's queue is Redis |
| Worker unavailable | `worker_unavailable` | Yes | Deletion/scheduled-brief dispatcher classification |
| Scheduler unavailable | Same worker process — arq's own in-progress-key TTL self-heal (see acceptance-matrix.md S11A-P2-012's method note) | Yes | `worker-recovery.md` runbook, re-verified against `arq==0.28.0` source |
| Application process unavailable | Surfaces as `dependency_timeout`/connection-refused to the caller; recovery proven via restart scenarios S11A-P2-001 to -004 | Yes | Client-side timeout/connection handling |
| Invalid or revoked authorisation | `authentication_expired` (expired, retryable) / `authorisation_revoked` (revoked, non-retryable) | Mixed | `GoogleTokenService`, `InvalidGrantError` handling |
| Resource exhaustion | `database_unavailable` (PostgreSQL is the app's only durable-storage boundary — see acceptance-matrix.md's storage-pressure scoping note) | Yes | `classify_exception()` |
| Internal validation failure | `unknown_error` (closed fallback) | No | `classify_exception()`'s final branch |
| Uncertain external outcome | `uncertain_external_outcome` | No — never auto-retried | `action_proposal_service.py::execute()` |

No raw infrastructure or provider exception is ever exposed to a user — every call site funnels through `classify_exception()` or an equivalent narrow, already-tested classifier. No new, unbounded, or user-controlled failure label was introduced by this phase; every code path above existed before Phase 2 and was reconfirmed, not authored, by it.

## Scenario families and stable IDs

See [acceptance-matrix.md](acceptance-matrix.md) for the full per-scenario detail (failure introduced, timing, expected states, recovery mechanism, prohibited behaviour, repetitions, evidence, result). Families, in ID order:

- `S11A-P2-001`–`004` — API restart (idle, during read, before write, uncertain write)
- `S11A-P2-005` — Web-process restart
- `S11A-P2-006`–`011` — Worker crash (claim timing, competing workers, uncertain write, deletion batching, scheduled briefs, backlog drainage)
- `S11A-P2-012` — Scheduler interruption
- `S11A-P2-013`–`015` — Redis outage and recovery
- `S11A-P2-016`–`017` — PostgreSQL outage and recovery
- `S11A-P2-018` — Provider timeout before write acceptance
- `S11A-P2-019` — Accepted-but-unconfirmed write (uncertain)
- `S11A-P2-020`–`022` — Token expiry and refresh
- `S11A-P2-023` — Revoked consent
- `S11A-P2-024` — Rate-limiter dependency failure
- `S11A-P2-025` — Storage pressure
- `S11A-P2-026` — Backup and restore
- `S11A-P2-027` — Rollback rehearsal
- `S11A-P2-028`–`031` — Cross-user isolation during failure
- `S11A-P2-032` — Observability
- `S11A-P2-033` — Recovery timing
- `S11A-P2-034` — Manual owner walkthrough
