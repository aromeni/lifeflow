# Stage 11A Phase 6B — Pre-Live Gate Results

**Date:** 2026-08-05

Applied for the authorised connection window, verified directly:

| Setting | Value | Verified via |
|---|---|---|
| `GOOGLE_PROVIDER_CONFIGURED` | true | `/config`, readiness command |
| `GOOGLE_OIDC_SIGNIN_ENABLED` | false throughout | `/config`; `/auth/google/login` → 409 confirmed before and after every restart |
| `GOOGLE_CONNECTOR_OAUTH_ENABLED` | true only for the connection window, restored to false at cleanup | `/config`, readiness command |
| `GOOGLE_PROVIDER_WRITES_ENABLED` | false by default; true only for the single execution window; restored to false immediately after | readiness command before/during/after |
| Automatic sync | never triggered — one manual sync only | confirmed by design (Connections page sync is on-demand only) and by a single `last_sync_at` value |
| Scheduler / background provider workers | stopped for the whole phase except a short, explicitly-scoped window to process the imported-data deletion job | process list before/after |
| Fake-provider / dangerous test controls | unset | readiness command: `e2e_test_controls_disabled`, `fake_provider_override_unset` both PASS |
| Frontend: no Google sign-in control | confirmed | `/auth/google/login` blocked at 409; landing page reads only `google_oidc_signin_enabled` (Phase 6A.1) |
| Frontend: connector consent available | confirmed | Connections page rendered an active "Connect Google" control while the flag was true |

## Operational note (not a product defect)

Restarting the API process without a fixed `SESSION_SECRET` in the local `.env` generates a new ephemeral signing key each time (documented, intentional dev-only behaviour — "sessions reset on restart"), which logged the owner out mid-phase after a configuration-flag restart. A local-only `SESSION_SECRET` was set for the remainder of the session so further restarts did not repeat this; no application code changed, no security control was weakened, and the value is never committed (`.env` is gitignored).

A second, unrelated environmental issue also surfaced: an unrelated earlier task's use of a Linux Docker container (bind-mounting this repository for Phase 6A.1 visual-snapshot regeneration) had left the frontend's Turbopack dev cache (`apps/web/.next-dev`) containing container-internal path references, causing repeated dev-server panics ("flickering") when reused from the host. Cleared by deleting the cache directories; no application code changed.
