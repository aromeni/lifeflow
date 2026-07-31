# Stage 11A Phase 3 — Test-Control Isolation Results (S11A-P3-041)

**Status:** PASS · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md)

## Inventory (every test/demo control found)

- `E2E_TEST_CONTROLS_ENABLED` — the master flag gating every other control below.
- `GOOGLE_API_ORIGIN_OVERRIDE` — redirects Google API calls to the fake-provider server; gated behind the flag above.
- `DEMO_CLOCK_OVERRIDE` — deterministic clock for demo/eval/E2E determinism; gated behind the flag above.
- The fake-Google server itself (`lifeflow_api/testing/fake_google_server.py`) — a separate ASGI app, never imported by `main.py`, refuses to start without `LIFEFLOW_E2E_FAKE_GOOGLE=1`.
- Dev-login (`/auth/dev-login`) — gated by `settings.environment == "development"` only (a runtime 404 outside development, not a startup-refusal flag, since it is not itself capable of widening what a real session can do).

## Existing evidence, re-run fresh

`test_e2e_test_controls.py` (7 tests, all re-run and passing): `test_e2e_test_controls_enabled_refuses_to_start_in_production` and its demo-clock-override variant both assert `create_app()` raises `RuntimeError` when `E2E_TEST_CONTROLS_ENABLED=true` and `environment=production` are combined; `test_e2e_test_controls_enabled_alone_is_safe_in_production` confirms the flag alone (without an origin override) does not itself break production; `test_origin_override_is_ignored_unless_test_controls_are_enabled` and `test_test_controls_enabled_without_an_origin_override_keeps_real_google` confirm the override has no effect unless the master flag is also set; `test_demo_clock_override_alone_is_safe_in_production` confirms the clock override alone is inert without the master flag.

`test_dev_login_is_disabled_outside_development` (in `test_auth_api.py`, re-run) confirms dev-login 404s outside the `development` environment.

## Verified against this phase's requirements

Attempted production startup with each dangerous control enabled (via the existing test suite's exact scenarios, re-run): every combination that would matter (test controls + production) is refused with a `RuntimeError` before the app ever starts serving requests — never a runtime-only rejection that could race a request. No control is exposed through ordinary production routes (they are settings-driven, not request-driven — no request body/header/query parameter can activate any of them). No test credential is accepted in production (the fake-Google server is a wholly separate ASGI app that main.py never imports). Controls do not alter security expiry semantics (session `max_age`, token-cipher key-id matching, and rate-limit windows are all unaffected by any test-control state).

## Result

No gap found. This area was already comprehensively covered; this phase's contribution is fresh re-verification, one attempt per dangerous control as required.
