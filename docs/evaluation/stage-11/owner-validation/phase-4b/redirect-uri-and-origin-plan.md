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
- **PKCE is used** for the flow that implements it (OIDC sign-in — `generate_pkce_pair()`, `google/oauth.py:46-64`, verified at token exchange `google/oauth.py:161-180`). The connector-consent flow does not currently use PKCE; this is recorded as a P2 observation in [defect-register.md](defect-register.md), revalidated on 2026-08-01 against Google's current web-server-flow documentation (`developers.google.com/identity/protocols/oauth2/web-server`) and the wider OAuth security-practice landscape:
  - LifeFlow's connector-consent flow is a **server-side confidential-client authorization-code flow**: `google_connector_client_secret` never leaves the backend, the authorization `code` is exchanged server-side, and tokens are never placed in a URL or browser-visible response (see the "Verification against the actual implementation" bullets above).
  - Google's current web-server-flow documentation does **not** mention PKCE for this flow at all — it is not described as required, recommended, or optional there; Google's own PKCE guidance is specifically for desktop/native apps, i.e. public clients that cannot hold a secret.
  - PKCE is nevertheless a genuine, non-zero defence-in-depth measure, not a theoretical one: RFC 9700 (OAuth 2.0 Security Best Current Practice) recommends PKCE for confidential clients as well as requiring it for public ones, and the draft OAuth 2.1 specification would require it for every client type, confidential or not.
  - **Conclusion, unchanged from the original finding**: this remains a non-blocking P2, not a P0/P1, because the flow's existing session-bound (`bind_user_id`), single-use `state` parameter already defends against the authorization-code-interception/replay scenario PKCE targets, in this specific server-side confidential-client shape. It is not claimed to offer "no benefit" — the closure condition (add PKCE before any non-local, public-client, or native deployment) stands, and becomes mandatory, not merely advisable, the moment the architecture changes to a public, native, or browser-held client instead of a confidential one.
- **Session owner is revalidated.** `consume_oauth_flow` checks `bound_user_id != request.session.get("user_id")` (`oauth_state.py:71-73`) for the connector-consent flow.
- **Connected-account identity is revalidated.** `GoogleTokenService.get_valid_access_token_for_execution` re-checks `user_id`, provider, status, and scope under `SELECT ... FOR UPDATE` before every decrypt (`accounts.py:196-283`), so even a successfully-connected account cannot be used to serve a different owner's request later.
- **Callback errors are minimised and safe.** Every failure branch (`auth.py:128-156`; `connected_accounts.py:112-130`) redirects to a safe frontend route with a closed-vocabulary error code; no raw exception, stack trace, or Google error payload is ever surfaced to the browser.
- **Tokens never enter URL query strings exposed to the browser.** The authorization `code` appears once in Google's redirect to the server-side callback route (standard OAuth), is consumed server-side, and the resulting access/refresh tokens are never placed in a redirect URL, browser storage, or client-visible response — they are encrypted (Phase 4A `TokenKeyRing`) and stored only in PostgreSQL.
- **Tokens never enter browser storage.** Confirmed by the existing Phase 2/3 sentinel scans (browser-storage inspection) and by this flow's design: the callback route redirects to a plain frontend URL with no token-bearing parameter.
- **Callback cannot bind a Google account to the wrong LifeFlow owner.** `test_oauth_state_connect_flow_binds_to_current_session_user` (`test_google_oauth.py:376-382`) proves this directly for the connector flow.

## Findings requiring no code change

All bullet points above describe already-implemented, already-tested behaviour discovered by inspection, not gaps. The one P2 observation (missing PKCE on the connector-consent flow) is recorded in [defect-register.md](defect-register.md) with an explicit non-blocking closure condition, consistent with the governing instruction's severity rules (§27) — it does not affect scope correctness, OAuth binding correctness, token security, or first-connection safety, since the existing session-bound single-use state already prevents the attack PKCE defends against in this server-side flow shape.
