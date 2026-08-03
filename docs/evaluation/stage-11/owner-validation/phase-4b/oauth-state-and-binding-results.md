# OAuth State, Nonce, and Account-Binding Results

**Status:** Verified, with 6 new tests closing coverage gaps found this phase · **Date:** 2026-08-01

Companion: [redirect-uri-and-origin-plan.md](redirect-uri-and-origin-plan.md) · [defect-register.md](defect-register.md)

## Already-covered, re-confirmed this phase

| Property | Mechanism | Evidence |
|---|---|---|
| Cryptographically strong state | `secrets.token_urlsafe(32/64)` (`google/oauth.py:46-64`) | `test_state_and_pkce_are_unique_per_call` |
| State expiry | `STATE_TTL_SECONDS = 600` (`oauth_state.py:15,69`) | `test_oauth_state_rejects_stale_flow` |
| State single-use | `request.session.pop(_SESSION_KEY, None)` unconditionally (`oauth_state.py:62`) | `test_oauth_state_is_single_use`; re-confirmed at the HTTP route level this phase (below) |
| State/session binding | Stored in the signed session cookie itself, not a shared store | implicit — no cross-session replay possible without the same cookie |
| Tamper rejection | `pending.get("state") != state` (`oauth_state.py:67-68`) | `test_oauth_state_rejects_wrong_state_value`, `test_callback_with_invalid_state_redirects_safely` |
| Purpose mismatch rejection | `pending.get("purpose") != purpose` (`oauth_state.py:65-66`) | `test_oauth_state_rejects_purpose_mismatch` |
| Cross-owner account binding rejection | `bound_user_id != request.session.get("user_id")` (`oauth_state.py:71-73`) | `test_oauth_state_connect_flow_binds_to_current_session_user` |
| PKCE (both flows) | `generate_pkce_pair()` in the shared `begin_oauth_flow` / verified at exchange (`google/oauth.py:46-64,161-180`) | `test_login_redirect_requests_openid_scope_only` (sign-in); `test_connector_connect_redirect_also_carries_pkce` (connector — added Stage 11A Phase 4C, correcting a documentation error, see below) |

## Gaps found this phase and closed

All six were found by inspecting the actual callback code against the governing instruction's §8 checklist, not by assuming a gap existed — each is now a passing regression test in `apps/api/tests/test_stage11a_phase4b_oauth_readiness.py`.

1. **Denied/cancelled consent (sign-in flow) left stale pending state.** Google's `?error=access_denied` redirect has no `code`, so it previously fell into the generic `missing_code` branch *before* `consume_oauth_flow` ever ran — the pending flow was never cleared and would otherwise sit in the session until its 600-second TTL lapsed. **Fixed**: `auth.py`'s `google_callback` now checks `error` first, clears the pending flow via a new `clear_pending_oauth_flow()` helper, and redirects with a distinct `auth_error=access_denied` (the raw Google `error` value is never reflected into the redirect). Proven by `test_signin_denied_consent_redirects_safely_and_clears_pending_flow`, which also proves the original state can no longer be replayed afterwards.
2. **Same gap in the connector-consent flow.** Identical fix in `connected_accounts.py`'s `google_connector_callback`. Proven by `test_connector_denied_consent_redirects_safely_and_clears_pending_flow`.
3. **Replay of an already-consumed sign-in callback was untested at the HTTP route level.** The underlying mechanism (`consume_oauth_flow`'s unconditional pop) already made this safe; only the end-to-end proof was missing. Proven by `test_replaying_a_consumed_signin_callback_is_rejected` — first call succeeds, immediate replay of the same `code`+`state` returns `invalid_state`.
4. **Callback after logout was untested.** `CurrentUser`'s session dependency already rejects an unauthenticated request before the route body ever runs, so this was already safe by construction; only the end-to-end proof was missing. Proven by `test_connector_callback_after_logout_is_unauthorised` (login → begin connect flow → logout → replay callback → `401`).
5. **Empty-string `state` parameter was untested.** `code is None or state is None` does not catch an empty string (`"" is not None`), so this exercises the real `consume_oauth_flow` state-mismatch path rather than a hypothetical one. Proven by `test_signin_callback_with_empty_state_is_rejected_not_crashed` — no crash, safe `invalid_state` redirect.
6. **Repeated/duplicated `state` query parameter was untested.** FastAPI/Starlette resolves this to a single value without raising; proven by `test_signin_callback_with_repeated_state_param_is_rejected_not_crashed` to redirect safely either way (`invalid_state` or `missing_code`, never a 500).

## Corrected during Stage 11A Phase 4C (see defect-register.md)

- **"No PKCE on the connector-consent flow" was never true.** This phase originally recorded PKCE as sign-in-only and treated the connector flow's absence of it as a non-blocking P2. Direct inspection during the Phase 4C integrity check showed `begin_oauth_flow` — shared by both flows — unconditionally generates and stores a PKCE pair regardless of `purpose`, and the connector flow's authorization URL and token exchange both use it exactly like sign-in. Closed with a new regression test, `test_connector_connect_redirect_also_carries_pkce`; no code change was needed.

## Concurrent-callback handling

Not separately tested this phase. `consume_oauth_flow`'s pop-then-validate sequence runs against the same in-process session-cookie deserialization per request; a genuinely concurrent pair of requests carrying the *same* session cookie and the *same* `state` would race on which one observes the pending flow first, but this requires an attacker (or the legitimate user) to fire two simultaneous requests with an identical, valid session cookie and state value — a narrow window with no plausible benign trigger (a normal browser redirect is a single request) and no demonstrated exploit path beyond what single-use already prevents for any single successful completion. Recorded as an explicit non-blocking observation rather than fabricated as either "proven safe" or "a defect" — a genuine concurrent-request test would need to be added before any claim stronger than this is made.
