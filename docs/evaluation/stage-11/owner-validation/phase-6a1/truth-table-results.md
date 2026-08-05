# Stage 11A Phase 6A.1 — Frontend Capability Truth-Table Results

**Date:** 2026-08-05

All scenarios verified with mocked `/config` responses (unit tests, `apps/web/src/app/page.test.tsx` and `apps/web/src/app/connections/page.test.tsx`) and, for the provider-unconfigured case, against the real running application (no mocks) via the E2E and visual-regression suites, since the local demo/e2e environment has no Google integration wired for the connector path in CI and, after this phase's fix, correctly shows the disabled state on the landing page too regardless of leftover local client configuration.

| Scenario | Landing page (sign-in) | Connections page (connector) |
|---|---|---|
| Both disabled | No active control — safe text | No active control — safe text |
| Sign-in only | Visible and usable | No active control — safe text |
| Connector only (the exact Phase 6 incident configuration) | No active control — safe text | Visible and usable |
| Both enabled | Visible and usable | Visible and usable |
| Provider unconfigured | No active control — safe text | No active control — safe text |

## Independence, proven in both directions

- `page.test.tsx`: *"connector consent being enabled never displays Google sign-in — reproduces the exact Phase 6 incident configuration"* — `google_connector_oauth_enabled: true`, `google_oidc_signin_enabled: false` — sign-in stays hidden.
- `connections/page.test.tsx`: *"Google sign-in being enabled never displays the connector control — reproduces the exact Phase 6 incident configuration in reverse"* — `google_oidc_signin_enabled: true`, `google_connector_oauth_enabled: false` — the connector control stays hidden.

## Fail-closed on load failure

Both pages default their capability state to `false` before the `/config` fetch resolves and on outright fetch failure (network error, non-2xx): `page.test.tsx`'s *"before the config response arrives"* and *"when the config request fails outright"*; `connections/page.test.tsx`'s equivalent *"when the config request fails outright, the connector control fails closed"*.

An integrity review before merge found this coverage stopped short of a malformed-but-non-throwing response (e.g. a backend response missing the expected field entirely, with no network error). Added one test per page — *"a malformed config response (missing capability field) fails closed, not enabled"* — confirming the existing falsy-check (`config.google_oidc_signin_enabled` / `config.google_connector_oauth_enabled` both simply `undefined`) already handles this correctly; no implementation change was needed.

## Stale or manipulated frontend state cannot bypass backend guards

Not applicable as a distinct frontend test — by construction, the frontend performs no authorisation itself. Every control is a plain link to a real backend route (`/auth/google/login`, `/connected-accounts/google/connect`); hiding or showing it changes only what is easy to click, never what the backend accepts. `require_google_oidc_signin`/`require_google_connector_oauth` (Phase 6A, untouched by this phase) re-check their own flag on every request regardless of what any client believes. A manually-constructed request to either route with the corresponding flag disabled still receives 404/409, exactly as Phase 6A's own regression suite (re-run clean in this phase, see `automated-verification-results.md`) already proves.

## No secret values in the capability response

`test_config_reports_google_disabled_by_default` and `test_config_reports_google_enabled_when_wired_and_both_flows_on` assert the full, exact JSON body in both states — three booleans, nothing else. `connections/page.test.tsx`'s *"the capability gate never exposes a secret value"* independently asserts the `PublicConfig` type's only keys are the three booleans.
