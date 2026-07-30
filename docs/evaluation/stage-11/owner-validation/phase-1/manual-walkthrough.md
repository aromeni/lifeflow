# Stage 11A Phase 1 — Manual Owner Walkthrough

**Status:** Complete · **Date:** 2026-07-31

Companion: [owner-observation-template.md](../../owner-observation-template.md) · `apps/web/e2e-owner-validation/phase1-walkthrough.spec.ts`

## Method

The application was driven end to end via a dedicated Playwright script (`apps/web/e2e-owner-validation/phase1-walkthrough.spec.ts`) against the real running app (real API, real Postgres, real Next.js dev server) — the same execution mechanism the existing automated E2E suites use, not a separate manual click-through, since that is the available and verifiable way to drive the real application interface in this environment. Fifteen full-page screenshots were captured at each key state and **individually viewed** (not merely asserted against) to produce the observations below — screenshots themselves are not committed to this repository (they live in `apps/web/test-results/`, already gitignored); only this written summary is.

## Journeys covered

Landing, onboarding (both steps), Today (empty and with a generated brief), evidence inspection, Approvals inbox, Gmail draft proposal, Calendar proposal, task-proposal approve→execute, calendar-proposal reject, Audit History, Connections (disconnect/imported-data/account-deletion sections), account-deletion preview (not completed live — see below), Settings/learned-preferences.

## Observations

### Observation — Landing page states the safety model up front

OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE

- Date and build SHA: 2026-07-31, branch `stage-11a-phase-1-synthetic-validation`.
- Scenario: S11A-P1-001.
- Expected result: safety model visible without needing to dig.
- Observed result: the landing page states, above the fold, "nothing is ever sent or changed without your explicit approval," and a "How your data is handled" panel explicitly lists "Never sends email — full stop" and "Never modifies or deletes an existing calendar event" as bare, unhedged claims.
- Owner impression: this is a stronger, more literal safety statement than most product landing pages make — appropriate given the actual code guarantees back it (see `safety-invariant-results.md`).
- Severity: N/A (positive observation).
- Repeatability: always (static content).
- Corrective action: none.
- Regression-test reference: `e2e-design/visual-regression.spec.ts` (landing), `accessibility.spec.ts` (landing).
- Resolution status: N/A.

### Observation — Today brief surfaces evidence and confidence on every card

OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE

