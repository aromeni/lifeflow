# Stage 9 Delivery Phase 5 Completion Report — Outage Resilience and Privacy-Safe Telemetry

**Branch:** `stage-9-resilience-telemetry` (base: the Phase 4 tip `481a67beb4df27ffa33b6e0ae7fc349b36b433c4`, remotely finalised at `origin/stage-9-rate-limiting`).
**Date:** 2026-07-28 (convergence pass completed and committed 2026-07-29).
**Status:** implemented, closed, verified, and **committed locally as eight commits** on `stage-9-resilience-telemetry` from the approved parent `481a67b`. Not pushed, not tagged, not merged — Phase 5 awaits remote finalisation. Stage 9 is not complete.

## Executive verdict

**APPROVE DELIVERY PHASE 5 FOR COMMIT**

Every mandatory acceptance row is closed with live evidence, not deferred: all four outage-simulation Playwright journeys are built and pass twice consecutively against a real stack (real PostgreSQL, Redis, API, ARQ worker, web app); provider-metrics coverage spans the full Gmail/Calendar ingestion read path plus OAuth refresh, with a dedicated, documented-double-count timeout counter; all 17 manual smoke-test items were executed live, including every item previously covered only by automated tests; a full exact-boundary security proof passed (one real gitleaks finding fixed via a precisely-scoped, negative-control-verified allowlist entry); and one genuine pre-existing gap was found and fixed along the way (the worker process never installed structured logging, so the correlation id this phase threads through every job had nothing to render it).

## Baseline repair

`test_approval_inbox_route_returns_the_new_proposal` (Stage 8-era) seeded a proposal from the file's frozen `REFERENCE` constant while `GET /action-proposals` expires proposals against the real wall clock — a latent bug that would eventually make the test fail as real time advanced past the seeded expiry. Fixed by seeding from a live reference, per the repository's own documented clock-control convention (`tests/helpers.py`); proved stable under a temporary +400-day clock shift (removed before finalising); a permanent regression test (`test_approval_inbox_route_expires_a_proposal_seeded_from_a_stale_reference`) locks in both directions (a stale-referenced proposal correctly expires; a freshly-seeded one stays `proposed`). No production expiry logic was touched.

## Dependency and failure-mode inventory, failure taxonomy, timeout policy, retry policy, circuit-breaker decision

