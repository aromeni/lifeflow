# Stage 9 Delivery Phase 5 — Outage Resilience Manual Checklist

Executed live (2026-07-28/29) against a dedicated local stack: Docker Compose
PostgreSQL and Redis, a separate API instance on port 8011
(`LIFEFLOW_E2E_FAKE_GOOGLE=1`, `E2E_TEST_CONTROLS_ENABLED=true`,
`GOOGLE_API_ORIGIN_OVERRIDE=http://127.0.0.1:8098`), the test-only fake
Google server on port 8098, and a real ARQ worker. No real Google or
Anthropic credentials were used; the fake token/synthetic account seeded via
`apps/api/scripts/e2e_google_support.py` never touches a real provider. All
values below are redacted (UUIDs and the fake token string omitted) — this
file records outcomes, not raw evidence.

## Baseline

1. `GET /health` → `{"status":"ok"}`. ✅
2. `GET /ready` → `{"status":"ok","degraded_dependencies":[]}`. ✅
3. `GET /metrics` baseline snapshot captured (32 lines, all zero/empty counters). ✅

## Dependency outages

4. Redis stopped (`docker compose stop redis`): `GET /ready` → `200`,
   `degraded_dependencies:["redis"]`; `GET /health` unaffected. ✅
5. Redis restarted: `GET /ready` recovers to `degraded_dependencies:[]`. ✅
6. PostgreSQL stopped: `GET /ready` → `503`; `GET /health` unaffected. ✅
7. PostgreSQL restarted: `GET /ready` recovers to `200`. ✅

## Provider fault injection (fake Google server, closed scenario vocabulary)

8. Dev-login and a synthetic Google account seeded via the E2E support script.
9. **Provider-read retry and recovery.** `transient_then_recover`
   (`fail_count=2`) set on `gmail_list_messages`. Sync succeeded; fake-server
   call count confirmed exactly 3 attempts (2 failures + 1 success, inside
   the 3-attempt retry budget); both synthetic messages imported. ✅
10. **Provider permanent failure.** Fresh account, `permanent_failure` set on
    `gmail_list_messages`. Sync returned `502
    {"code":"google_sync_failed","message":"Google rejected the request.",
    "retryable":false,"dependency":"google"}` — no raw provider status or
    exception text in the response. ✅
11. **Provider authentication expiry.** Same account, `auth_expired` set.
    Sync returned `502 {"message":"Your Google connection needs to be
    refreshed.","retryable":true,"dependency":"google"}`. ✅
12. **Uncertain provider write.** A `create_gmail_draft` proposal approved and
    executed with `hang_on_write` set on `gmail_create_draft`. Execution
    outcome reported as `uncertain`; fake-server draft-object count = 1. ✅
13. **No automatic retry of the uncertain write.** A replay call against the
    same proposal returned the identical execution id; fake-server draft
    count remained 1 (no second draft created). ✅

## Worker correlation propagation

14. A real deletion confirmation was processed through a Redis
    outage-then-recovery window with the ARQ worker running. Worker log
    output inspected: genuine structured JSON lines, each carrying a real,
    non-`"-"` correlation id distinct per job — confirming the
    `configure_logging` fix (this item is what surfaced the gap; the worker
    previously emitted plain-text logs with no correlation id rendered at
    all). ✅

## Post-activity and cleanup

15. `GET /metrics` snapshot after the above shows correctly labelled non-zero
    counters for every outcome exercised: `success`, `transient_error`,
    `client_error`, `auth_error`, `timeout`. ✅
16. Every captured response body and log line grepped for the fake token
    literal and any synthetic account identifier: no leak found. ✅
17. Clean shutdown: `pgrep` for the fake-server, dedicated-API, and worker
    processes returned nothing after teardown — no orphan process left
    running. ✅

## Note

Step 14's worker was deliberately hard-killed (`kill -9`) once during this
pass to observe recovery; this left a stale `arq:in-progress:cron:*` Redis
lock that delayed (not permanently blocked) that cron job's next run in a
later, unrelated `./scripts/e2e.sh` invocation on the shared dev stack.
Resolved with `redis-cli flushall` (dev/test Redis only) and documented in
`docs/delivery/runbooks/worker-recovery.md` — a real, bounded, self-healing
operational behaviour worth knowing about, not a defect in this phase's code.
