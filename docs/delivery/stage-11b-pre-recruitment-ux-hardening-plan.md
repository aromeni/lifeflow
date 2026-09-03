# Stage 11B — Pre-Recruitment UX Hardening

**Status:** In progress · **Date:** 2026-09-03

Companion: [Engineering Acceptance Contract](engineering-acceptance-contract.md) · [owner-validation-exit-template.md](../evaluation/stage-11/owner-validation-exit-template.md) (conditions 5–7) · [docs/product/design-system.md](../product/design-system.md)

## Objective

Close the three open, non-safety P2 conditions from Stage 11A's `CONDITIONAL READINESS` exit decision, per the project owner's explicit authorisation ("AUTHORISE STAGE 11B — PRE-RECRUITMENT UX HARDENING"). Bounded product UX/copy remediation, outside Stage 11A, before recruitment authorisation is ever requested.

## Authorised scope

- Condition 5: deletion-choice clarity.
- Condition 6: outage/degraded-state guidance.
- Condition 7: uncertain-outcome guidance.
- Smallest product changes necessary to make each condition clear and actionable.
- Focused automated coverage per condition; run frontend/backend/E2E tests.
- A short owner walkthrough per condition using the real UI, with the owner's actual impression recorded.
- If all three re-verifications pass: close conditions 5–7, reassess the Stage 11 exit verdict.
- Dedicated branch and PR. **No merge or tag without a separate integrity review.**

## Prohibited scope

Do not reconnect Google. Do not perform provider reads or writes. Do not run another soak. Do not recruit participants. Do not begin Stage 12.

## Immutable invariant this phase must not touch

"No automatic retry after an uncertain external outcome" (Engineering Acceptance Contract §3). See condition 7's acceptance criterion below for how this phase satisfies the "how reconciliation or retry becomes authorised" requirement without adding a new retry/reconciliation mechanism — a materially new product capability against a safety invariant is exactly the kind of "product-policy choice [with] multiple materially different, valid outcomes and no approved decision" the contract (§8.11) flags as a stop condition, not something to decide unilaterally inside a copy-remediation phase. This phase satisfies the requirement by **explaining honestly that no in-product mechanism exists today**, and what the safe manual path is instead. Flagged explicitly to the owner in the completion report as a scope decision, not silently made.

## Acceptance matrix

