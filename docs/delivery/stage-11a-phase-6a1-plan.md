# Stage 11A Phase 6A.1 — Align Frontend Google Flow Visibility with Split OAuth Controls

**Status:** Complete · **Date:** 2026-08-05

Companion: [Phase 6A.1 evidence pack](../evaluation/stage-11/owner-validation/phase-6a1/) · [Phase 6A plan](stage-11a-phase-6a-plan.md) · [Engineering Acceptance Contract](engineering-acceptance-contract.md)

## Objective

Phase 6A ([stage-11a-phase-6a-plan.md](stage-11a-phase-6a-plan.md)) separated the backend's Google OIDC sign-in and connector-consent authorisation into two independent, fail-closed flags. Its own merge report recorded a residual gap: the frontend never consumed either new flag. This phase closes that gap without touching backend enforcement, which remains authoritative and unchanged.

## Authorised scope

Project owner authorisation: `AUTHORISE FRONTEND GOOGLE FLOW-VISIBILITY ALIGNMENT`.

- Expose three independent, content-free capability booleans from `GET /config`.
- Make the landing page's "Sign in with Google" control follow only the sign-in capability.
- Make the Connections page's "Connect Google" control follow only the connector-consent capability, showing safe explanatory text instead of a control that would predictably fail after clicking.
- Add regression coverage proving independence, fail-closed behaviour, and no secret leakage.

## Prohibited scope (unchanged from Phase 6A)

Connecting either Google account, enabling either OAuth flow locally, initiating OAuth, calling Google, storing credentials, ingestion, provider writes, the soak period, recruitment, Stage 12, or tagging.

## What was wrong before this phase

`GET /config` returned a single field, `google_oauth_enabled`, computed from `google_wiring.google_integration_ready()` — a configuration-completeness check (is the OAuth client constructed, are the Gmail/Calendar clients constructed, is the token cipher present) that has nothing to do with either of Phase 6A's per-flow authorisation flags. The landing page used this single field to decide whether to render "Sign in with Google"; the Connections page didn't consult any capability field at all and rendered "Connect Google" unconditionally whenever no connected account existed.

The practical consequence, demonstrated directly during this phase's own verification (not merely asserted): with the local development environment's real Google client configuration left in place from earlier phases (`GOOGLE_OAUTH_ENABLED=true`) but both of Phase 6A's per-flow flags at their safe default (`false`), the landing page rendered a live-looking, clickable "Sign in with Google" button — one that would have received a `409 Google sign-in is configured, but is not currently authorised.` immediately on click. This is exactly the kind of mismatch the governing instruction anticipated. The pre-existing visual-regression baseline (`landing-darwin.png`) had captured this incorrect state as "correct," which is itself evidence the discrepancy was real and previously unnoticed, not hypothetical.

## What changed

- `apps/api/src/lifeflow_api/health.py`: `PublicConfig` now has three fields — `google_provider_configured`, `google_oidc_signin_enabled`, `google_connector_oauth_enabled`. Each per-flow boolean is computed as `provider_configured and settings.<flag>`, so a flow can never report enabled unless the provider is also configured — the frontend never has to combine the master state with a per-flow flag itself, and cannot get that combination wrong.
- `apps/web/src/app/page.tsx`: reads `google_oidc_signin_enabled` only (previously `google_oauth_enabled`).
- `apps/web/src/app/connections/page.tsx`: added an independent `/config` fetch (fail-closed default `false`), and a single `connectControl()` render function used at both call sites that previously rendered "Connect Google" unconditionally. When the connector capability is `false`, it renders safe explanatory text (`Connecting a Google account is not enabled in this environment.`) instead of a live link.
- `packages/contracts/`: regenerated from the updated OpenAPI schema.

## What did not change

Every backend OAuth guard, route, state-purpose binding, and startup validation from Phase 6A is untouched. This phase is additive read-only exposure of existing server-side state; it introduces no new authorisation decision anywhere.

## Evidence pack

See [docs/evaluation/stage-11/owner-validation/phase-6a1/](../evaluation/stage-11/owner-validation/phase-6a1/).

## Exit decision

`PASS — FRONTEND GOOGLE FLOW VISIBILITY ALIGNED`. See [phase-6a1-decision.md](../evaluation/stage-11/owner-validation/phase-6a1/phase-6a1-decision.md).
