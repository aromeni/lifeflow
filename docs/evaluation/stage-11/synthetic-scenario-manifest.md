# Stage 11 — Synthetic Evaluation Scenario Manifest

**Status:** Planning document, grounded in the existing demo dataset and fixtures · **Date:** 2026-07-30

Companion: [task-protocol.md](task-protocol.md) · [product-hypotheses.md](product-hypotheses.md) · [round-1-runbook.md](round-1-runbook.md)

Every scenario below reuses fixtures that already exist in this repository — none was invented for this document. Source: `apps/api/src/lifeflow_api/demo/data/v1/manifest.json`, `emails.json`, `events.json`; `apps/web/e2e-resilience/stage10-outage-notice-fixture.spec.ts`; `apps/web/e2e-resilience/stage10-uncertain-execution-fixture.spec.ts`; `apps/web/src/app/{today,approvals,connections,audit-history,settings,onboarding}`.

## Fictional-data confirmation

Every email sender/recipient domain in the demo dataset uses the IANA-reserved `.example` TLD, or `lifeflow.local` for the demo user (`demo@lifeflow.local`) — confirmed domains: `northgate-consulting.example`, `bramley-finch.example`, `brightmail-promotions.example`, `calmspace-app.example`, `fenwick-moss.example`, `filmhouse-cinema.example`, `maplecourt-residents.example`, `railbookings.example`, `ridgeline-coaching.example`, `ridgewaychamber.example`, `stmartins-primary.example`, `studiofortnight.example`, `thameside-analytics.example`, `ukdesignweekly.example`, `velvet-mail.example`. No real-world domain (e.g. `gmail.com`, `outlook.com`, `yahoo.com`) appears anywhere in the dataset. This is enforced by the automated validator (see §Validator below).

## Scenario inventory

