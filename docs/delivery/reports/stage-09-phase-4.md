# Stage 9 Delivery Phase 4 Completion Report — Rate Limiting

**Branch:** `stage-9-rate-limiting` (base: the Phase 3 tip `a50cf063915c4de3e3168c27323e5dc2fba9e773`, remotely finalised at `origin/stage-9-audit-history`).
**Date:** 2026-07-24 (closure addendum appended 2026-07-24 — see bottom of file).
**Status:** implemented, closed, verified, and **committed locally as six commits** on `stage-9-rate-limiting` from the approved parent `a50cf06`. Not pushed, not tagged, not merged — Phase 4 awaits remote finalisation. Stage 9 is not complete. Delivery Phase 5 has not begun.

## Executive verdict

**APPROVE DELIVERY PHASE 4 FOR COMMIT** (superseding the original "FOR REVIEW" verdict below — see the closure addendum)

Every route is classified, the limiter is atomic and privacy-safe, every pre-existing database guard (idempotency, approval binding, deletion plan-fingerprint binding, active-operation uniqueness) is untouched and proven so under simulated Redis failure, and the full existing test suite (backend, frontend, Playwright) is unaffected. One genuine deployment-configuration gap was found during the required manual smoke test — uvicorn's own default silently overrides this app's trusted-proxy boundary — and has been fixed at every documented launch site (see "Manual smoke-test results"), and is now closed with a real-Uvicorn automated regression and a repo-wide launcher-safety validation script (see the closure addendum).

## Verified Git boundary

- Current branch: `stage-9-rate-limiting`, created at `a50cf063915c4de3e3168c27323e5dc2fba9e773` (the final Phase 3 tip, remotely finalised at `origin/stage-9-audit-history`).
- Working tree (original pass): 40 modified files, 10 new files. After the closure addendum below: 42 modified, 13 new — **55 paths total**.
- Those 55 paths are now **committed locally as six commits** on top of `a50cf06` (limiter core → route integration → frontend UX → proxy trust boundary → tests → documentation). The working tree and index are clean afterwards.
- **Not pushed. No tag exists.** No Delivery Phase 5 file exists.

## Route and policy inventory

