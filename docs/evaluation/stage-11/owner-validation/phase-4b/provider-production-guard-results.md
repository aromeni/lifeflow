# Provider Production Guard Results

**Status:** Reviewed, 3 coverage gaps found and closed with new tests · **Date:** 2026-08-01

Companion: [oauth-state-and-binding-results.md](oauth-state-and-binding-results.md) · [preconnection-readiness-results.md](preconnection-readiness-results.md)

Per the governing instruction §23, the real-provider pathway must be verified unable to run under six conditions. All six guards already existed in `main.py`'s `create_app()`; this phase's review found that three had never been exercised by a test asserting their specific error, only implicitly as a side effect of unrelated test setup.

| Condition | Guard (already implemented) | Test coverage before this phase | Test coverage after this phase |
|---|---|---|---|
| Fake-provider origin override active incorrectly | `google_api_origin_override` is only ever read when `e2e_test_controls_enabled=True` (`main.py:178-187`), and that flag cannot be `True` in production (next row) | `test_origin_override_is_ignored_unless_test_controls_are_enabled` (existing) | unchanged — already covered |
| E2E test controls enabled in production | `main.py:103-104` raises `RuntimeError` unconditionally | `test_e2e_test_controls_enabled_refuses_to_start_in_production` (existing) | unchanged — already covered |
| Deterministic demo clock enabled in production | `demo_mode.py:44` only reads `demo_clock_override` when `e2e_test_controls_enabled=True` — transitively blocked by the same production guard as the row above; no separate flag exists to bypass this | Covered transitively by the E2E-test-controls test above; no code path exists to enable the demo clock independently | No new guard needed — verified by inspection that no independent enable path exists; recorded here rather than fabricating a redundant test for a code path that cannot exist |
| Synthetic credentials used in production | The only mechanism that could substitute synthetic/fake responses for real Google responses is the origin override, itself gated as above | Covered transitively | unchanged |
| Required session or encryption secrets missing | `main.py:64-65` (`SESSION_SECRET`); `main.py:127-141` (`TOKEN_KEY`/`TOKEN_KEY_ID` validity) | `SESSION_SECRET` guard was exercised only as an unasserted side effect of other tests' settings (e.g. `test_e2e_test_controls_enabled_alone_is_safe_in_production` had to explicitly set a valid `session_secret` to reach the code path it actually tests) — **no test asserted the `SESSION_SECRET` error message directly** | **New**: `test_missing_session_secret_refuses_to_start_in_production` |
| Callback origin unapproved | Not a runtime guard — the redirect URI is a single fixed configuration value with nothing else to compare against (see [redirect-uri-and-origin-plan.md](redirect-uri-and-origin-plan.md)) | N/A | N/A |
| OAuth configuration incomplete | `main.py:150-166` lists every missing required field | **No test asserted this error message directly** | **New**: `test_google_oauth_enabled_without_client_config_refuses_to_start`, `test_google_oauth_enabled_without_token_key_refuses_to_start` |
| Active key configuration invalid | `TokenCipherError` → `RuntimeError` (`main.py:139-140`) | `test_key_ring_rejects_*` family (existing, `test_token_cipher.py`) exercises `build_key_ring` directly; `main.py`'s wrapping into `RuntimeError` was exercised transitively by the Phase 4A merge-correction's `test_production_startup_refuses_the_development_key_id_default` | unchanged — sufficiently covered |

## New tests (this phase)

All three added to `apps/api/tests/test_stage11a_phase4b_oauth_readiness.py`, all passing:

- `test_missing_session_secret_refuses_to_start_in_production`
- `test_google_oauth_enabled_without_client_config_refuses_to_start`
- `test_google_oauth_enabled_without_token_key_refuses_to_start`

## No guard was weakened

Every guard's existing behaviour is unchanged. This review found test-coverage gaps, not implementation defects — each guard already worked correctly when inspected and manually exercised; only the standing regression protection (an assertion that would fail loudly if a future change broke the guard) was missing for three of them.