| Scenario | Fixture identifier(s) | Task supported | Hypothesis tested | Expected correct interpretation | Expected safe action | Prohibited interpretation | Reset procedure |
|---|---|---|---|---|---|---|---|
| Landing page | `apps/web/src/app/page.tsx` | T1 | P-H1, P-H4 | Participant identifies the product as a permissioned assistant for Gmail/Calendar | N/A (no action) | Belief that it autonomously sends/acts without approval | Reload landing page |
| Onboarding flow | `apps/web/src/app/onboarding/page.tsx` | T2, T3 | U-H1, S-H1, S-H2 | Participant completes onboarding and correctly states Gmail=drafts-only, Calendar=new-events-only | Complete onboarding via "Try demo" | Belief that connecting grants send/edit/delete permission | Reset onboarding state via demo reset |
| Today summary | Demo dataset (`emails.json`, `events.json`), `apps/web/src/app/today/page.tsx` | T4–T7 | V-H1, V-H2, U-H2, U-H3, U-H4 | Participant summarises brief correctly and identifies `em-001` (near-deadline, explicit request) or an equivalent high-priority item as top priority | Inspect evidence, no side effect | Belief that the brief itself takes action | Reset demo dataset to v1 seed state |
| Explicit-request signal | `em-001`, `em-006`, `em-008`, `em-010`, `em-017`, `em-023` | T5, T6 | U-H3, V-H2 | Participant explains why an explicit request is ranked highly | N/A | Dismissing an explicit request as noise | Reset demo dataset |
| Near-deadline signal | `em-001`, `ev-004` | T5, T6 | U-H2, U-H3 | Participant identifies urgency correctly | N/A | Missing the deadline signal entirely | Reset demo dataset |
| Overdue follow-up ("Waiting For") | `em-002`, `em-024` | T8 | V-H3 | Participant correctly explains what an overdue Waiting For item means and that no automatic action has been taken | N/A | Belief the system already followed up on their behalf | Reset demo dataset |
| Calendar conflict | `ev-002`, `ev-003` | T5–T7 | U-H3, V-H2 | Participant identifies the conflict as a reason for priority | N/A | Belief the system will resolve the conflict automatically | Reset demo dataset |
| Newsletter / noise deprioritisation | `em-003`, `em-013`, `em-020`, `em-007`, `em-012`, `em-016`, `em-018`, `em-022` | T4, T5 | U-H3 | Participant agrees low-signal items are correctly deprioritised | N/A | Treating noise items as high priority | Reset demo dataset |
| Prompt-injection resistance | `em-004` | Observed incidentally during T4–T7 (not a scored participant task — a backend safety property, not a UX comprehension target) | S-H1–S-H3 (indirectly) | The injected instruction has no visible effect on the UI or produces no unsafe proposal | N/A | N/A (facilitator does not point this out to avoid biasing think-aloud) | Reset demo dataset |
| Ambiguous / low-confidence signal | `em-005` | T6, T7 | U-H4 | Participant correctly reads a lower confidence indicator as lower confidence, not as an error | N/A | Interpreting low confidence as a system malfunction | Reset demo dataset |
| Proposed Gmail draft | `em-001`, `em-015` material via `apps/web/src/app/approvals/page.tsx` | T9, T10 | U-H5, V-H4, S-H1 | Participant states approving creates a draft only, never sends | Review, then approve/edit/reject | Belief that approval sends the email | Reset approvals queue |
| Proposed calendar event | `em-023`, `ev-007` material via `apps/web/src/app/approvals/page.tsx` | T11 | V-H4, S-H2, S-H3 | Participant states approving creates a new event only, never edits/deletes existing ones | Review, then approve/edit/reject | Belief that approval could modify `ev-001`–`ev-012` | Reset approvals queue |
| Reject/edit a proposal | Any pending proposal in the approvals queue | T12 | V-H6 | Participant exercises reject or edit deliberately | Reject or edit | N/A | Reset approvals queue |
| Uncertain execution outcome | `apps/web/e2e-resilience/stage10-uncertain-execution-fixture.spec.ts` (drives the real backend-classified uncertain-execution state via the test-only fake-Google server) | T13 | S-H5 | Participant proposes checking status/audit trail rather than blindly retrying | Check status, do not blind-retry | Blind retry of an uncertain action | Reset resilience fixture state |
| Temporary provider outage | `apps/web/e2e-resilience/stage10-outage-notice-fixture.spec.ts` | T14 | Outage-comprehension criterion | Participant explains their data is not lost, service is temporarily degraded | Wait / retry later, no data-loss panic | Belief that data has been deleted | Reset resilience fixture state |
| Audit History | `apps/web/src/app/audit-history/page.tsx` | T15 | V-H5, S-H8 | Participant confirms Audit History is read-only | N/A (view only) | Attempting or believing they can act from Audit History | N/A — read-only, nothing to reset |
| Account disconnect | `apps/web/src/app/connections/page.tsx` (disconnect control, Stage 9 Privacy Centre) | T16, T17 | U-H6, S-H6 | Participant explains disconnect ≠ imported-data deletion | Locate control (not necessarily complete it) | Belief disconnect erases imported data | Reset connections state |
| Imported-data deletion | `apps/web/src/app/connections/page.tsx` (`DeletionControls.tsx`) | T17 | U-H6, S-H6 | Participant explains this deletes imported emails/events, distinct from disconnect | Locate control (not necessarily complete it) | Confusing this with account deletion | Reset connections state |
| Learned-preference deletion | `apps/web/src/app/settings/page.tsx` (memory/preferences controls, Stage 8 Phase 3) | T18 | U-H6, S-H7 | Participant explains this deletes one inferred preference, not the account | Locate control (not necessarily complete it) | Confusing this with account deletion | Reset settings state |
| Permanent account deletion | `apps/web/src/app/settings/page.tsx` or `connections/page.tsx` (account-deletion confirmation, Stage 9 Delivery Phase 2) | T19 | U-H6, S-H7 | Participant correctly reads the confirmation step as permanent and distinct from the above | Locate and read, do not complete during the session | Accidentally triggering real deletion during a demo session | Reset account state; **facilitator must never let a participant actually complete this action during a session** |

## Validator

Automated, static-only checks (no participant data or live browser session required) live in `apps/api/tests/test_stage11_evaluation_readiness.py`:

- every sender/recipient domain in `emails.json` ends in `.example` or is `lifeflow.local` — no real-world domain is present;
- every scenario ID referenced in this manifest's table (e.g. `em-001`, `ev-004`) actually exists in `manifest.json`'s scenario lists or the raw email/event ID sets;
- the demo dataset's `manifest.json` scenario keys referenced above (`explicit_request`, `near_deadline`, `overdue_follow_up`, `calendar_conflict`, `newsletter_deprioritise`, `prompt_injection`, `ambiguous_low_confidence`, `proposed_gmail_draft_material`, `proposed_calendar_event_material`) are present.

Fixture reachability for the two resilience-suite states (outage notice, uncertain execution) is verified by re-running the existing Playwright specs that already exercise them (`apps/web/e2e-resilience/stage10-outage-notice-fixture.spec.ts`, `stage10-uncertain-execution-fixture.spec.ts`) — this document does not duplicate that suite, it relies on it, and the verification section of the readiness report for this gate records the result of re-running it.

No evaluation-only shortcut was added to production code to make any of this reachable — every fixture above already existed prior to this planning gate (Stage 9 Delivery Phase 5, Stage 10).

## Demo reset

"Reset demo dataset" above refers to the existing, already-documented demo-mode reset behaviour (restarting the demo stack re-seeds from `apps/api/src/lifeflow_api/demo/data/v1/`) — no new reset mechanism was built for this evaluation.
