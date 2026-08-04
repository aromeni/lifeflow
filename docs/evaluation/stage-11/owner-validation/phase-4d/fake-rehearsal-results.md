# Stage 11A Phase 4D — Fake-Provider Rehearsal Results

**Status:** PASS — 3/3 end-to-end cycles clean; all 14 required injected scenarios covered · **Date:** 2026-08-04

## End-to-end rehearsal

`apps/api/scripts/stage11a_phase4d_connection_rehearsal.py` runs the exact controlled sequence the live checkpoint will follow — configuration preconditions → connect → callback → v2 credential-storage verification → four-call read-only smoke sequence (Gmail `getProfile`, `messages.list`; Calendar `get(primary)`, `events.list`) → write-kill-switch re-check → revoke+disconnect → revocation-confirmation truthfulness check → final residue check — against a dedicated, isolated local PostgreSQL database created and dropped every run, using `httpx.MockTransport` for every Google-facing call and the Phase 4B no-live-network safety net on the shared real client. **3/3 cycles pass.** Never a real Google account, project, or API call.

## The 14 required injected scenarios

Per the governing instruction §10, each scenario below must be proven safe. Most are already covered by existing, passing regression suites from prior phases — re-proving them inside this one rehearsal script would duplicate coverage rather than add it, so this table is the honest map from requirement to proof, not a claim that every scenario is a step inside the rehearsal script itself.

| # | Scenario | Proof | Result |
|---|---|---|---|
| 1 | Wrong account binding | `test_oauth_state_connect_flow_binds_to_current_session_user` (`test_google_oauth.py`) | Safe — cross-owner binding rejected |
| 2 | Unexpected scope | `test_connector_callback_stores_only_actually_granted_scopes` (`test_google_auth_and_connections_api.py`) — persists exactly what Google reports granted, never the requested set | Safe — partial/unexpected grant handled honestly |
| 3 | Second callback (replay) | `test_replaying_a_consumed_connector_callback_is_rejected` (**new**, `test_stage11a_phase4b_oauth_readiness.py`) — closes the connector-flow-specific gap the sign-in-only proof left open | Safe — `invalid_state` on replay |
| 4 | Missing refresh token | Procedural, per governing instruction §16: `first_google_readonly_smoke.py` decrypts and uses only the stored access token — it has no code path that could obtain or wait for a refresh token. If Google's live consent does not issue one, the operator's documented response (perform no read, revoke, disconnect, do not repeat consent) is a decision, not a code branch; `GoogleTokenService._decrypt_or_refresh` already raises `ReauthorisationRequiredError` rather than fabricating a token in any code path that does need one | Safe by design — no forced-refresh path exists |
| 5 | Unknown key version | `test_connection_gate_blocks_on_an_unknown_key_id` (Phase 4A, `test_stage11a_phase4a_credential_rotation.py`) | Safe — gate blocks, `clear_to_connect=false` |
| 6 | v1 credential envelope | `test_connection_gate_blocks_on_a_known_legacy_reference` (Phase 4A) | Safe — gate blocks |
| 7 | Gmail write attempt | `test_gmail_write_blocked_when_provider_writes_disabled` (**new**, `test_google_route_integration.py`) — real connected account, real approval, `provider_writes_disabled` before any Gmail HTTP request | Safe — zero Gmail calls beyond token exchange |
| 8 | Calendar write attempt | `test_calendar_write_blocked_when_provider_writes_disabled` (**new**) | Safe — zero Calendar calls |
| 9 | Call-budget exceedance | `test_default_budget_matches_the_governing_task_exactly`, `test_call_budget_is_enforced_per_operation` (**new**, `test_stage11a_phase4d_live_readonly_guard.py`) | Safe — refused before transmission |
| 10 | Provider 401 | `test_auth_error_classified_on_401_and_403` (`test_google_gmail_client.py`) | Safe — classified `GoogleAuthError`, no retry |
| 11 | Provider 429 | `test_transient_error_classified_on_5xx_and_429` (`test_google_gmail_client.py`) | Safe — classified `GoogleTransientError`, this phase's tooling never retries regardless of classification |
| 12 | Provider 500 | Same test as #11 (5xx and 429 share the transient classification) | Safe |
| 13 | Revocation uncertainty | `test_revoke_reports_true_only_on_an_objective_200` (**new**, `test_google_oauth.py`) plus `test_disconnect_google_never_requires_google_reachable`'s unreachable-revoke scenario (existing, `test_google_auth_and_connections_api.py`) | Safe — `revocation_confirmed` is `False`/`None`, never fabricated `True`; local disconnect proceeds regardless |
| 14 | Disconnect during inspection | The read-only smoke sequence and the disconnect step are two separate, sequential operator-invoked commands (`first_google_readonly_smoke.py` then the `/disconnect` route) — there is no background process that could disconnect concurrently with an in-flight smoke read. `GoogleTokenService`'s row-level `SELECT ... FOR UPDATE` (D19) already makes any *genuinely* concurrent credential access safe by construction, proven by the existing `test_google_token_execution_race.py` suite | Safe — no concurrent-access code path exists for this phase's own tooling to race against |

## Conclusion

No fake rehearsal reached Google. All 14 required scenarios are proven safe, twelve of them by direct regression tests (nine pre-existing from Phases 4A–4C, five new this phase), and two by structural/procedural argument where no code branch exists to test. The end-to-end rehearsal script proves the full happy-path sequence 3/3 clean using the same configuration gates, write-block, and revocation-truthfulness mechanism the live checkpoint will use.
