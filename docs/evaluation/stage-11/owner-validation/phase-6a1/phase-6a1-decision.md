# Stage 11A Phase 6A.1 — Decision

**Date:** 2026-08-05

## Summary

Phase 6A separated backend Google OIDC sign-in and connector-consent authorisation into two independent, fail-closed flags but left the frontend reading only the old, single, configuration-completeness signal. This phase closed that gap: `GET /config` now exposes three independent, content-free booleans (`google_provider_configured`, `google_oidc_signin_enabled`, `google_connector_oauth_enabled`), the landing page's sign-in control follows only the sign-in capability, and the Connections page's connector control follows only the connector capability — showing safe explanatory text instead of a control that would predictably fail after clicking. No backend guard, route, or authorisation decision was touched.

This phase's own verification demonstrated the discrepancy was real, not hypothetical: the local development environment's leftover real Google client configuration from an earlier phase caused the pre-fix landing page to render a live "Sign in with Google" button that would 409 immediately on click — captured, uncorrected, in the repository's own pre-existing visual-regression baseline.

## Requirements met

- Three independent, content-free capability booleans exposed, no secret values — **met**.
- Master `google_provider_configured` never by itself implies either flow authorised — **met**, verified directly.
- Sign-in UI follows only the sign-in capability; connector UI follows only the connector capability — **met**, proven in both directions with the exact Phase 6 incident configuration reproduced on both pages.
- Frontend capability-load failures fail closed — **met**.
- Backend remains authoritative; no guard weakened or removed — **met**, no backend authorisation file touched.
- All required tests and CI checks green — **met** locally (1049 backend, 99 frontend, full lint/typecheck/build/E2E-functional/E2E-accessibility/E2E-responsive/E2E-visual); PR CI tracked separately (see final report).
- Zero provider activity — **met**, verified directly.

## Decision

**PASS — FRONTEND GOOGLE FLOW VISIBILITY ALIGNED.**

This does not authorise reconnecting either account, a Calendar-write trigger attempt, the soak period, recruitment, or Stage 12 — each remains a separate, explicit owner decision.

**Next owner decision (after this PR merges):**

`AUTHORISE A CORRECTED CALENDAR-WRITE TRIGGER ATTEMPT`