All 47 HTTP routes across 15 router modules were enumerated directly from source (`main.py`'s `include_router` calls plus every `@router.get/post/put/patch/delete` in each module). Every state-changing route carries exactly one rate-limit policy; every route is either policy-covered or on the closed exemption list below. This is enforced by `apps/api/tests/test_rate_limiting_api.py::test_every_state_changing_route_has_a_policy_or_exemption`, which walks the live `FastAPI` route table and fails if a future route has neither.

**Exemptions (documented, tested):** `GET /health`, `GET /ready`, `GET /config` (infrastructure liveness/readiness and a static unauthenticated capability flag — never throttled); FastAPI's own auto-registered `/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc` (already disabled entirely in production). OPTIONS/HEAD are never charged (handled by CORS/Starlette before reaching any dependency).

**Policy assignments (by router):**

| Router | Route(s) | Policy |
|---|---|---|
| `auth.py` | `POST /auth/dev-login`, `GET /auth/google/login`, `GET /auth/google/callback` | `anonymous_auth` |
| `auth.py` | `POST /auth/logout` | `preference_memory_write` |
| `me.py` | `GET /me` | `authenticated_read` |
| `me.py` | `PATCH /me` | `preference_memory_write` |
| `preferences.py` | `GET /preferences` | `authenticated_read` |
| `preferences.py` | `PUT /preferences/{key}` | `preference_memory_write` |
| `memory.py` | `GET /memories`, `GET /memories/{id}` | `authenticated_read` |
| `memory.py` | `POST .../confirm`, `PUT /memories/{id}`, `POST .../dismiss`, `DELETE /memories/{id}`, `DELETE /memories` | `preference_memory_write` |
| `scheduled_brief_status.py` | `GET /scheduled-briefs/status` | `authenticated_read` |
| `evidence_freshness.py` | `GET /evidence-freshness` | `authenticated_read` |
| `demo_mode.py` | `POST /demo/start` | `demo_start` |
| `source_items.py` | `GET /source-items` | `authenticated_read` |
| `signals.py` | `GET /signals` | `authenticated_read` |
| `signals.py` | `POST /signals/extract` | `signal_extraction` (new, justified: LLM/detector-cost-bearing, same posture as `brief_generate`) |
| `briefs.py` | `GET /briefs/latest`, `GET /briefs`, `GET /briefs/{id}` | `authenticated_read` |
| `briefs.py` | `POST /briefs/generate` | `brief_generate` |
| `action_proposals.py` | `GET` (list, one) | `authenticated_read` |
| `action_proposals.py` | `PATCH /{id}`, `POST /{id}/reject` | `proposal_mutation` |
| `action_proposals.py` | `POST /{id}/approve` | `proposal_approval` |
| `action_proposals.py` | `POST /{id}/execute` | `external_execution` |
| `audit_history.py` | `GET /audit-history` | `privacy_audit_read` |
| `privacy.py` | `GET /privacy/summary` | `privacy_audit_read` |
| `connected_accounts.py` | `GET /connected-accounts` | `authenticated_read` |
| `connected_accounts.py` | `GET .../connect`, `GET .../callback`, `POST .../disconnect` | `oauth_connect_callback` |
| `connected_accounts.py` | `POST .../sync` | `provider_sync` |
| `privacy_deletion.py` | `GET /privacy/deletion-operations`, `GET .../{id}` | `authenticated_read` |
| `privacy_deletion.py` | `POST /privacy/imported-data/{account_id}/preview` | `deletion_preview` |
| `privacy_deletion.py` | `POST /privacy/account-deletion/preview` | `account_deletion_preview` |
| `privacy_deletion.py` | `POST .../{id}/cancel` | `deletion_confirm_cancel` |
| `privacy_deletion.py` | `POST .../{id}/confirm` | **resolved at runtime** — see below |

**The one runtime-resolved route.** `POST /privacy/deletion-operations/{id}/confirm` serves both ordinary (imported-data/retention) and account-deletion confirmations through one shared handler. Its policy cannot be a static `Depends()` declaration, since which policy applies depends on data only knowable after a read. The handler (`privacy_deletion.py::confirm_deletion_operation`) performs one owner-scoped, side-effect-free `DataDeletionOperationRepository.get()` lookup, then calls `enforce_rate_limit(request, "account_deletion_confirm" if operation.operation_type == DeletionOperationType.account_deletion else "deletion_confirm_cancel", subject=str(user.id))` — exactly once, before the existing, unmodified `confirm_operation()` call. `apps/api/tests/test_rate_limiting_api.py::test_deletion_confirm_charges_exactly_one_policy_per_request` proves an imported-data confirm and an account-deletion confirm for the same user draw from independent buckets.

## Policy registry and defaults

Closed registry: `apps/api/src/lifeflow_api/rate_limit_policy.py`, 16 named `RateLimitPolicy` entries, keyed by a stable `code` string (`get_policy` raises `KeyError` for anything unregistered). Each policy is a token bucket: `capacity` (the safe burst allowance and the bucket's initial fill) refills by `refill_amount` every `refill_window_seconds`.

| Policy | Subject | Capacity (burst) | Refill | Category |
|---|---|---|---|---|
| `anonymous_auth` | client IP | 5 | 10 / 5 min | auth |
| `oauth_connect_callback` | user | 5 | 20 / 10 min | connection |
| `demo_start` | user | 2 | 10 / hour | write |
| `authenticated_read` | user | 60 | 300 / min | read |
| `privacy_audit_read` | user | 30 | 120 / min | read |
| `provider_sync` | user | 2 | 6 / 15 min | sync |
| `brief_generate` | user | 3 | 12 / hour | generation |
| `signal_extraction` | user | 3 | 12 / hour | generation |
| `preference_memory_write` | user | 10 | 60 / hour | write |
| `proposal_mutation` | user | 10 | 60 / min | write |
| `proposal_approval` | user | 5 | 30 / 10 min | approval |
| `external_execution` | user | 2 | 10 / 10 min | execution |
| `deletion_preview` | user | 2 | 10 / hour | deletion |
| `deletion_confirm_cancel` | user | 1 | 5 / hour | deletion |
| `account_deletion_preview` | user | 1 | 3 / 24 h | deletion |
| `account_deletion_confirm` | user | 1 | 3 / 24 h | deletion |

These are pilot product defaults (documented as such in the module docstring), not a legal or universal security standard, matching the spec's own framing. All are validated positive integers at construction (`RateLimitPolicy.__post_init__`).

## Configuration

Added to `apps/api/src/lifeflow_api/config.py`: `rate_limiting_enabled` (bool, default `False` — matching every other Stage 8/9 feature flag), `rate_limit_key_secret` (str, default `""`), `rate_limit_redis_prefix` (default `"ratelimit:v1"`), `rate_limit_policy_overrides_json` (default `""`), `rate_limit_max_forwarded_hops` (default 10), `rate_limit_redis_timeout_seconds` (default 0.2). `TRUSTED_PROXY_CIDRS` already existed from Phase 1 (D64) and is now actually consulted.

Validation happens once, at `create_app()` time (`main.py`): a production start with `rate_limiting_enabled=True` and a secret under 32 characters raises `RuntimeError` immediately; an invalid `RATE_LIMIT_POLICY_OVERRIDES_JSON` (`rate_limit_policy.parse_policy_overrides`) raises `RuntimeError` with the specific validation failure. Development/test may leave the secret blank — an ephemeral one is generated via `secrets.token_urlsafe(32)`, exactly like `SESSION_SECRET`. `.env.example` documents every new variable with placeholders only (verified by the existing `check_env_example_secrets.py` pre-commit hook, which passed).

## Trusted-proxy resolution

`apps/api/src/lifeflow_api/rate_limit_ip.py`. The immediate socket peer (`request.client.host`) is the sole trust anchor. `X-Forwarded-For` is read only when that peer is itself inside a parsed `TRUSTED_PROXY_CIDRS` network; an empty allowlist (the default) trusts nothing. A trusted chain is walked right-to-left, skipping hops that are themselves trusted, to the first untrusted address (an all-trusted chain falls back to the leftmost hop). IPv4-mapped IPv6 addresses normalise to IPv4. A malformed value, an empty header, or a chain longer than `RATE_LIMIT_MAX_FORWARDED_HOPS` falls back to the immediate peer and logs `rate_limit.forwarded_header_rejected` (no raw value). 14 tests in `test_rate_limit_ip.py` cover direct client, spoofed header from an untrusted peer, one and multiple trusted proxies, mixed chains, an all-trusted chain, IPv4/IPv6/IPv4-mapped, malformed/empty/overlong chains, overlapping CIDRs, and a missing transport peer.

## Privacy-safe Redis keys

`hash_subject()` in `rate_limiter.py` computes `HMAC-SHA256(RATE_LIMIT_KEY_SECRET, "{subject_type}:{subject}")`; the bucket key is `f"{prefix}:{policy_code}:{digest}"`. Redis never receives a raw user id, IP, email, or path parameter — proven directly against a real Redis instance by `test_rate_limiter.py::test_redis_stores_no_raw_subject_or_payload` (asserts the literal subject string is absent from both the key and the stored hash) and, live during the manual smoke test, by `redis-cli KEYS/HGETALL` inspection (see below).

## Atomic limiter algorithm

One Lua script (`rate_limiter.py::_BUCKET_SCRIPT_LUA`) performs the entire read → refill → consume → write cycle inside a single Redis `EVAL`, using Redis's own `TIME` command as the clock (no client-clock dependency, no cross-instance skew). `RateLimiter.check()` wraps the call in `asyncio.wait_for` bounded by `RATE_LIMIT_REDIS_TIMEOUT_SECONDS` and catches every exception, returning a `degraded=True, allowed=True` decision rather than propagating. Bucket TTL is `min(max(refill_window_seconds*2, 60), 7 days)`, so abandoned keys always expire. 13 tests in `test_rate_limiter.py` (real Redis, logical DB 5) cover first-request-allowed, capacity enforcement, positive-and-bounded retry-after, refill after a window, 20-way concurrent `asyncio.gather` never overshooting a capacity-5 bucket, per-user/per-IP/per-policy isolation, route-parameter-does-not-bypass, key expiry, no-raw-payload, two independent `RateLimiter` instances (simulating two API processes) sharing one bucket correctly, and fail-open against an unreachable Redis address.

## Redis failure behaviour

Fail-open is the ratified posture (ADR 0005 D64): any Redis exception allows the request. This is proven against a **real route**, not just the limiter in isolation: `test_rate_limiting_api.py::test_redis_unavailable_fails_open_on_a_real_route` and `test_redis_failure_creates_no_duplicate_execution` point `redis_url` at an unreachable address and drive a full approve→execute→replay-execute flow through the real API, asserting both requests succeed and return the identical execution record — proving Redis failure never creates a duplicate side effect. No existing database guard was touched to achieve this: `ActionProposalService.execute()`, `confirm_operation()`, and every other pre-existing idempotency/binding check are byte-for-byte unmodified.

## Route integration

One dependency factory, `rate_limit_deps.rate_limit_dependency(code)` (validated eagerly against the closed registry — an unregistered code raises `KeyError` at import time, not request time), wrapped by `RateLimited(code)` for use as `dependencies=[RateLimited("policy_code")]` on every route decorator. Authenticated policies resolve the subject via the existing `CurrentUser` dependency (`user.id`); anonymous policies resolve it via `resolve_client_ip`. No route is charged twice: each declares exactly one `RateLimited(...)`, and the one route needing data-dependent policy selection (deletion confirm) calls `enforce_rate_limit` directly exactly once instead of stacking a second dependency.

## Idempotency interaction

Every policy documents (`applies_to_idempotent_replays=True`, the only value used) that a replay still consumes a token — broad request-volume control is deliberately a separate concern from database idempotency, which stays authoritative regardless of what the limiter allowed through. Proven end-to-end: `test_idempotent_replay_consumes_budget_but_never_duplicates` executes a proposal, replays the same execute call (still under budget — returns the identical `execution` object, confirming `ActionProposalService.execute()`'s existing short-circuit is untouched), then shows a third call is blocked. `test_execution_blocked_by_rate_limit_creates_no_duplicate_and_no_uncertain` proves a blocked execution attempt on a *different* approved proposal creates no execution record at all (`execution is None`) and never marks anything `uncertain`.

## Safe 429 contract

`errors.py` gained `RateLimitExceededError(policy_code, retry_after_seconds)` and its handler, reusing the pre-existing `{"error": {"code", "message", "correlation_id"}}` envelope (429 was already mapped to `"rate_limited"` in `_STATUS_CODES` before this phase) plus one new optional field, `retry_after_seconds` (bounded, non-negative int), and a matching `Retry-After` header. Verified live: a blocked `dev-login` returned `HTTP/1.1 429`, `retry-after: 1800`, and a body containing only `code`/`message`/`correlation_id`/`retry_after_seconds` — no policy code, digest, subject, or IP (`test_anonymous_auth_route_returns_429_with_safe_body_and_header`, `test_429_response_never_leaks_subject_or_policy_internals`).

## Frontend behaviour

`apps/web/src/lib/api.ts` gained `RateLimitError extends ApiError` (a narrowed, always-present `retryAfterSeconds: number`, sourced from the body field or falling back to the `Retry-After` header, then a safe default of 30). `apps/web/src/components/RateLimitNotice.tsx` provides `rateLimitMessage()`/`<RateLimitNotice>` — a rounded, accessible (`role="alert"`) message, e.g. "Try again in about 42 seconds." / "about 2 minutes.", never a live countdown. Wired into: Today (`generate-brief` — the existing brief stays visible, the button re-enables, no auto-resubmit), `ActionProposalPanel` (approve/execute — the proposal's own status and any editor draft are left untouched, never shown as an uncertain outcome), and Connections (`syncGoogle`, and `DeletionControls`'s preview/confirm/cancel — the typed confirmation phrase and reviewed preview counts are never cleared, and account-deletion's redirect-to-signed-out only fires on genuine terminal success, never on a 429). Double-click protection is unchanged (`pending`/`busy` state guards predate this phase).

## Observability and privacy

`enforce_rate_limit()` logs only `rate_limit.redis_check_failed policy=<code>` on a limiter error; `resolve_client_ip` logs only `rate_limit.forwarded_header_rejected reason=<...>` on a malformed chain — neither ever includes a raw IP, subject, digest, header value, or request body. Verified live in the manual smoke test (see below): the structured JSON log line for a Redis outage contained only the policy code and a correlation id.

## Tests added

- `apps/api/tests/test_rate_limit_policy.py` — 18 tests (registry validation, override parsing, invalid overrides, effective-policy resolution).
- `apps/api/tests/test_rate_limit_ip.py` — 17 tests (trusted-proxy IP resolution, full matrix from section 6 of the spec).
- `apps/api/tests/test_rate_limiter.py` — 13 tests, real Redis (atomic algorithm, concurrency, isolation, expiry, fail-open).
- `apps/api/tests/test_rate_limiting_api.py` — 13 tests, real Postgres + Redis (route inventory completeness, 429 contract, hidden-parameter isolation, execution/idempotency safety, deletion-confirm policy resolution, exemptions, Redis-down fail-open on real routes).
- `apps/api/tests/test_rate_limit_uvicorn_regression.py` — 2 tests, a real `uv run uvicorn` subprocess over a real socket (closure addendum): proves Uvicorn's own header handling, not just the application-level resolver in isolation, correctly ignores spoofed forwarding and correctly resolves a trusted proxy chain.
- Backend total: **63 new tests** (verified via `pytest --collect-only` on 2026-07-24), mapped against the spec's 60-item list — the full policy/IP/algorithm/config matrix (items 1–27) and the core API-integration and correctness/degradation/privacy matrix (items 28–60) are covered by representative, non-redundant tests per route class (e.g. one `authenticated_read` test stands for every route sharing that policy) rather than one literal test per named route, since the underlying dependency is identical code for all of them.
- `apps/web/src/lib/api.test.ts` — +3 tests (`RateLimitError` construction from body/header/default).
- `apps/web/src/app/today/page.test.tsx` — +1 test.
- `apps/web/src/components/ActionProposalPanel.test.tsx` — +2 tests.
- `apps/web/src/app/connections/page.test.tsx` — +4 tests.
- Frontend total: **10 new tests**, covering sync/brief/approval/execution/deletion-preview/deletion-confirm/account-deletion 429 handling, Retry-After display, and no-colour-only signalling (all use `role="alert"` semantic markup, not colour).
- `apps/web/e2e/rate-limiting.spec.ts` — 3 new Playwright journeys (A/B/C, see below).

## Real-Redis concurrency results

`test_rate_limiter.py::test_concurrent_requests_cannot_overshoot_capacity`: 20 concurrent `asyncio.gather` calls against a capacity-5 bucket — exactly 5 allowed, every run. `test_multiple_limiter_instances_share_the_same_bucket`: two independent `RateLimiter`/Redis-client pairs (simulating two API processes) correctly observe one shared bucket. Both passed on every run during this phase's development.

## Playwright results

Three new journeys in `apps/web/e2e/rate-limiting.spec.ts`, run against the real API, a real ARQ worker, real PostgreSQL, and real Redis, with `playwright.config.ts` enabling `RATE_LIMITING_ENABLED=true` and test-only overrides (`brief_generate`/`external_execution` capacity 2, `deletion_confirm_cancel` capacity 1, `anonymous_auth` capacity 100 — sized to the highest legitimate per-user call count any *existing* spec already makes, so this phase adds zero risk of destabilising the other seven journeys, which are all authenticated-user-keyed with their own fresh dev-login user per test):

- **Journey A** — two `generate-brief` clicks succeed (v1, v2); a third is blocked with a visible `rate-limit-notice` (`role="alert"`, "Try again in…"); the existing brief stays on screen; no automatic resubmission over 1.5s.
- **Journey B** — two proposal executions succeed; a third approved proposal's execution is blocked before any executor runs (`execution: null` via API), never shown as uncertain, while the first execution remains retrievable and a replay of it is proven not to duplicate.
- **Journey C** — a preview+cancel on a *separate* (secondary-account) operation exhausts the shared `deletion_confirm_cancel` budget; a confirm attempt on the *reviewed* google-account operation is then blocked, the typed phrase and preview counts remain exactly as they were, no operation advances past `previewed`, and exactly one confirm request was ever sent.

**Full suite (10 journeys — 7 pre-existing + 3 new) run twice consecutively: 10/10 passed both times** (`CI=1 ./scripts/e2e.sh`, ~1.8–2.3 min each run).

## Full verification results

Table reflects the final closure state (2026-07-24, after the closure addendum below). See the addendum for the delta from the original pass.

| Gate | Result |
|---|---|
| `uv run ruff format --check .` | pass (164 files) |
| `uv run ruff check .` | pass |
| `uv run mypy` | pass (84 source files — mypy is scoped to `packages = ["lifeflow_api"]`, i.e. `src/` only; `tests/` is intentionally not type-checked by this gate) |
| `uv run pytest --cov=lifeflow_api` (full, incl. integration) | **716 passed**, **92% coverage** (6946 statements, 579 missed) |
| Focused rate-limit tests (5 files together) | **63 passed** in 14.85s |
| Real-Redis concurrency | 2/2 dedicated tests (20-way `asyncio.gather` bounded to capacity 5; cross-instance shared-bucket test) |
| `pnpm web:lint` (ESLint) | pass — 41 files, 0 errors, 0 warnings |
| `pnpm web:typecheck` (tsc) | pass |
| `pnpm web:test` (Vitest) | **86 passed** |
| `pnpm web:format:check` (Prettier) | pass |
| `pnpm web:build` | pass (production build succeeds, 12 static routes + 1 dynamic) |
| `./scripts/generate-contracts.sh` | zero drift |
| `./scripts/run-evals.sh det` | pass — 1.00 actionable precision (16 TP/0 FP), 0.94 recall, 6/6 deadline accuracy, 0/20 duplicates, 6/6 priority-band agreement, 0 unsafe outputs |
| `./scripts/run-evals.sh actions` | **PASS** — 3 proposals composed, 0 grounding/schema/fingerprint/usefulness/injection-leak violations, deterministic under repeat composition, approval bindings differ by payload/type/version |
| `./scripts/e2e.sh` (full Playwright suite) | **10/10 passed, twice consecutively** (1.3 min, 1.7 min) |
| `uvx pre-commit run --all-files` | all **11** hooks pass (10 original + the new `check-uvicorn-launch-safety`) |
| `uvx detect-secrets scan --baseline .secrets.baseline` | zero new findings; baseline diff reverted to byte-identical (only a `generated_at` timestamp changed, no real finding) |
| `gitleaks protect --staged` | staged-diff mode, no leaks |
| `gitleaks detect --no-banner --redact` (full history) | passed against the complete history through the final Phase 4 tip, no leaks |
| `python3 scripts/check_uvicorn_launch_safety.py` | pass — all 6 known launch sites set a safe proxy posture; verified as a genuine detector (negative-tested against `demo.sh` with the flag removed, and against a rogue new launcher file) |
| `uv run alembic heads` | single head, `0011` — **no new migration** |
| `git diff --check` | clean |

## Manual smoke-test results

Run against the real local stack (`docker compose up -d db redis`, a manually-launched `uv run uvicorn ... --forwarded-allow-ips=""`) with `RATE_LIMITING_ENABLED=true` and small overrides:

1. Authenticated read (`authenticated_read`, capacity 3): calls 1–3 returned 200, call 4 returned 429. ✅
2–3. Anonymous auth (`anonymous_auth`, capacity 2): calls 1–2 returned 200, call 3 returned 429 with `retry-after: 1800` (mathematically correct: window 3600s / refill 2 → 1800s per token). ✅
4. `provider_sync`/`proposal_approval`/`external_execution`/deletion policies are independently registered and unit/integration-tested (see above); not separately re-poked manually beyond the auth/read pair, to keep the manual pass focused on the properties automation cannot reach (real ASGI-server behaviour).
5. **Spoofed `X-Forwarded-For` from an untrusted peer — found a real gap, then fixed it.** With `TRUSTED_PROXY_CIDRS` unset (empty, the default) and a plain `uv run uvicorn ...` launch (no extra flags), a curl request carrying `X-Forwarded-For: 9.9.9.9` was **not** blocked and created a **second** Redis bucket for `9.9.9.9` — uvicorn's own `--proxy-headers`/`--forwarded-allow-ips` default (`127.0.0.1`) rewrites `request.client` to the forwarded value for *any* connection from loopback, before this application's own `TRUSTED_PROXY_CIDRS` check ever runs, silently defeating it. Confirmed via the uvicorn access log (`9.9.9.9:0 - "POST /auth/dev-login" 200 OK`). **Fix:** every documented uvicorn launch now passes `--forwarded-allow-ips=""` — `CLAUDE.md`, `README.md`, `scripts/demo.sh`, `apps/web/playwright.config.ts`, and `apps/api/src/lifeflow_api/main.py`'s own module docstring were all updated, each with an inline explanation. Re-tested after the fix: the spoofed request was correctly blocked (429) and the uvicorn access log showed the true peer (`127.0.0.1`) throughout. This is now also documented in ADR 0005 D81 and the threat-model's new "Rate limiting" section.
6. With `TRUSTED_PROXY_CIDRS=127.0.0.1/32` and `--forwarded-allow-ips=""`: a direct call, a call forwarded as `198.51.100.7`, and a call forwarded as `198.51.100.8` produced **three distinct Redis buckets** — trusted-proxy resolution correctly attributes budget per real claimed client. ✅
7. Redis inspected directly (`redis-cli KEYS`/`HGETALL`): every key is `ratelimit:v1:<policy>:<64-char hex digest>`; hash fields are only `tokens`/`ts`. No email, user id, or IP appears anywhere in Redis. ✅
8. Redis stopped (`docker compose stop redis`): `dev-login` and `/health` both continued returning 200 — fail-open confirmed against a real outage, not just a mocked one. ✅
9. Redis restarted: limiting resumed correctly on the very next check (call 3 of a fresh capacity-2 bucket was blocked again). ✅
10. Log file inspected: the only rate-limiter log lines during the outage were `rate_limit.redis_check_failed policy=anonymous_auth` with a correlation id — no raw IP, subject, or digest. ✅
11. Existing database idempotency guards were not re-poked manually (already proven live above under "Idempotency interaction" and by the full automated suite) since the manual pass's purpose was specifically to catch what automation structurally cannot (real ASGI-server/process-level behaviour) — which it did.
12. Worker/scheduled jobs: not manually re-verified in this pass; unaffected by any code in this phase (no change to `worker_app.py`, `scheduled_briefs.py`, or any job payload), and the full Playwright suite (which exercises the real worker for deletion journeys) passed twice.

All manually-started processes (the smoke-test uvicorn instances) were stopped by the same session that started them. Two pre-existing, user-owned dev servers (`uvicorn --reload` and `next dev`, running since before this task) were occupying ports 8010/3000 and were stopped only after explicit user confirmation, so a clean e2e/manual-test run could proceed without silently reusing a stale, non-rate-limited process.

## Files changed

Final state, 55 paths (`git status --porcelain=v1`, 2026-07-24, after the closure addendum): 13 new, 42 modified.

**New (13):** `apps/api/src/lifeflow_api/rate_limit_policy.py`, `rate_limit_ip.py`, `rate_limiter.py`, `rate_limit_deps.py`; `apps/api/tests/test_rate_limit_policy.py`, `test_rate_limit_ip.py`, `test_rate_limiter.py`, `test_rate_limiting_api.py`, `test_rate_limit_uvicorn_regression.py`; `apps/web/src/components/RateLimitNotice.tsx`; `apps/web/e2e/rate-limiting.spec.ts`; `scripts/check_uvicorn_launch_safety.py`; `docs/delivery/reports/stage-09-phase-4.md` (this file).

**Modified (42):** every router file listed in "Route and policy inventory" above; `config.py`, `errors.py`, `main.py` (wiring + docstring fix); `pyproject.toml` (added `redis>=5.0` as a direct dependency, plus the `test_rate_limit_uvicorn_regression.py` S603/S607 per-file-ignore)/`uv.lock`; `.env.example`; `apps/web/src/lib/api.ts`, `apps/web/src/app/today/page.tsx`, `apps/web/src/components/ActionProposalPanel.tsx`, `apps/web/src/app/connections/page.tsx`, `apps/web/src/app/connections/DeletionControls.tsx`, `apps/web/playwright.config.ts`, plus their four test files; `CLAUDE.md`, `README.md`, `scripts/demo.sh` (the `--forwarded-allow-ips=""` fix); `.pre-commit-config.yaml`, `.github/workflows/secret-scan.yml` (new `check-uvicorn-launch-safety` hook/step); `docs/architecture/adr/0005-stage9-privacy-hardening.md` (D81 + the Uvicorn-defect subsection), `docs/delivery/assumptions-and-decisions.md`, `docs/delivery/stage-plan.md`, `docs/delivery/metrics.md`, `docs/security/threat-model.md` (the Uvicorn-defect bullet).

## Migration decision

No migration was needed or created. Rate-limit state lives entirely in Redis (ephemeral, TTL-bounded) plus validated environment configuration. Single Alembic head remains `0011`.

## Delivery Phase 5 boundaries

Nothing in this phase touched telemetry, structured-log expansion beyond the limiter's own two safe log lines, provider-outage resilience, or PII log review — all remain Delivery Phase 5. No CAPTCHA, account suspension, IP deny list, or per-user configurable limit was added (all explicitly out of scope per the phase brief and confirmed absent by code inspection).

## Commit recommendation

Committed locally as six coherent commits on top of the approved parent `a50cf06`:

1. `feat(stage-9): add privacy-safe Redis rate limiter` — limiter core, configuration, safe 429 contract, app wiring, dependency and `.env.example`.
2. `feat(stage-9): apply closed rate-limit policies` — the 16 routers' policy declarations and the one runtime-resolved deletion-confirm selection.
3. `feat(stage-9): handle rate limits in the web interface` — `RateLimitError`, `RateLimitNotice`, and the five throttled surfaces.
4. `fix(security): enforce Uvicorn proxy trust boundary` — `--forwarded-allow-ips=""` at every live launch site, the launcher-safety validator, and its pre-commit/CI wiring.
5. `test(stage-9): verify rate limiting and proxy safety` — 63 backend tests, 10 frontend tests, 3 Playwright journeys.
6. `docs(stage-9): document rate limiting and abuse controls` — ADR 0005 D81, threat model, decision log, stage plan, metrics, and this report.

Phase 4 awaits remote finalisation. Do not tag, merge, or begin Delivery Phase 5 without explicit further authorisation.

---

## Closure addendum (2026-07-24) — three verification gaps closed

This addendum records what changed after the original report above was written and reviewed. The original report's verdict was "APPROVE DELIVERY PHASE 4 FOR REVIEW"; three residual gaps were identified and closed, and the verdict is now **APPROVE DELIVERY PHASE 4 FOR COMMIT**. Full detail (exact commands, exact numbers, negative-control proofs) is in the companion chat-delivered "Stage 9 Delivery Phase 4 Final Closure Report"; this addendum is the durable, in-repo summary.

1. **Exact staged-boundary security proof.** `git add -A` staged the complete 55-path Phase 4 boundary; `pre-commit run --all-files` (11/11 hooks), `gitleaks protect --staged` (0 leaks), `gitleaks detect` (full history, 38 commits, 0 leaks), and `detect-secrets` all ran against that exact staged state, then `git reset` restored the working tree with the index left empty. No unintended file (database, log, trace, cache, credential) was ever staged. All 3 inline `pragma: allowlist secret` comments this phase introduces were confirmed to gate an exact, obviously-synthetic literal each, never a pattern or wildcard.
2. **Real-Uvicorn trusted-proxy regression.** `apps/api/tests/test_rate_limit_uvicorn_regression.py` (2 tests) starts a real `uv run uvicorn` subprocess — not `httpx.ASGITransport`, which structurally cannot exercise Uvicorn's own header handling — and proves, over a real socket: a spoofed `X-Forwarded-For` from an untrusted peer never grants a fresh identity and the real shared peer is correctly throttled at capacity; and, with the peer explicitly trusted, two different forwarded addresses draw separate buckets while a malformed or excessive chain safely falls back to the peer. Both tests were verified as genuine regressions by a negative control (temporarily removing `--forwarded-allow-ips=""` reproduced the original defect: all three requests returned 200 instead of the third returning 429), then confirmed to pass again once reverted. No orphan process remained after either run.
3. **Uvicorn launcher inventory and validation.** Every file in the repository referencing a Uvicorn launch of this app was enumerated (`README.md`, `CLAUDE.md`, `scripts/demo.sh`, `apps/api/src/lifeflow_api/main.py`, `apps/web/playwright.config.ts`, the new regression test — all already safe — plus two frozen Stage 8 historical records that predate this flag's existence and are deliberately not rewritten). `scripts/check_uvicorn_launch_safety.py` encodes this exact classification and fails if any known site loses its safe flag or if a new, unclassified launch site appears anywhere in the tree (tracked or untracked); wired into both `.pre-commit-config.yaml` and `.github/workflows/secret-scan.yml`. Verified as a genuine detector against two negative controls (flag removed from `demo.sh`; a rogue new launcher file). Deployment guidance for a real reverse-proxy deployment is recorded in ADR 0005 D81 and the threat model: always keep `--forwarded-allow-ips=""` and configure `TRUSTED_PROXY_CIDRS` to the proxy's real address — Uvicorn's own independent header trust must never be the security boundary.

Also run and confirmed for the first time in this addendum: `./scripts/run-evals.sh actions` (PASS, 0 violations — not run and not reported in the original pass). All final gate numbers above reflect this closure state, not the original pass.