| ID | Requirement | Category | Implementation location | Verification | Status |
|---|---|---|---|---|---|
| P11B-R001 | A single comparison summary distinguishes what each of the 4 deletion controls removes, keeps, and whether it's reversible | UX | `apps/web/src/app/connections/page.tsx` | Unit test + owner walkthrough | Implemented |
| P11B-R002 | Disconnect requires an explicit two-step confirm with consequence/reversibility copy before the API call fires | UX | `connections/page.tsx`, new `ConfirmButton` | Unit test | Implemented |
| P11B-R003 | Per-item memory delete requires an explicit two-step confirm with consequence copy before the API call fires | UX | `apps/web/src/app/settings/page.tsx` | Unit test | Implemented |
| P11B-R004 | Delete-all memory requires an explicit two-step confirm with consequence copy before the API call fires | UX | `settings/page.tsx` | Unit test | Implemented |
| P11B-R005 | New `ConfirmButton` primitive is accessible (focus moves to Confirm on arm, cancel returns to initial state, explanation is in a live region) | UX, accessibility | `apps/web/src/components/ui/ConfirmButton.tsx` | Unit test | Implemented |
| P11B-R006 | Existing disconnect/imported-data/account-deletion/memory-delete E2E and unit tests updated for the new two-step flow, none weakened | Test | `connections/page.test.tsx`, `settings/page.test.tsx`, `e2e/deletion.spec.ts` | Full suite run | Implemented |
| P11B-R007 | Owner walkthrough of condition 5 conducted; actual impression recorded, not fabricated | UX, documentation | `docs/evaluation/stage-11/owner-validation/phase-11b/` | Manual, owner's own words | Pending walkthrough |
| P11B-R008 | Google sync degraded/error notices explicitly state: what's unavailable, what remains safe/unaffected, whether action is needed, retry guidance | UX | `connections/page.tsx` | Unit test | Implemented |
| P11B-R009 | Gmail/Calendar partial-read notices explicitly state the same four elements, without claiming an automatic retry that does not exist (verified: D38 — the cursor advances past an incomplete item; it is not retried by a later sync) | UX | `connections/page.tsx` | Unit test | Implemented |
| P11B-R010 | Today brief `partial`/`degraded` status notices explicitly state the same four elements | UX | `apps/web/src/app/today/page.tsx` | Unit test | Implemented |
| P11B-R011 | No claim in any revised copy is factually inaccurate relative to actual backend retry/cursor behaviour | Correctness | backend inspection (`google_sync.py`, `connected_accounts.py`) | Inspection, cited in this table | Verified |
| P11B-R012 | Existing outage/degraded unit and E2E tests (`stage10-outage-notice-fixture.spec.ts` etc.) updated for new copy, none weakened | Test | frontend unit tests, `e2e-resilience/` | Full suite run | Implemented |
| P11B-R013 | Owner walkthrough of condition 6 conducted; actual impression recorded | UX, documentation | `docs/evaluation/stage-11/owner-validation/phase-11b/` | Manual | Pending walkthrough |
| P11B-R014 | Uncertain-execution notice explicitly explains: the outcome is unknown; why LifeFlow won't auto-retry; what to verify (action-type-specific: Gmail Drafts vs. Google Calendar); what's safe next; how reconciliation/retry becomes authorised (honestly: no in-product mechanism today) | UX | `apps/web/src/components/ActionProposalPanel.tsx` | Unit test | Implemented |
| P11B-R015 | Copy is specific to `action_type` (`create_gmail_draft` vs `create_calendar_event`) — verified those are the only two action types that can reach `uncertain` (`create_task` cannot; inspected `action_executors.py`) | Correctness | `ActionProposalPanel.tsx` | Inspection + unit test | Verified |
| P11B-R016 | No new backend endpoint, no new `ActionExecution`/`ActionProposal` state, no change to `no automatic retry` invariant | Boundary | n/a (explicit exclusion) | Diff inspection | Verified — nothing added |
| P11B-R017 | Existing uncertain-execution unit/E2E tests updated for new copy, none weakened | Test | `ActionProposalPanel.test.tsx`, `stage10-uncertain-execution-fixture.spec.ts`, `journey-b-uncertain-write.spec.ts` | Full suite run | Implemented |
| P11B-R018 | Owner walkthrough of condition 7 conducted; actual impression recorded — specifically whether the owner would now act differently on an `uncertain`/low-confidence item | UX, documentation | `docs/evaluation/stage-11/owner-validation/phase-11b/` | Manual | Pending walkthrough |
| P11B-R019 | Frontend unit tests, lint, typecheck, build all green | Quality | n/a | `pnpm web:test && pnpm web:lint && pnpm web:typecheck && pnpm web:build` | Verified — 109/109 tests, lint/typecheck/build clean |
| P11B-R020 | Backend unmodified — no `apps/api` production code changed (this phase is frontend-copy-only; no backend route, schema, or model touched) | Boundary | n/a | `git diff --stat` scoped to `apps/api/src` | Verified — no backend src changes |
| P11B-R021 | `GOOGLE_OIDC_SIGNIN_ENABLED`, `GOOGLE_CONNECTOR_OAUTH_ENABLED`, `GOOGLE_PROVIDER_WRITES_ENABLED` all stay `false` throughout (no provider reads/writes; demo mode only) | Safety | `.env` | Inspection at every checkpoint | Verified |
| P11B-R022 | Relevant E2E suites pass against the updated UI | Test | Playwright | Full run | Verified — `e2e-resilience` full suite (6/6), `e2e/deletion.spec.ts` (2/2), `e2e-design` (24/26, 2 pre-existing unrelated failures confirmed via `main` comparison, 1 baseline legitimately updated) |
| P11B-R023 | If all three owner re-verifications pass, `owner-validation-exit-template.md` conditions 5–7 marked closed and Stage 11 exit verdict reassessed against existing criteria | Documentation | `owner-validation-exit-template.md` | Manual, after walkthroughs | Pending |
| P11B-R024 | Dedicated branch (`stage-11b-pre-recruitment-ux-hardening`) and PR opened; not merged or tagged | Git boundary | n/a | `git log`, `gh pr view` | Pending |

## Acceptance criteria, stated before editing (per condition)

