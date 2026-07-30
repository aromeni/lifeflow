# Stage 11A Phase 1 — Defect Register

**Status:** Complete — 0 P0/P1, 1 P3 informational finding · **Date:** 2026-07-31

Companion: [../../issue-register-template.md](../../issue-register-template.md) (shared P0–P3 definitions) · [manual-walkthrough.md](manual-walkthrough.md) · [acceptance-matrix.md](acceptance-matrix.md)

## Register

| ID | Severity | Scenario | Description | Root cause | Fix status | Regression coverage | Re-evaluated? |
|---|---|---|---|---|---|---|---|
| F-001 | P3 | S11A-P1-013/018 (Connections) | "Connected accounts" summary card reads "Not connected" while the "Data stored by LifeFlow" panel directly below shows "Connected accounts: 1" / "Imported emails & events: 36" for the same demo-only session — both numbers are correct, but the juxtaposition could read as contradictory to someone unfamiliar with the synthetic-vs-real-provider distinction | The Google-specific card only renders for `provider === "google"` accounts (`connections/page.tsx:90`); the stats panel counts all connected accounts regardless of provider, including the demo/synthetic one | Accepted-as-is for Phase 1 — cosmetic wording only, no safety/correctness impact, out of scope for a synthetic-validation phase to redesign product copy | None added (informational, not a regression risk) | N/A |

## Non-defects explicitly considered and ruled out

- **Audit History screenshot timing** — the first walkthrough run screenshotted the page mid-load. This was a defect in the **new test script**, not the product (the existing `e2e/audit-history.spec.ts` already waits correctly and was never affected). Fixed in the script; not logged as a product defect. See [execution-log.md](execution-log.md).
- **Imported-data deletion "unavailable" for demo sessions** — initially looked like a possible gap (S11A-P1-018) until the UI's own copy ("Connect and sync an account to enable imported-data deletion") and the component logic (`DeletionControls.tsx:337-357`, gated on `googleAccountId`) confirmed this is intentional, accurate scoping: a synthetic demo account has no real external provider relationship to separately disconnect-then-clean-up, and full account deletion already covers its data. Not a defect.
- **`.local` email domain rejected by `EmailStr`** — surfaced while building the reset-repeatability harness (`dev-login` returned 422 for an explicitly-supplied `...@lifeflow.local` address). This is `email-validator` correctly rejecting a reserved-use TLD when validation actually runs; the pre-existing `dev@lifeflow.local` default only works because Pydantic v2 doesn't validate field defaults. Not a product defect — worked around by using `.example` for all new synthetic identities (see [synthetic-data-inventory.md](synthetic-data-inventory.md)).

## No unresolved P0 or P1

Zero P0 findings. Zero P1 findings. Phase 1 exit is not blocked by anything in this register.
