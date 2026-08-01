# Owner-Operated Readiness Walkthrough

**Status:** Performed against the real local app with synthetic demo data · **Date:** 2026-08-01

Companion: [evidence-handling-plan.md](evidence-handling-plan.md) · [real-provider-data-boundary.md](real-provider-data-boundary.md)

**Note on who performed this walkthrough**: this task is being executed autonomously per its governing instruction; the walkthrough below was performed by driving the real local app (API + web dev servers, real Postgres/Redis, the "Try demo" synthetic dataset) with Playwright, and reviewing the resulting screens directly — the same interface and data the project owner would see. It is recorded as **OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE** per the governing instruction's template, since no participant was involved. Screenshots were taken to a local scratch directory for review and are not committed to this repository (only synthetic, fictional content ever appeared in them, but the evidence pack in this directory contains markdown findings only, matching the rest of this evidence pack's convention).

## Method

`docker compose up -d db redis`, `alembic upgrade head`, the API (`uvicorn`) and web (`next dev`) dev servers started locally, then driven via a Playwright script: dev-login → `/demo/start` (synthetic Gmail/Calendar dataset) → each required screen.

## Screens reviewed

### Landing (`/`)

**OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE.** The landing page explicitly separates three distinct actions in its own copy: "Sign in with Google only confirms who you are — it never reads your mail or calendar," "Connecting Gmail and Calendar is a separate, later step from the Connections screen, with its own consent screen and its own scopes. Disconnect any time," and "Try demo uses entirely fictional data and needs no Google account at all." This directly answers the required question — the distinction between simulation and a real future provider connection is already stated in the product's own copy, not something this phase needs to add.

### Onboarding (`/onboarding`)

**OWNER OBSERVATION.** States "LifeFlow only prepares actions — nothing is ever sent or changed without your explicit approval" before asking only for a timezone. Clear, matches the product's approval-first design.

### Today (`/today`)

**OWNER OBSERVATION.** The generated brief clearly sections items (Needs attention / Today and upcoming / Waiting for / Suggested actions / Low-confidence review), each with a confidence score, detected cue, and an "Evidence" disclosure link. A banner notes "5 synced calendar events with fewer than two attendees are not listed under Today and upcoming. They synced correctly and your calendar is unchanged" — a good example of explaining an absence rather than leaving it ambiguous.

### Approvals (`/approvals`)

**OWNER OBSERVATION.** Header states "3 proposals · simulated execution only." Each proposal card carries an explicit banner: "Simulation — no external system will change / This action will be simulated. No external service will be changed." The Calendar-event proposal additionally states "Guest notifications: off — Creating this event never emails attendees an invitation and never updates their calendars — only your own calendar is affected," which matches the code-level proof in [oauth-scope-matrix.md](oauth-scope-matrix.md) (`sendUpdates=none`, insert-only). This is exactly the clarity the readiness checklist requires: draft-only Gmail behaviour and insert-only Calendar behaviour are both stated plainly, not merely implied.

### Connections (`/connections`)

**OWNER OBSERVATION.** "Connected accounts: Not connected. [Connect Google]" — confirmed directly: even with the synthetic demo dataset fully loaded (1 connected account of provider `synthetic`, 36 imported items), this screen does **not** claim a Google connection exists. This is an important, positive finding for Phase 4B: the UI never conflates demo/synthetic state with a real Google connection, so a future real connection's presence or absence will be unambiguous to the owner. "Everything here is read-only — LifeFlow never sends email, never changes your calendar, and never deletes anything on this page" is stated directly under the page heading. The data-controls section clearly separates "Disconnect a provider" (revokes access, imported data stays until separately deleted) from "Delete the LifeFlow account" (explicitly: "it never deletes your Gmail or Google account, and it cannot be undone") — disconnect is clearly distinguished from deletion, as required.

### Settings (`/settings`)

**OWNER OBSERVATION.** "Everything here is explicit: LifeFlow only adapts in ways you set yourself... none of these settings can approve or execute anything on your behalf." The synced-account status line ("synthetic: last synced...") labels the provider type explicitly, reinforcing the simulation/real distinction.

### Audit History (`/audit-history`)

**OWNER OBSERVATION.** "Private content, provider identifiers, technical metadata, and error details are never shown here" is stated directly under the heading, and the visible entries (Brief generated, Action proposed ×3, Evidence reviewed, Profile settings updated, Connection sync completed, Demo data prepared, Signed in, Account created) are all plain-language, content-free — consistent with the Phase 3 log-privacy sentinel findings.

## Screens/flows not separately screenshotted this phase

Disconnect confirmation, imported-data deletion preview/confirm, inferred-preference deletion, full-account-deletion preview/confirm, the outage-warning banner, and the uncertain-execution warning are all reachable from the Connections screen's visible entry points ("Preview what will be deleted," "Manage learned preferences") but were not individually driven and screenshotted in this pass — they are already covered by dedicated, passing E2E suites (`apps/web/e2e/deletion.spec.ts`, `apps/web/e2e/connections.spec.ts`, and the outage-resilience suite's own warning-banner journeys), which this phase's automated-verification run re-executes in full (see the final Phase 4B report's automated-suite section). Re-screenshotting them here would duplicate, not add to, that existing evidence.

## Answers to the required questions

- **Is the future real-provider state understandable?** Yes — the Connections screen already distinguishes "Not connected" from a real connection state, and the landing page explains the three-way distinction (sign-in / connect / demo) up front.
- **Is the account identity visible?** Not yet directly observable (no real account exists), but the existing "Connected accounts" pattern (provider name + status) is the same UI surface a future real connection would populate — no separate UI work is implied by this phase.
- **Is the difference between simulation and real provider clear?** Yes — stated explicitly on the Approvals screen banner and the landing page copy.
- **Is draft-only behaviour clear?** Yes — stated explicitly on both the landing page and the Gmail-draft approval card.
- **Is Calendar insert-only behaviour clear?** Yes — stated explicitly on the Calendar-event approval card ("Guest notifications: off," own-calendar-only).
- **Is consent revocation distinguishable from temporary outage?** Not directly observed this phase (no outage or revocation scenario was triggered against a live connection); the existing outage-resilience E2E suite covers the outage side, and [test-account-cleanup-plan.md](test-account-cleanup-plan.md) covers the revocation side — both rely on existing, separately-tested UI states rather than a new one this phase introduces.
- **Is disconnect distinguishable from deletion?** Yes — stated explicitly and separately on the Connections screen.
- **Is uncertainty explained safely?** Consistent with the existing Phase 2 uncertain-write UI findings (not re-verified with a fresh screenshot this phase, since no code in that path changed).
