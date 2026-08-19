# Stage 11A Phase 8 — Decision

**Date:** 2026-08-19

## Summary

Phase 7 closed with two named open items. This phase addressed both:

1. **Revocation** — closed. The owner independently checked Google's own
   connected-apps permissions page, found LifeFlow's access genuinely still
   active (confirming Phase 7's `revocation_confirmed: false` reflected a
   real failure, not an ambiguous network hiccup), and removed it directly
   via Google's own interface. See `revocation-closure.md`. Reclassified
   `GOOGLE REVOCATION CONFIRMED — OWNER VERIFIED OUTSIDE THE PRODUCT`.
2. **GM-12** — explicitly deferred, not closed. A cheap-path attempt
   (immediate reconnect + sync, on the chance enough real time had passed)
   did not work. A fresh trigger (`P8-FOLLOWUP-TEST-01`) was designed,
   grounded directly in the actual `detect_follow_ups` logic, and sent by
   the owner on 2026-08-17 — but its 5-day elapsed-time requirement cannot
   be satisfied today. See `gm12-deferral.md` for the full reasoning on why
   this is deferred rather than force-closed, and the exact re-verification
   condition carried forward.

A further live reconnection was performed for the cheap-path attempt and
independently verified (`authorisation_revision` 4→5, same four scopes,
Account B untouched, zero OIDC bindings), then the account was disconnected
again immediately rather than left idle-connected for a multi-day wait —
confirmed clean (`revocation_confirmed: true` this time), readiness command
19/19 PASS.

No application code changed this phase. `GOOGLE_PROVIDER_WRITES_ENABLED`
stayed `false` throughout every live action.

## Decision

**PASS — BOTH PHASE 7 OPEN ITEMS ADDRESSED (ONE CLOSED, ONE EXPLICITLY
DEFERRED WITH A NAMED RE-VERIFICATION CONDITION).**

This phase's own PASS feeds into, but is distinct from, the overall Stage
11A exit decision — see [owner-validation-exit-template.md](../../owner-validation-exit-template.md)'s
now-filled decision record, and
[stage-11a-owner-validation-plan.md](../../../delivery/stage-11a-owner-validation-plan.md)'s
Phase 8 and Stage 11A Exit status sections.