A dependency-and-failure-mode inventory across Google, Redis, PostgreSQL, and ARQ preceded design (ADR 0005 D82–D91). `failure_taxonomy.py` introduces a closed, typed `FailureCode` enum shared by the Google connectors and scheduled briefs, replacing several independently-invented string literals. `timeouts.py` centralises every network timeout — connect/read/write budgets for Google, a database statement timeout, and the worker health-check ping timeout — all validated, positive-only configuration; writes get a longer budget than reads so a local timeout on a write is never mistaken for "Google didn't receive the request." `retry.py::retry_read` provides bounded, jittered retry for reads only; it is structurally never applied to `create_draft`/`insert_event`, and two dedicated tests count actual transport calls to prove a write is attempted exactly once regardless of failure classification. Retry exhaustion always re-raises the original exception type. A circuit breaker was evaluated and deliberately omitted (D85): existing per-account status, timeouts, retries, and the durable uncertain-outcome model already provide its benefits at pilot scale, and a breaker is itself a common source of new privacy/availability risk (shared state that could leak across users, or fail closed for everyone on one user's account-specific problem).

## Durable execution recovery, worker resilience

`recover_stale_pending_executions` proactively sweeps every user's stale `pending` `ActionExecution` rows once a minute via a new cron job (`recover_stale_action_executions`), closing the one asymmetry between the durable-execution model and the deletion/scheduled-brief subsystems (which already had this pattern). Three Redis-enqueue paths that previously let an uncaught Redis error abort an entire cron tick and roll back every row processed earlier in the same loop — scheduled-brief dispatch, scheduled-brief stale-run recovery, and durable deletion operations — now fail open, leaving the row unenqueued for the next tick's pending-drain pass. ARQ payloads carry only internal identifiers; duplicate job delivery cannot duplicate durable work (proven by concurrent-worker Playwright Journey C).

## Health and readiness, structured logging, correlation propagation

`GET /ready` now reports Redis as a non-blocking degraded dependency (`degraded_dependencies: ["redis"]`, still `200`) while PostgreSQL unavailability correctly returns `503` — proven both live (Redis/Postgres stopped and restarted against the real Docker Compose stack) and by `test_ready.py`. `GET /health` remains independent of every dependency, including Google. `with_worker_correlation` binds a fresh correlation id for the duration of each ARQ job/cron invocation, mirroring `CorrelationIdMiddleware`'s HTTP-request scoping. Live verification during the manual smoke test surfaced a genuine gap: `worker_app.py::on_startup` never called `configure_logging`, so the worker process used Python's default plain-text logging and the correlation id had nothing to render it. Fixed with one line matching `main.py::create_app`'s identical call, and covered by a new regression test (`test_on_startup_configures_structured_logging`).

## Provider metrics coverage, timeout metrics, metrics cardinality

`metrics.py` (Prometheus text exposition via `GET /metrics`) extends `observe_provider_call` across the full Gmail/Calendar ingestion read path (`list_messages`, `get_message`, `list_history`, `get_current_history_id`, `list_events`) and OAuth token refresh — previously only `create_draft`/`get_draft`/`insert_event`/`get_event` were instrumented. The outcome vocabulary grew from five to eight closed values, adding `history_expired`, `sync_token_expired`, and `grant_invalid` as distinct, well-understood conditions rather than falling into `unknown_error`. `lifeflow_provider_timeouts_total` is populated whenever a `GoogleTransientError`'s `__cause__` is an `httpx.TimeoutException` — a documented deliberate double count alongside (not instead of) `provider_requests_total{outcome="timeout"}`, distinguishing a true socket timeout from an ordinary HTTP-level transient error (429/5xx). Every label set is fixed at definition time (provider name, operation name, failure code, rate-limit policy code, worker job name) — never a user/account/proposal/provider-object id, an IP address, or an exception message. `test_metrics.py` includes a static AST scan proving every `observe_provider_call` call site uses a literal from the closed vocabulary, plus tests asserting per-call-path emission, timeout-vs-response-error separation, and that arbitrary operation names are rejected.

## API error contract, frontend degraded behaviour

The existing safe error envelope (`ErrorBody`) gains two additive, optional fields — `retryable: bool | None` and `dependency: str | None` — populated at the Google sync route via the closed failure taxonomy, never a raw provider status code or exception message. The frontend (`apps/web/src/lib/api.ts`, `apps/web/src/app/connections/page.tsx`) now distinguishes a "temporarily unavailable, safe to retry shortly" notice (`role="status"`, amber) from a "will not succeed by retrying, reconnect Google" notice (`role="alert"`, red) instead of one undifferentiated red error. An uncertain execution still offers no retry regardless of these fields; rate-limit `429` handling is unchanged.

## Provider-fake safety boundary

`lifeflow_api/testing/fake_google_server.py` is a standalone ASGI app, never imported by `main.py`, that raises `SystemExit` at import time unless `LIFEFLOW_E2E_FAKE_GOOGLE=1` is set. The real API is redirected to it only via `google_api_origin_override`, itself inert unless `e2e_test_controls_enabled=true`; `create_app` refuses to start (`RuntimeError`) if that flag is ever `true` with `environment=production`, proven by `test_e2e_test_controls_enabled_refuses_to_start_in_production`, and separately proven that the flag alone (no override) and the override alone (no flag) each leave real Google endpoints untouched. The fake server never accepts or validates a real bearer token and never calls a real Google host; its closed `Scenario` enum (`healthy`, `transient_then_recover`, `permanent_failure`, `auth_expired`, `hang_on_write`) and operation vocabulary are validated on every control call (422 on anything else), and its `/__control__/state` endpoint exposes only synthetic counts, never content. `GmailDraftClient`/`CalendarEventClient` gained an optional `base_url` constructor parameter defaulting to the real host — configurability, not a weakened abstraction.

## Playwright journeys (built against `apps/web/e2e-resilience/`, a dedicated stack via `scripts/e2e-resilience.sh`)

- **Journey A (transient provider-read outage):** injects `transient_then_recover` (fail twice, inside the 3-attempt retry budget) on `gmail_list_messages`; proves bounded retry recovers with exactly 3 calls, sync succeeds with both messages imported, no error is shown, and a second healthy sync does not duplicate the imported `SourceItem`s.
- **Journey B (uncertain external write):** approves and executes a `create_gmail_draft` proposal with `hang_on_write` triggered on the fake server; proves the write is recorded (exactly one draft object exists server-side) while the API reports the execution as `uncertain`; a real OS-level API restart (kill + respawn, not a simulated restart) does not trigger a retry, because the uncertain state is durably committed to PostgreSQL, not held in memory; a direct replay is answered idempotently with the same execution record.
- **Journey C (worker outage and recovery):** confirms an imported-data deletion through the UI with no ARQ worker running at all — the UI shows "Queued" (not failure, not completion) and stays that way; starting two worker processes simultaneously (a duplicate-consumer scenario) proves the operation completes exactly once via the atomic per-operation claim.
- **Journey D (dependency health):** against the real Docker Compose stack, proves `/health`/`/ready`/`/metrics` behave correctly through Redis stop/restart (degraded, non-blocking) and PostgreSQL stop/restart (`503`, blocking); a simulated Google permanent failure leaves both `/health` and `/ready` unaffected; no response body ever contains a connection string, credential, or traceback.

Both the resilience suite (4 journeys) and the original suite (10 journeys) were run twice consecutively on the fully-converged code, each run starting a fresh stack and leaving no orphan process (`lsof -ti tcp:PORT -sTCP:LISTEN` confirmed empty after each run — not a plain `lsof -ti:PORT`, which matches sockets by port on either end of a connection and would incorrectly report the test runner's own outbound connections as occupying the port).

## Complete manual smoke test

All 17 required items were executed live against the real local stack (Docker Compose PostgreSQL/Redis, a dedicated API on port 8011, the fake Google server on port 8098, a real ARQ worker), using synthetic fixtures and a fake token only — no real email/calendar content, OAuth credentials, provider response bodies, or private user identifiers. This includes every item previously covered only by automated tests: provider-read retry and recovery, provider permanent failure, provider authentication expiry, an uncertain provider write, confirmation that the uncertain write is never automatically retried, and worker correlation propagation (which is what surfaced the structured-logging gap above). Every manually-started process was confirmed terminated with no orphan afterward. See `docs/delivery/stage-09-phase-5-manual-checklist.md` for the redacted, item-by-item record.

## Safety and privacy invariants

Gmail drafts-only/never-send and Calendar insert-only/never-modify are unchanged; exact payload/version/account-context approval binding is unchanged; durable pending-before-provider-call commit is unchanged; uncertain writes are never auto-retried (now proven live via Journey B, not only unit-tested); reads are retried only when idempotent; PostgreSQL remains sole source of truth; Redis remains ephemeral and privacy-safe; owner scoping is untouched; no raw content appears in any log line, metric label, or error field (see threat model T31).

## Tests added

New: `test_failure_taxonomy.py`, `test_timeouts.py`, `test_retry.py`, `test_execution_recovery_sweep.py`, `test_scheduled_briefs_enqueue_resilience.py`, `test_deletion_engine_enqueue_resilience.py`, `test_metrics.py`, `test_correlation.py` (extended), `test_e2e_test_controls.py`, and the four `apps/web/e2e-resilience/` Playwright specs. Extended: `test_google_gmail_client.py`, `test_google_calendar_client.py`, `test_google_oauth.py`, `test_google_executors.py`, `test_google_route_integration.py`, `test_ready.py`, `test_rate_limiting_api.py`, `test_worker_app.py`, `apps/web/src/app/connections/page.test.tsx`, `apps/web/src/lib/api.test.ts`.

## Negative controls

`test_origin_override_is_ignored_unless_test_controls_are_enabled` / `test_test_controls_enabled_without_an_origin_override_keeps_real_google` prove both halves of the test-only redirect must be set together. A deliberately different high-entropy string, staged and scanned with `gitleaks protect --staged`, was still caught after adding the fake-token allowlist entry, proving the allowlist is exact-literal-scoped rather than overly broad. `test_a_response_level_transient_error_does_not_touch_the_timeout_counter` proves an ordinary 5xx doesn't get miscounted as a timeout. Journey B's replay step proves idempotent re-entry rather than re-execution; its API-restart step proves durability rather than in-memory state.

## Exact-boundary security proof

`git add -A` staged the complete intended boundary; `git diff --cached --check` was clean. `pre-commit run --all-files` against that exact staged boundary found two real issues — a test fixture needing `# pragma: allowlist secret`, and two new Uvicorn launch sites needing classification in `scripts/check_uvicorn_launch_safety.py` — both fixed, then re-run clean. `gitleaks protect --staged` found one real finding (the fixed synthetic `TOKEN_KEY` value, base64 of a readable phrase that still reads as high-entropy to a generic-secret rule), resolved with a narrowly-scoped, exact-literal `.gitleaks.toml` allowlist entry and verified via the negative control above. `gitleaks git --no-banner --redact` (full history) found no leaks. `.secrets.baseline` diffs at each commit reflect only genuine line-number shifts from real content changes plus a `generated_at` timestamp — never a spurious or path-based suppression.

## Files changed

77 total paths (51 modified, 26 new), assembled as eight commits — see "Commit split" below.

## Migration decision

No migration was needed or created. Every Phase 5 mechanism lives in application code, Redis, or in-process state; the Alembic head remains `0011`.

## Known limitations

1. A stale ARQ `arq:in-progress:cron:*` lock left by a hard-killed worker during the manual smoke test silently delayed (never permanently blocked) that cron job's next run until the lock's own TTL expired — a real, bounded, self-healing operational behaviour, documented in `docs/delivery/runbooks/worker-recovery.md`.
2. `docs/delivery/metrics.md`'s "E2E journeys (Playwright)" figure is a combined count of `apps/web/e2e` and `apps/web/e2e-resilience`; the two suites require separate invocations and must never run concurrently, since Journey D stops the shared Postgres/Redis containers.

## Explicit exclusions

No circuit breaker (D85); no new `AuditEvent` type; no database migration; no change to rate-limiting, deletion, or audit-history behaviour; no later-stage feature introduced.

## Commit split

Assembled as eight commits on top of the approved parent `481a67b`:

1. `fix(tests): repair date-sensitive proposal dedup test` — baseline repair, isolated.
2. `feat(stage-9): add failure taxonomy, timeouts and bounded read retries` — `failure_taxonomy.py`, `timeouts.py`, `retry.py`, Google client timeout wiring, database statement timeout, read-retry integration, OAuth refresh retry, scheduled-brief failure-code consolidation.
3. `feat(stage-9): harden execution recovery and worker enqueueing` — `recover_stale_pending_executions`, its cron job, and the three Redis-enqueue fail-open fixes.
4. `feat(stage-9): add readiness, correlation and privacy-safe metrics` — `metrics.py`, the full provider-metrics extension, `GET /ready`'s Redis degraded reporting, worker correlation propagation, the worker structured-logging fix.
5. `feat(stage-9): add safe dependency errors and degraded sync UX` — the additive error-envelope fields and the Connections page's distinct degraded states.
6. `test(stage-9): verify outage resilience with a fake provider` — the fake Google server, the test-only origin-override boundary, and the four resilience Playwright journeys.
7. `chore(contracts): regenerate Phase 5 API contracts`.
8. `docs(stage-9): document resilience, telemetry and recovery` — ADR, decision log, threat model, stage plan, runbooks, this report, and the regenerated metrics dashboard.

Phase 5 awaits remote finalisation. Do not tag, merge, or begin Stage 9 final closure without explicit further authorisation.
