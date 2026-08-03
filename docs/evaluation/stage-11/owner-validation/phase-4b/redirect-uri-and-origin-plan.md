# Redirect URI and Origin Plan

**Status:** Verified against the actual implementation · **Date:** 2026-08-01

Companion: [oauth-state-and-binding-results.md](oauth-state-and-binding-results.md) · [google-cloud-project-plan.md](google-cloud-project-plan.md)

## Exact planned values (placeholders — no live secret)

| Value | Configured as | Current value (local dev) |
|---|---|---|
| Local frontend origin | `apps/web` dev server | `http://localhost:3000` |
| Local API origin | `apps/api` dev server | `http://localhost:8010` |
| OIDC (sign-in) OAuth callback URI | `GOOGLE_OIDC_REDIRECT_URI` (`config.py:68`) | `http://localhost:8010/auth/google/callback` |
| Connector-consent OAuth callback URI | `GOOGLE_CONNECTOR_REDIRECT_URI` (`config.py:73`) | `http://localhost:8010/connected-accounts/google/callback` |
| Logout/completion return route | Frontend route, not a Google-facing URI | `apps/web`'s post-logout redirect target (session-cleared, no Google involvement) |
| Permitted development origins | `http://localhost:3000`, `http://localhost:8010` | as above |
| Prohibited wildcard origins | Any `*`-containing or non-exact-match redirect URI | never configured; Google itself rejects wildcard redirect URIs |
| HTTPS requirement | Non-`localhost` environments only | not applicable yet — Phase 4B and the eventual soak period are local-only |
| Production placeholder requirement | A future Stage 12+ deployment would need HTTPS callback URIs on a real domain | not defined in this phase — out of scope |

## Verification against the actual implementation

- **Callback route is server controlled.** `/auth/google/callback` (`auth.py:120`) and `/connected-accounts/google/callback` (`connected_accounts.py:100`) are fixed FastAPI routes; the redirect URI sent to Google is read from `Settings`, never from any request input.
- **Redirect target is allowlisted.** There is nothing to allowlist against beyond the single configured value — the same string is used both when building the authorization URL and at token-exchange time (`auth.py:110,140`; `connected_accounts.py:90,124`), so no second, attacker-controllable value can ever diverge from it.
- **No open redirect exists.** Confirmed by inspection: neither callback route accepts or forwards to an arbitrary caller-supplied URL; both redirect only to fixed frontend routes with a bounded `auth_error=`/`connect_error=` query parameter from a closed enum of values (`auth.py:128-156`; `connected_accounts.py:112-130`).
- **Callback state is validated.** See [oauth-state-and-binding-results.md](oauth-state-and-binding-results.md).
- **PKCE is used by both flows, not just OIDC sign-in.** `begin_oauth_flow` (`oauth_state.py:33-56`) is the single function both the sign-in and connector-consent routes call; it unconditionally calls `generate_pkce_pair()` and stores `code_verifier` in the session regardless of `purpose` — only `nonce` is conditional on `include_nonce=True` (OIDC-only, since the connector flow never exchanges an ID token). `connected_accounts.py:98`'s `connect_google` passes `code_challenge=pkce.challenge` to `build_authorization_url`, which unconditionally embeds `code_challenge`/`code_challenge_method=S256` (`google/oauth.py:78-92` — `code_challenge` is a required parameter, not optional), and the connector callback exchanges the code with `code_verifier=flow.code_verifier` (`connected_accounts.py:137`), exactly like sign-in. **This corrects an inspection error carried across two prior phases**: Phase 4B originally recorded "the connector-consent flow does not currently use PKCE" as a P2, and a later boundary-correction task revalidated only the premise's *security implication* against Google's documentation without re-checking the premise itself against LifeFlow's code. The premise was false the entire time — confirmed here by direct inspection plus a new regression test, `test_connector_connect_redirect_also_carries_pkce`, asserting `code_challenge`/`code_challenge_method=S256` on the connector `/connect` redirect. See [defect-register.md](defect-register.md) for the closure entry.
- **Session owner is revalidated.** `consume_oauth_flow` checks `bound_user_id != request.session.get("user_id")` (`oauth_state.py:71-73`) for the connector-consent flow.
- **Connected-account identity is revalidated.** `GoogleTokenService.get_valid_access_token_for_execution` re-checks `user_id`, provider, status, and scope under `SELECT ... FOR UPDATE` before every decrypt (`accounts.py:196-283`), so even a successfully-connected account cannot be used to serve a different owner's request later.
- **Callback errors are minimised and safe.** Every failure branch (`auth.py:128-156`; `connected_accounts.py:112-130`) redirects to a safe frontend route with a closed-vocabulary error code; no raw exception, stack trace, or Google error payload is ever surfaced to the browser.
- **Tokens never enter URL query strings exposed to the browser.** The authorization `code` appears once in Google's redirect to the server-side callback route (standard OAuth), is consumed server-side, and the resulting access/refresh tokens are never placed in a redirect URL, browser storage, or client-visible response — they are encrypted (Phase 4A `TokenKeyRing`) and stored only in PostgreSQL.
- **Tokens never enter browser storage.** Confirmed by the existing Phase 2/3 sentinel scans (browser-storage inspection) and by this flow's design: the callback route redirects to a plain frontend URL with no token-bearing parameter.
- **Callback cannot bind a Google account to the wrong LifeFlow owner.** `test_oauth_state_connect_flow_binds_to_current_session_user` (`test_google_oauth.py:376-382`) proves this directly for the connector flow.

## Findings requiring no code change

All bullet points above describe already-implemented, already-tested behaviour discovered by inspection, not gaps — including PKCE, which is present on both flows and required no code change; only its documentation and regression coverage were incomplete, both now corrected (see [defect-register.md](defect-register.md)).
