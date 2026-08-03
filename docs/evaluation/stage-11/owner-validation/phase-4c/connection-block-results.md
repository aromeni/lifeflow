# Stage 11A Phase 4C — Connection-Block Results

**Status:** VERIFIED — configured environment remains blocked · **Date:** 2026-08-01

## Implementation

- `Settings.google_oauth_initiation_enabled` defaults to `false` independently of `google_oauth_enabled`.
- `oauth_initiation.py::require_google_oauth_initiation` is the shared gate for both Google initiation routes and both callback routes.
- An unconfigured integration retains the established 404 behaviour.
- A configured but unauthorised integration returns HTTP 409 with fixed safe guidance: OAuth is configured, but initiation remains blocked pending explicit owner authorisation.
- The gate runs before state creation, redirect construction, callback-state consumption, code exchange, token storage, or account binding.
- Enabling the initiation flag while `GOOGLE_OAUTH_ENABLED=false` fails application startup.
- Disconnect, sync, and execution semantics are not weakened or repurposed; this is an initiation/callback gate only.
- `.env.example` pins `GOOGLE_OAUTH_INITIATION_ENABLED=false`.
- The preconnection readiness command now verifies non-placeholder client presence, one-physical-client mapping, exact approved callbacks, and the blocked initiation state without displaying configuration values.

## Focused verification

`uv run pytest tests/test_stage11a_phase4c_oauth_initiation_block.py tests/test_google_auth_and_connections_api.py tests/test_stage11a_phase4b_oauth_readiness.py tests/test_stage11a_phase4b_no_live_network_guard.py tests/test_health.py`

- 44 collected, 44 passed.
- Both initiation routes: blocked, no `Location` header.
- Both callback routes: blocked before mock token transport; zero transport calls.
- Stored `ConnectedAccount` count after callback attempts: 0.
- Demo start while blocked: PASS and imports synthetic data normally.
- Existing enabled-flow, state/callback, production-guard, no-live-network, and public-config tests: PASS.

Focused Ruff and full mypy also pass (94 source files).

The post-installation focused boundary was then expanded and re-run: 152 OAuth, credential-rotation, no-live-network, state/callback, provider-client, closed-action-model, and Phase 4C tests passed sequentially.

## Safe negative control

The guard condition was temporarily disabled locally with a one-line synthetic canary. The focused test failed exactly as intended: expected 409, received 302 from the sign-in initiation route. The canary was immediately removed, never staged or committed, and the same test then passed (1/1). The complete 44-test focused set passed after restoration.

No credential, provider account, live network, OAuth endpoint, authorisation code, or Google API was used by the negative control.

## Current local readiness

After the owner installed the new Phase 4C client, the presence-only command reports:

- client configuration: configured, values not displayed;
- approved callbacks: PASS;
- OAuth initiation blocked: PASS;
- one physical client mapped to both logical flows: PASS;
- Google identity bindings: 0;
- credential-bearing connected-account rows: 0.

The command reports `READY`: locally configured and safe for a later separately authorised connection decision. `READY` does not enable initiation; `GOOGLE_OAUTH_INITIATION_ENABLED` remains false, and both initiation and callback paths remain blocked.