- Date and build SHA: 2026-07-31.
- Scenario: S11A-P1-004.
- Expected result: every actionable item traceable to a source, with a visible confidence and suggested step.
- Observed result: all 20 items across the four sections showed a detected-cue label, a confidence percentage, an evidence-source count, and "Suggested next step: ... (nothing happens without your approval)" — with zero exceptions across the full generated brief.
- Owner impression: dense but genuinely scannable; the repeated "nothing happens without your approval" phrase on every card is slightly repetitive but reinforces the safety model consistently rather than only once at the top.
- Severity: N/A.
- Repeatability: always (deterministic composition, confirmed by `run-evals.sh brief`'s "Deterministic under repeat composition: True").
- Corrective action: none required; noted as a possible future copy-density review, not a defect.
- Regression-test reference: `run-evals.sh brief`, `run-evals.sh brief+mock`.
- Resolution status: N/A.

### Observation — Gmail/Calendar proposal cards show exact canonical payload and hash

OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE

- Date and build SHA: 2026-07-31.
- Scenario: S11A-P1-007, S11A-P1-008.
- Expected result: exact payload preview, no ambiguity about what approval means.
- Observed result: the Gmail draft card showed the literal To/Subject/Body text plus an expandable "Exact canonical JSON and hash" section; the calendar card additionally showed an explicit "Guest notifications: off — ... only your own calendar is affected" callout.
- Owner impression: this is exactly the level of transparency the landing page promises — a reviewer does not have to trust a summary, the exact bytes are inspectable.
- Severity: N/A.
- Repeatability: always.
- Corrective action: none.
- Regression-test reference: `test_action_proposals.py::test_approval_binds_exact_displayed_type_payload_and_version`.
- Resolution status: N/A.

### Observation — Connections page: "Not connected" alongside non-zero "Connected accounts: 1"

OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE

- Date and build SHA: 2026-07-31.
- Scenario: S11A-P1-013 (Connections screen), see also finding F-001 in [defect-register.md](defect-register.md).
- Expected result: the privacy summary panel's numbers should read as consistent with the connection-status banner above it.
- Observed result: the "Connected accounts" card reads "Not connected" (correct — no *Google* account exists), but the "Data stored by LifeFlow" panel directly below it shows "Connected accounts: 1" and "Imported emails & events: 36" — both true (the demo/synthetic account and its imported dataset), but juxtaposed with "Not connected" in a way that could read as contradictory to someone unfamiliar with the synthetic-vs-real-provider distinction.
- Owner impression: technically accurate, not unsafe, but a moment of "wait, which is it?" on first read. This is exactly the kind of finding Stage 11A exists to catch before a participant does.
- Severity: **P3** — cosmetic/wording clarity, not a safety or correctness issue; recorded as F-001.
- Repeatability: always, in any demo-only (no real Google account) session.
- Corrective action: none applied in this phase (out of scope for Phase 1 per its plan — product-copy changes are not authorised here); recorded for a future design pass.
- Regression-test reference: none added (informational finding, not a regression risk).
- Resolution status: open, accepted-as-is for Phase 1 (P3, does not block exit).

### Observation — Account-deletion preview: exact counts, clear danger treatment

OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE

- Date and build SHA: 2026-07-31.
- Scenario: S11A-P1-019.
- Expected result: exact will-delete/will-keep counts, phrase-gated confirmation, clearly marked as irreversible.
- Observed result: red/pink-bordered panel; itemised "Will be deleted" (2 proposals, 1 brief version, 1 connected account, 20 signals, 36 imported items) and "Will be kept (content-free)" (1 execution history entry, 16 audit records, 1 execution record); exact-phrase input (`DELETE MY LIFEFLOW ACCOUNT`) gating a disabled "Delete permanently" button.
- Owner impression: no ambiguity about consequence or reversibility. Deliberately **not completed live** in this walkthrough — ending the session mid-walk would have truncated the remaining journeys, and the automated reset-repeatability harness already proves full completion (10/10 cycles) without that risk.
- Severity: N/A.
- Repeatability: always.
- Corrective action: none.
- Regression-test reference: `test_privacy_deletion_api.py::test_confirm_wrong_phrase_422`; `test_stage11a_phase1_reset_repeatability.py` (completes the equivalent flow 10 times).
- Resolution status: N/A.

### Observation — Audit History: complete, plain-language, chronologically correct

OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE

- Date and build SHA: 2026-07-31.
- Scenario: S11A-P1-015.
- Expected result: every lifecycle event from this session, newest first, plain language, no raw metadata.
- Observed result: 16 entries, newest first, covering account creation → sign-in → demo-data preparation → connection sync → evidence review → three proposals → brief generation → approval → four distinct execution-lifecycle entries → rejection — each with a plain description, a category tag, and a status badge; no token, ID, or raw payload visible in any entry.
- Owner impression: this is a genuinely complete and readable record — the "execution started / execution attempt recorded / execution confirmed / action completed" four-step breakdown for one executed proposal is more granular than expected and adds real confidence that the durability model (Stage 7 ADR 0003 D16) is observable, not just internally correct.
- Severity: N/A.
- Repeatability: this exact screenshot required a script fix first (see below) — the underlying page behaviour was always correct.
- Corrective action: fixed the walkthrough script (not the product) to wait for real content before screenshotting; re-ran and confirmed.
- Regression-test reference: `test_audit_history.py`, `e2e/audit-history.spec.ts`.
- Resolution status: resolved (script-only correction).

### Observation — Settings: honest empty state for learned preferences

OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE

- Date and build SHA: 2026-07-31.
- Scenario: S11A-P1-021.
- Expected result: an empty, opt-in memory section should read as "nothing has happened," not as broken.
- Observed result: "Nothing learned yet. Turn on learning above to let LifeFlow suggest preferences from your actions," with the learning toggle off by default, plus five explicit bullet guarantees (deleting memory doesn't touch Gmail/Calendar, explicit settings always win, etc.).
- Owner impression: correctly matches Stage 8 Phase 3's explicit-opt-in design; no ambiguity about why the section is empty.
- Severity: N/A.
- Repeatability: always, in a fresh session with learning not yet enabled.
- Corrective action: none.
- Regression-test reference: `apps/web/src/app/settings/page.test.tsx`.
- Resolution status: N/A.

## What this walkthrough does not claim

This is one facilitator's (the executing agent's, standing in for the owner in this automated-but-owner-directed context) pass through the product. It is not participant research, not a usability study, and none of the impressions above are statistically representative of how any other person would react — see [evaluation-context-decision.md](../../evaluation-context-decision.md) for why that distinction matters and is enforced here.
