# Stage 11A Phase 3 — Manual Owner Walkthrough (S11A-P3-025/044)

**Status:** Complete · **Date:** 2026-07-31

Companion: [browser-privacy-results.md](browser-privacy-results.md) · [defect-register.md](defect-register.md)

New Playwright walkthrough (`apps/web/e2e-owner-validation/phase3-privacy-walkthrough.spec.ts`, run via `scripts/stage11a-phase3-owner-walkthrough.sh` against the real local demo stack, synthetic data only) drove: landing → sign-in → onboarding → Today (brief generated) → Approvals → Audit History → Connections → Settings → logout → post-logout revisit. At every stage, `localStorage`, `sessionStorage`, `document.cookie`, and `indexedDB.databases()` were inspected directly via `page.evaluate`, and one real network response (`GET /privacy/summary`) was inspected for token-field absence. 4 screenshots were captured, individually viewed below, and never committed (`test-results/` is gitignored).

All entries below are **OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE**.

- **Today, post-brief-generation** — `localStorage`/`sessionStorage`/`document.cookie`/IndexedDB were all empty (aside from the Next.js dev-server's own internal `__next_debug_channel` sessionStorage key, addressed below). The brief rendered "Needs attention," "Today and upcoming," "Waiting for," "Suggested actions," and "Low-confidence review" counts exactly as the deterministic demo fixture predicts, with a plain-language note explaining why 5 low-attendee calendar events aren't surfaced under Today. Nothing about this screen suggested any client-side data retention beyond the current page's in-memory React state.
- **Approvals inbox** — the screenshot happened to land mid-load ("Loading action proposals…"); storage was confirmed empty regardless of load state. No functional concern — this is a cosmetic timing artefact of exactly when the screenshot fired relative to the fetch, not a privacy or correctness issue (recorded as a non-defect, matching the same class of screenshot-timing race Phase 1/2 already documented for their own walkthroughs).
- **Connections ("Privacy & Connections")** — the page's copy is exactly as direct as the product principles require: "Everything here is read-only — LifeFlow never sends email, never changes your calendar, and never deletes anything on this page." The demo account correctly shows "Not connected" / "No access granted" (demo mode seeds a `synthetic` provider, not `google`), so the Google-specific imported-data-deletion control is correctly unavailable — the same accurate state Phase 1's walkthrough already established. The real `GET /privacy/summary` network response was inspected directly and confirmed to contain neither `encrypted_access_token`, `encrypted_refresh_token`, nor `authorisation_revision`.
- **Post-logout revisit** — navigating back to `/today` after a real logout call correctly rendered "You are not signed in. Start the demo first." — no stale brief content, no flash of previously-loaded data, no client-side cache serving anything from the ended session.

## What this walkthrough found (and how it was resolved)

A genuine, if minor, discovery: `sessionStorage` contained one key, `__next_debug_channel:<random-id>`, at the very first storage check (the landing page, before any sign-in). Investigation (repository-wide grep across `apps/web/src`) confirmed this is **Next.js's own development-server internal tooling** (the dev-mode HMR/error-overlay channel), never written by any LifeFlow application code, and structurally absent from a production build (`next build && next start` never runs the dev overlay). The walkthrough's assertion was adjusted to allowlist this exact, well-understood framework-internal key by name while still failing on any other, unexpected key — recorded in [defect-register.md](defect-register.md) as a non-defect, not silently ignored.

## What this walkthrough does not claim

This is owner-operated, synthetic-data-only testing by the person who built the product — it is evidence about the product, not participant research, and is never combined with or presented alongside future participant statistics.