**Condition 5 — deletion-choice clarity.** Met when: (a) a single on-page summary lets a reader state, for each of the 4 controls, what it removes, what it keeps, and whether it's reversible, without reading the individual control copy; (b) disconnect and both memory-delete actions require an explicit confirm step naming the consequence before firing, matching the existing imported-data/account-deletion pattern's spirit (though not necessarily its exact typed-phrase mechanism, which is reserved for the two highest-risk, already-irreversible operations); (c) the owner, walking through the real UI, can state the distinction and consequence of each option without hesitation.

**Condition 6 — outage/degraded-state guidance.** Met when: every existing surface where a degraded/outage state is shown to the user (Google sync degraded/error, Gmail/Calendar partial-read, Today brief partial/degraded) states, in its own copy: what's unavailable, what remains safe/unaffected, whether the user needs to do anything, and when/whether retrying helps — without any claim not verifiably true of the actual backend behaviour; the owner, walking through a reproduced outage state, confirms the message is clear.

**Condition 7 — uncertain-outcome guidance.** Met when: the uncertain-execution notice explicitly states all five required elements (outcome unknown; why no auto-retry; what to verify, specific to the action type; what's safe to do next; how reconciliation/retry becomes authorised — honestly stated as "no in-product mechanism today, verify directly first"), without adding any new state-mutating capability against the no-automatic-retry invariant; the owner, walking through a reproduced uncertain-execution state, confirms they would now know what to do with it (directly addressing the walkthrough finding that they'd previously disregarded `uncertain`/low-confidence items).

## What happened

**Implementation (2026-09-03).** All copy/UX changes implemented, frontend-only:

- New `ConfirmButton` primitive (`apps/web/src/components/ui/ConfirmButton.tsx`): a two-step arm/confirm/cancel control, reused at all three previously-unconfirmed destructive call sites.
- Disconnect (`connections/page.tsx`), per-item memory delete and delete-all memory (`settings/page.tsx`) now require an explicit confirm step naming the consequence and reversibility before firing.
- A new "deletion options" comparison table on the Connections page states removes/keeps/reversible for all four controls in one place.
- Google sync degraded/error notices, Gmail/Calendar partial-read notices, and Today's brief `partial`/`degraded` status notices all revised to explicitly state: what's unavailable, what remains safe/unaffected, whether action is needed, and retry guidance — verified against actual backend behaviour first (`google_sync.py` confirms an "incomplete" item's cursor advances past it; it is genuinely not retried by a later sync, so the copy never claims otherwise).
- The uncertain-execution notice (`ActionProposalPanel.tsx`) now explains all five required elements, with verify-guidance specific to the action type (Gmail Drafts vs. Google Calendar — confirmed via `action_executors.py` inspection that `create_task` can never reach `uncertain`). No new backend endpoint or state was added — deliberately, per this plan's "immutable invariant" section; the "how reconciliation becomes authorised" element is answered honestly (no in-product mechanism today).

**Verification.** A real regression was found and fixed during verification, not glossed over: the new deletion-options table's `min-w-lg` forced 512px minimum width, causing genuine horizontal page overflow at the 390px breakpoint (`stage10-outage-notice-fixture.spec.ts`'s responsive check caught it) — fixed with `table-fixed` + `wrap-break-word` cells instead of a fixed minimum width.

- Frontend unit tests: 109 passed (10 files), including 9 new/revised tests across `connections/page.test.tsx`, `settings/page.test.tsx`, `ActionProposalPanel.test.tsx`.
- `pnpm web:lint`, `pnpm web:typecheck`, `pnpm web:build`: all clean.
- `e2e-resilience` full suite (6 journeys, including Journey D's real Postgres/Redis stop/start): all pass.
- `e2e/deletion.spec.ts` (Journeys A & B, real UI + worker): both pass.
- `e2e-design` (visual-regression, accessibility, responsive): 24/26 pass. Two failures (`Today with a generated brief`, `Approvals: a single proposal card`) were investigated, not assumed benign — independently reproduced against unmodified `main` (via `git stash`) and confirmed **pre-existing**, caused by the demo dataset's date-relative content drifting against static baseline images (the same phenomenon documented extensively during Stage 11A Phase 10), unrelated to this phase's changes. Left untouched. The one genuinely-affected baseline (`connections.png`, taller page from the new table) was regenerated and its diff visually inspected before accepting.
- Backend: zero files under `apps/api/src` touched (confirmed via `git diff --stat`).

**Owner walkthroughs.** _Pending — see below._

## Evidence pack

See `docs/evaluation/stage-11/owner-validation/phase-11b/`.
