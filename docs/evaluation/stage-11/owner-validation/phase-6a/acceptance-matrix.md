# Stage 11A Phase 6A — Acceptance Matrix

Built before editing, per the governing instruction. Status vocabulary follows the [Engineering Acceptance Contract](../../../../delivery/engineering-acceptance-contract.md).

## Section 1 — Starting boundary

| ID | Requirement | Verification | Result |
|---|---|---|---|
| P6A-001 | `main`/`origin/main`/`HEAD` all equal `6672292b9a9608676478701eb3c8f2ad4525d505` | `git fetch --prune`; `git rev-parse` | **Verified** |
| P6A-002 | Phase 6 decision is CONDITIONAL PASS, recorded accurately | Inspection of `phase-6/phase-6-decision.md` | **Verified** |
| P6A-003 | Gmail validation recorded accurately; Calendar validation remains incomplete | Inspection | **Verified** |
| P6A-004 | Account A and Account B both disconnected; OAuth access revoked | SQL: 0 credential-bearing rows | **Verified** |
| P6A-005 | Stored credentials zero; Google identity bindings zero | SQL query | **Verified** (0, 0) |
| P6A-006 | Imported provider data zero (for any real connection) | SQL query (Phase 6 account) | **Verified** |
| P6A-007 | Provider-write and OAuth-initiation flags disabled | `.env` grep | **Verified** (`false`, `false`) |
| P6A-008 | Working tree and index clean; no `stage-11*` tag | `git status`; `git tag -l` | **Verified** |
| P6A-009 | Readiness command reports 16/16 PASS, READY | `preconnection_readiness_check.py` | **Verified** |

## Section 2 — Coupling analysis (must precede any edit)

| ID | Requirement | Result |
|---|---|---|
| P6A-010 | Every Google auth/connector route, initiation guard, callback guard identified from code | **Verified** — `require_google_oauth_initiation` (`oauth_initiation.py`) is the single shared guard called at 4 sites: `auth.py:104,126` (OIDC login/callback), `connected_accounts.py:88,114` (connector connect/callback) |
| P6A-011 | Exact root cause identified, not attributed to operator error | **Verified** — one boolean flag (`google_oauth_initiation_enabled`) gates two logically distinct flows; enabling it for connector reconnection necessarily also armed sign-in, by construction, regardless of operator intent or care |
| P6A-012 | Whether OAuth *state* isolation was already sufficient, checked directly | **Verified** — `oauth_state.py`'s `purpose` field, checked in `consume_oauth_flow`, already makes cross-flow state substitution structurally impossible (`OAuthStateError("OAuth flow purpose mismatch.")`); this was true before this phase and is unchanged by it |
| P6A-013 | Master `google_oauth_enabled` flag's actual scope confirmed (config-presence, not initiation) | **Verified** — `main.py`'s startup validation only requires client config completeness; it does not itself authorise any flow |
| P6A-014 | Frontend control surface inspected | **Verified** — "Sign in with Google" (`page.tsx`) and "Connect Google" (`connections/page.tsx`) are static links with no independent capability check; the route itself is and remains the sole enforcement point (unchanged by this phase; noted, not expanded into a new capability-exposure API, per scope discipline) |
| P6A-015 | Every test file assuming the single shared flag identified | **Verified** — 4 files: `test_stage11a_phase4c_oauth_initiation_block.py`, `test_google_auth_and_connections_api.py`, `test_google_route_integration.py`, `test_stage11a_phase4b_no_live_network_guard.py`; 2 active scripts: both `*_connection_rehearsal.py` files |

## Section 3 — Split design and implementation

| ID | Requirement | Result |
|---|---|---|
| P6A-020 | Two independent config fields, both default `false` | **Verified** — `google_oidc_signin_enabled`, `google_connector_oauth_enabled` |
| P6A-021 | Neither settable by an HTTP request | **Verified** — `pydantic-settings` env-only, unchanged pattern from every existing flag |
| P6A-022 | Connector enablement never enables sign-in and vice versa | **Verified** — independent flags, independent guard functions, no shared mutable state |
| P6A-023 | Each initiation route checks only its own control | **Verified** — `auth.py` calls `require_google_oidc_signin`; `connected_accounts.py` calls `require_google_connector_oauth` |
| P6A-024 | Each callback route checks its own control before consuming state or exchanging a code | **Verified** — same two functions called at the top of each callback, before `consume_oauth_flow`/`exchange_code` |
| P6A-025 | Master `google_oauth_enabled` remains a prerequisite, never sole authorisation | **Verified** — both new guards still require `google_oauth_enabled` and a constructed client, matching the original guard's shape |
| P6A-026 | Startup rejects an enabled flow without the master enabled | **Verified** — two `RuntimeError` checks in `main.py`, one per flag |
| P6A-027 | No backward-compatible fallback restores the shared flag's behaviour | **Verified** — `google_oauth_initiation_enabled` is removed outright, not deprecated-but-functional |
| P6A-028 | PKCE, state, owner binding, redirect matching, token security unchanged | **Verified** — `oauth_state.py`, `google/oauth.py` untouched by this phase |

## Section 4 — State/callback isolation proof

| ID | Requirement | Result |
|---|---|---|
| P6A-030 | Sign-in state cannot be consumed by the connector callback | **Verified** (pre-existing + reconfirmed with a fresh test) |
| P6A-031 | Connector state cannot be consumed by the sign-in callback | **Verified** (pre-existing + reconfirmed with a fresh test) |
| P6A-032 | Connector callback cannot create a login session; sign-in callback cannot attach a connected account | **Verified** — structurally true by construction (each callback's own code path only ever performs its own side effect) |

## Section 5 — Configuration truth table (§6 of the governing instruction)

| ID | Requirement | Result |
|---|---|---|
| P6A-040 | Both disabled → both initiation and both callbacks blocked | **Verified**, new test |
| P6A-041 | Sign-in enabled, connector disabled → sign-in available, connector blocked | **Verified**, new test |
| P6A-042 | Sign-in disabled, connector enabled → connector available, sign-in blocked (**the exact Phase 6 incident, reproduced and now fixed**) | **Verified**, new test |
| P6A-043 | Both enabled → both available, still isolated from each other | **Verified**, new test |
| P6A-044 | Provider not configured → both blocked regardless of per-flow flags | **Verified**, new test |

## Section 6 — Regression and verification

| ID | Requirement | Result |
|---|---|---|
| P6A-050 | Exact Phase 6 incident reproduced as a named regression test, now fixed | **Verified** |
| P6A-051 | Full backend suite green | Pending execution |
| P6A-052 | Frontend/E2E suites green | Pending execution |
| P6A-053 | No real Google interaction occurred during this task | **Verified** at completion |
| P6A-054 | Readiness command reports the 4 distinct states | **Verified** |

## Section 7 — Documentation

| ID | Requirement | Result |
|---|---|---|
| P6A-060 | `.env.example` updated, no real values | **Verified** |
| P6A-061 | ADR 0003 receives a dated addendum, not a rewrite | **Verified** |
| P6A-062 | `assumptions-and-decisions.md` receives a new dated entry | **Verified** |
| P6A-063 | Phase 4C/4D/6 plans receive dated correction notes where they reference the old flag | **Verified** |
| P6A-064 | Historical Phase 6 evidence pack is not rewritten | **Verified** — untouched |
