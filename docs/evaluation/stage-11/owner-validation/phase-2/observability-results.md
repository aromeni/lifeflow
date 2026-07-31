# Stage 11A Phase 2 — Observability Validation

**Status:** Complete · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) (S11A-P2-032) · [failure-scenario-inventory.md](failure-scenario-inventory.md)

Bounded evidence table across every scenario family this phase exercised. "Bounded" means: every log/metric field is drawn from a closed, finite vocabulary (`FailureCode`, `Severity`, a fixed provider/operation label set) — never a raw exception message, stack trace, token, email body, or free-form identifier.

| Scenario family | Failure category logged | Metric label(s) | Private content check |
|---|---|---|---|
| API/worker restart | N/A (process-level, not a classified failure) | N/A | No token/payload in restart logs (`/tmp/phase2-rollback-*.log` inspected manually) |
| Redis outage | `redis_unavailable` / rate-limit `degraded=True` | `lifeflow_rate_limit_fail_open_total{policy_code=...}` (closed policy-code vocabulary) | Confirmed clean — see redis-recovery-results.md |
| PostgreSQL outage | `database_unavailable` | N/A (no DB-specific counter; readiness state is the signal) | `/ready` response contains only `{"status": "unavailable"}`, no driver detail |
| Provider timeout before acceptance | `unknown_error`→refused via `FinalExecutionError` (a closed error-code string, e.g. `approval_context_changed`) | N/A | `execution.result_json` contains only the fixed disclosure message, never the raw exception |
| Uncertain write | `uncertain_external_outcome` | N/A | `execution.result_json` contains only a fixed safe message per executor (e.g. "Gmail did not confirm draft creation before the call ended.") |
| Token refresh / revoked consent | `authentication_expired` / `authorisation_revoked` | N/A | No raw token, refresh token, or provider response body in any audit event (`test_action_proposals.py::test_audit_metadata_never_contains_payload_content` re-run) |
| Storage pressure | `database_unavailable` | N/A | `classify_exception()`'s safe message never includes the raw driver text (this phase's own `test_stage11a_phase2_storage_pressure.py` asserts this directly) |
| Backup/restore, rollback | N/A (new local tooling, not part of the app's runtime observability surface) | N/A | Dump table-of-contents scanned for secret-shaped strings — clean |

## Closed-vocabulary confirmation

Re-ran `test_metrics.py::test_metric_label_registries_are_closed_and_bounded` and `::test_every_observe_provider_call_site_uses_a_literal_closed_provider_and_operation` — both pass, confirming no metric call site in the codebase (including anything touched by this phase) introduces an unbounded label (an account id, proposal id, execution id, provider-object id, correlation id, or raw exception text as a label value).

## Readiness/health truthfulness

Reconfirmed throughout: `/health` never varies with dependency state; `/ready` accurately reflects PostgreSQL (blocking) and Redis (non-blocking, `degraded_dependencies`) at every point during this phase's Redis/Postgres outage cycles — see redis-recovery-results.md and postgres-recovery-results.md.

## Worker startup logging

`worker_app.py`'s `on_startup` hook calls `configure_logging` before any job processing begins — unchanged by this phase, re-confirmed by `test_worker_app.py`'s re-run.

## Alert-worthy vs ordinary transient distinction

The existing `Severity` enum (`info`/`warning`/`error`) already distinguishes these: transient, retryable conditions (`provider_transient_error`, `redis_unavailable`, `dependency_timeout`) are `warning`; non-retryable and data-integrity-relevant conditions (`provider_permanent_error`, `database_unavailable`) are `error`. No new severity level was needed for anything this phase exercised.
