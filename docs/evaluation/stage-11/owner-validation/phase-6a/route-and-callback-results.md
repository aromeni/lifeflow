# Stage 11A Phase 6A — Route and Callback Enforcement Results

**Date:** 2026-08-05

## Guard call sites, confirmed by direct code inspection

| Route | Guard |
|---|---|
| `GET /auth/google/login` | `require_google_oidc_signin` |
| `GET /auth/google/callback` | `require_google_oidc_signin` |
| `GET /connected-accounts/google/connect` | `require_google_connector_oauth` |
| `GET /connected-accounts/google/callback` | `require_google_connector_oauth` |

Each guard is called as the first line of its route handler, before any state creation, redirect construction, or (on callback) `consume_oauth_flow`/`exchange_code` call — unchanged in structure from the guard they replace, only the flag each checks has changed.

## Fail-closed behaviour, per flow, confirmed

- **404** when the provider isn't configured (`google_oauth_enabled=false` or no constructed client) — indistinguishable from a route that doesn't exist, matching the established Stage 7 convention.
- **409**, with a bounded, non-identifying message (`GOOGLE_OIDC_SIGNIN_BLOCKED_DETAIL` / `GOOGLE_CONNECTOR_OAUTH_BLOCKED_DETAIL`), when the provider is configured but that specific flow's flag is `false`. Never a provider URL, client identifier, secret, or callback value.
- No `location` header is ever present on a blocked response — confirmed by explicit assertion in every blocked-path test.
- The mock HTTP transport is instrumented to raise `AssertionError` if invoked at all while a flow is blocked; every relevant test confirms zero transport calls.

## Callback-specific enforcement

Both callbacks check their own guard **before** touching `consume_oauth_flow` or `oauth_client.exchange_code` — confirmed directly in `test_callbacks_are_blocked_before_code_exchange_or_token_storage` (now updated for the split) and the new `test_connector_enablement_never_enables_signin`/`test_signin_enablement_never_enables_connector`, which each hit the *callback* route (not just initiation) of the disabled flow with a syntactically valid `code`/`state` pair and confirm it's blocked before any state lookup occurs.

## Disabling a flow after initiation

Not separately tested this phase beyond what the existing single-use, TTL-bound state design already guarantees: `consume_oauth_flow` pops the pending state unconditionally on first use, so a flow disabled mid-flight would encounter the same guard check at the callback (blocked) before ever reaching state consumption — structurally equivalent to the "both blocked" scenario already covered.
