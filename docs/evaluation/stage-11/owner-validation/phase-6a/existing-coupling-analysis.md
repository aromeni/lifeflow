# Stage 11A Phase 6A — Existing Coupling Analysis

**Date:** 2026-08-05 · Written before any edit, per the governing instruction.

## Every Google auth/connector route and its guard

| Route | File | Guard called (before this phase) |
|---|---|---|
| `GET /auth/google/login` | `auth.py:102` | `require_google_oauth_initiation` |
| `GET /auth/google/callback` | `auth.py:118` | `require_google_oauth_initiation` |
| `GET /connected-accounts/google/connect` | `connected_accounts.py:86` | `require_google_oauth_initiation` |
| `GET /connected-accounts/google/callback` | `connected_accounts.py:105` | `require_google_oauth_initiation` |

All four routes called the same function, backed by the same flag (`google_oauth_initiation_enabled`).

## Exact root cause — a structural coupling, not operator error

`require_google_oauth_initiation` (`oauth_initiation.py`) checked exactly one boolean. There was no code path by which an operator could authorise the connector-consent flow without that same check also passing for OIDC sign-in, and vice versa. During Stage 11A Phase 6, the project owner enabled the flag specifically to authorise a connector reconnection (an explicitly scoped, owner-approved action); because the flag was shared, it also satisfied the guard on `/auth/google/login`, and the owner's subsequent "Sign in with Google" click completed a real OIDC flow that was never separately authorised. This is the guard functioning exactly as it was built — the incident is a direct, predictable consequence of the design, not a lapse in how it was used.

## What the coupling did and did not affect

| Layer | Affected by the shared flag? | Evidence |
|---|---|---|
| Initiation routes | **Yes** — both `/auth/google/login` and `/connected-accounts/google/connect` gated by the same flag | Direct code inspection |
| Callback routes | **Yes** — both callbacks gated by the same flag | Direct code inspection |
| UI visibility | **No** — the "Sign in with Google" and "Connect Google" links are static, unconditional; they were never capability-aware in either direction, before or after this fix | `apps/web/src/app/page.tsx`, `apps/web/src/app/connections/page.tsx` |
| Startup configuration | **Partially** — the master `google_oauth_enabled` + client-completeness validation was, and remains, entirely separate and correct; only the initiation-specific startup check (`GOOGLE_OAUTH_INITIATION_ENABLED=true requires GOOGLE_OAUTH_ENABLED=true`) referenced the shared flag | `main.py` |
| State generation | **No** — `begin_oauth_flow(request, purpose=...)` already tagged every generated state with its flow's purpose (`"signin"` vs. the connector's own purpose constant) | `oauth_state.py`, `auth.py`, `connected_accounts.py` |
| State consumption | **No** — `consume_oauth_flow(request, purpose=...)` already rejected a purpose mismatch (`OAuthStateError("OAuth flow purpose mismatch.")`) before this phase; reconfirmed fresh with new tests, not merely assumed | `oauth_state.py:73-74` |
| Account binding | **No** — the connector flow's `bind_user_id` and the resulting `ConnectedAccountService.store_tokens()` call are only ever reached from the connector callback's own code path; there is no shared binding logic between the two flows | `connected_accounts.py` |
| Session creation | **No** — only the sign-in callback ever writes `request.session["user_id"]` from a Google identity; the connector callback requires an existing session (`CurrentUser`) and never creates one | `auth.py`, `connected_accounts.py` |

**Conclusion: the coupling was isolated to the initiation/callback-gating layer alone.** Every other layer this instruction asked to check (UI, startup, state, binding, session) was already independent per-flow before this phase, and is reconfirmed, not newly built, by it.

## Tests that assumed the shared flag

| File | What it assumed |
|---|---|
| `test_stage11a_phase4c_oauth_initiation_block.py` | Both flows blocked/unblocked together via one flag |
| `test_google_auth_and_connections_api.py` | `GOOGLE_SETTINGS_OVERRIDES` set the one shared flag `true` for every test using it |
| `test_google_route_integration.py` | Same shared-override pattern, independent copy of the dict |
| `test_stage11a_phase4b_no_live_network_guard.py` | Inline construction with the shared flag |

## Active tooling that assumed the shared flag

| Script | Usage |
|---|---|
| `stage11a_phase4b_connection_rehearsal.py` | Constructed `Settings` with the shared flag to simulate the connector flow |
| `stage11a_phase4d_connection_rehearsal.py` | Same pattern |

Both use the connector flow only (via dev-login for the LifeFlow session, never OIDC sign-in) — updated to `google_connector_oauth_enabled=True` specifically, not the sign-in flag.
