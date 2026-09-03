# Stage 11A — Owner Observation Template

**Status:** Complete — four defect-derived entries plus a full §F walkthrough with the project owner's own words (Phase 10, 2026-08-24) · **Date:** 2026-07-30 (log entries added 2026-08-24)

Companion: [stage-11a-owner-validation-plan.md](../../delivery/stage-11a-owner-validation-plan.md) §F · [owner-validation-evidence-register.md](owner-validation-evidence-register.md)

**Every entry made from this template must display the label `OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE` immediately below its heading.** This is not optional formatting — it is the boundary that keeps one person's engineering impressions from being mistaken for, or later presented as, independent participant research findings (see [evaluation-context-decision.md](evaluation-context-decision.md)'s public-communication constraint).

## Entry format

```
### Observation — [short title]

OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE

- Date and build SHA:
- Scenario:
- Expected result:
- Observed result:
- Objective evidence: (screenshot/log reference containing only synthetic data, or automated-test output)
- Owner impression:
- Severity: P0 / P1 / P2 / P3
- Repeatability: always / sometimes (state frequency) / once, not yet reproduced
- Corrective action:
- Regression-test reference: (link to the test added, or "none yet — tracked as [issue]")
- Resolution status: open / fixed / accepted-as-is (with reason)
```

## Rules

- An owner impression (e.g., "the priority label wording felt ambiguous to me") is data about the product from one person familiar with its internals — useful for catching engineering-visible defects, not a substitute for how an unfamiliar user would react. Do not phrase entries as if they represent a general user's reaction.
- Severity uses the same P0–P3 definitions as [issue-register-template.md](issue-register-template.md), so findings here are comparable in kind (not in evidentiary weight) to future participant findings.
- Never copy an owner-observation entry into [findings-template.md](findings-template.md) (the participant findings report) without it being clearly re-labelled and kept in its own section — the two must never be merged into one statistic.
- Objective evidence must never include real account content, even from an approved test account — only synthetic data or automated-test output.

## Log

**Note on the four entries below (added Phase 10, 2026-08-24):** these are
friction points that were already independently documented as defect-
register findings during Phases 6B and 7, reformatted here into this
template's structure because they are exactly the kind of thing §F asks
for. Every field except **Owner impression** is a factual record of what
happened, sourced from the original phase evidence. **Owner impression**
is deliberately left as "not yet provided" in each — Claude cannot
honestly write the project owner's own subjective reaction on their
behalf, and doing so would defeat the entire point of this template (see
the Rules above: an owner impression is data from *the person*, not an
inference about them). The project owner is welcome to fill these in, but
this condition does not require it — the factual friction is the
substantive content §F is after, and it is captured either way.

None of these four cover the purely subjective dimensions §F also lists.
Those are addressed separately, in the owner's own words, in the
"§F walkthrough" entry below — added the same day, after a direct
conversational walkthrough with the project owner.

### Observation — Session invalidated by an API restart

OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE

- Date and build SHA: 2026-08-05, Stage 11A Phase 6B (`stage-11a-phase-6b-calendar-write-trigger` branch)
- Scenario: mid-live-session, the local API process was restarted to apply a configuration-flag change.
- Expected result: the owner's browser session would remain valid across the restart.
- Observed result: the owner was logged out (`✕ Not signed in`) — every API restart with no fixed `SESSION_SECRET` in the local `.env` generates a fresh ephemeral signing key, which is documented, intentional dev-only behaviour, not a bug.
- Objective evidence: `docs/evaluation/stage-11/owner-validation/phase-6b/defect-register.md`, D-6B-02.
- Owner impression: provided 2026-08-24 — no distinct recollection of this specific incident (see the §F walkthrough below for the owner's broader impressions).
- Severity: P3 (environmental, not a product defect).
- Repeatability: always, under this specific condition (API restart with no fixed `SESSION_SECRET`).
- Corrective action: a local-only `SESSION_SECRET` was set for the remainder of the session; no application code changed.
- Regression-test reference: none — this is expected dev-only behaviour, not a defect to regression-test.
- Resolution status: accepted-as-is (the ephemeral-key behaviour is intentional for dev/test; the fix was operational — set a fixed local secret — not a code change).

### Observation — Deletion control hidden after disconnect

OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE

- Date and build SHA: 2026-08-05, Stage 11A Phase 6B
- Scenario: the cleanup sequence disconnected Account A before deleting its imported data.
- Expected result: the "Delete imported provider data" control would remain available to complete cleanup in the planned order.
- Observed result: the Connections page gates that control on the account still showing as *connected* — after disconnecting, the control disappeared from the UI, even though the backend route itself imposes no such requirement (ownership-only check).
- Objective evidence: `docs/evaluation/stage-11/owner-validation/phase-6b/defect-register.md`, D-6B-03.
- Owner impression: provided 2026-08-24 — no distinct recollection of this specific incident (see the §F walkthrough below for the owner's broader impressions).
- Severity: P3 (process finding, not a product defect).
- Repeatability: always, under this specific sequencing (disconnect-then-delete).
- Corrective action: the deletion was carried out by calling the same audited API path directly rather than through the UI; a future phase could reorder its own instructions, or the product could relax the frontend gate to allow deletion for a disconnected-but-still-owned account.
- Regression-test reference: none yet — tracked as a possible future frontend-gating change, not committed to in this phase.
- Resolution status: open (as a product-polish question — the underlying data was still deleted correctly via the backend route).

### Observation — Turbopack dev-cache contamination causing dev-server instability

OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE

- Date and build SHA: 2026-08-05, Stage 11A Phase 6B (surfaced during live testing, root cause traced to an earlier Phase 6A.1 task)
- Scenario: the frontend dev server was started for live testing.
- Expected result: the dev server would start and serve normally.
- Observed result: the owner reported the page "flickering" and "Try demo" not working — traced to `apps/web/.next-dev` containing absolute container-path references left over from an earlier, unrelated Linux Docker container task (bind-mounting the repo at `/work` for visual-snapshot regeneration), which the host `next dev` process couldn't resolve.
- Objective evidence: Phase 6B session notes; fixed by deleting `apps/web/.next-dev` and `apps/web/.next` (both gitignored, rebuildable).
- Owner impression: provided 2026-08-24 — no distinct recollection of this specific incident (see the §F walkthrough below for the owner's broader impressions).
- Severity: P3 (environmental, not a product defect).
- Repeatability: once, not yet reproduced since (only occurs after reusing a dev cache written by a container-based task).
- Corrective action: deleted the contaminated cache directories; no application code changed.
- Regression-test reference: none — environmental, not a code path.
- Resolution status: fixed (for this instance); no durable guard was added against a future recurrence of the same container/host cache-reuse pattern.

### Observation — Intermittent Google revoke-token failure at teardown

OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE

- Date and build SHA: 2026-08-14 (Phase 7 teardown) and 2026-08-17/23 (Phase 8/9), on `stage-11a-phase-7-soak-period` and successors
- Scenario: disconnecting Account A at the end of a live phase, which best-effort revokes the refresh token with Google before clearing local credentials (D20 — local disconnect must never be blocked by Google being unreachable).
- Expected result: Google's revoke endpoint would return HTTP 200 each time, as it had in Phase 6B.
- Observed result: Phase 7's teardown returned `revocation_confirmed: false` (a non-200/network-failure result, indistinguishable from the client side) — the owner independently checked Google's own connected-apps page and confirmed access was genuinely still active, so this was a real failure, not a masked success. Every other attempt (Phase 6B, and the retries in Phase 8/9) returned `true`.
- Objective evidence: `docs/evaluation/stage-11/owner-validation/phase-7/soak-completion-and-teardown.md`, `docs/evaluation/stage-11/owner-validation/phase-8/revocation-closure.md`, `docs/evaluation/stage-11/owner-validation/phase-9/verification-results.md`.
- Owner impression: provided 2026-08-24 — no distinct recollection of this specific incident (see the §F walkthrough below for the owner's broader impressions).
- Severity: P3 (a single observed instance; the product's own behaviour throughout — proceeding with local disconnect regardless, and recording `false` truthfully rather than assuming success — was correct by design).
- Repeatability: once, not yet reproduced (three other attempts across three different phases all succeeded).
- Corrective action: the owner manually revoked access via Google's own interface when this was found still active; no application code changed, since the app's behaviour on a revoke failure was already correct.
- Regression-test reference: `test_accounts_service.py` already asserts all three of `revocation_confirmed`'s truthful outcomes (`True`, `False`, `None`); no new test was needed, since this was a live external-service result, not a code defect.
- Resolution status: accepted-as-is (transient, correctly handled, independently confirmed closed via the owner's own Google-side check).

### Observation — §F walkthrough: the ten evaluation dimensions

OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE

- Date and build SHA: 2026-08-24, Stage 11A Phase 10, conversational walkthrough with the project owner (`main` post-PR-#22-merge).
- Scenario: the project owner was asked, one at a time, for a brief honest reaction to each of §F's ten evaluation dimensions, based on their own use of the product across this entire engagement.
- Observed result / owner impressions (owner's own words, lightly cleaned up for typos, meaning unchanged):
  1. **Onboarding clarity** — "I have done this a few times so I have gotten familiar with it." No friction reported.
  2. **Today scanability** — "Yes, it does read clearly indicating it's all about today and nothing else... which is the impression I get." No friction reported.
  3. **Priority relevance** — "This seems okay. Could be more colourful. Maybe a very dark UI interface might make things stand out better." Correctness not questioned; a visual-design suggestion, not a comprehension problem.
  4. **Evidence usefulness** — "I'm able to read through and understand it." No friction reported.
  5. **Approval comprehension** — "I know clicking on approve means I recognise and agree with the 'draft'." No friction reported.
  6. **Deletion-choice clarity** — **genuine finding, not just a neutral answer**: "Yes, I will need to know exactly what each does to ensure I do not perform any risky actions by accident." The owner does not feel the difference between the four deletion options (disconnect / imported-data / inferred-memory / account) is clear enough to act on confidently.
  7. **Outage guidance** — **genuine finding**: "No, this sometimes hasn't been clear."
  8. **Uncertain-outcome guidance** — **genuine finding**: "I have always disregarded items listed as uncertain. Not sure if this might be the right cause of action." The owner has consistently not acted on `uncertain` outcomes and is themselves unsure whether that's correct — directly relevant, since the product's design assumes a human resolves an uncertain outcome rather than ignoring it.
  9. **Navigation** — "Feels natural but I thought we could improve the look and appearance of these buttons." A visual-polish suggestion, not a wayfinding problem.
  10. **Recurring friction** (open-ended, plus a request for a reaction to the four defect-derived entries above) — "I have not noticed/experienced anything of that sort yet so can't tell." Recorded as: no distinct recollection of the four specific incidents, and no other recurring friction beyond what's covered in 1–9.
- Objective evidence: this conversation; no screenshot or log needed, as these are the owner's own stated impressions, not a reproducible technical scenario.
- Owner impression: *is* the observed result above — this entry records the owner's impressions directly, not Claude's inference about them.
- Severity: items 1, 2, 4, 5, 9, 10 — no defect (P4/informational, no action needed beyond noting 3 and 9's visual-design suggestions for a future design pass). Items 6, 7, 8 — **P2, genuine open usability findings**, none safety-critical but each real:
  - #6 (deletion-choice clarity): risk is *user* confusion leading to an unintended choice among destructive-adjacent options, not a product safety failure (every deletion path already requires its own typed confirmation phrase, per the product's design) — but the owner's own report that they'd need more clarity to feel confident is worth acting on.
  - #7 (outage guidance): the outage notice's wording/visibility has not always been clear to the one person who has seen it most.
  - #8 (uncertain-outcome guidance): most significant of the three — if the person most familiar with the product's internals defaults to ignoring `uncertain` outcomes, that is a real signal the current guidance does not sufficiently prompt the intended human follow-up action.
- Repeatability: consistent impressions, not one-off — these are the owner's standing view formed across the whole engagement, not a single incident.
- Corrective action: none taken this phase — these are UX/copy findings for a future design pass, not implemented here. Recording them honestly is this phase's job; fixing them is separate, future, explicitly-scoped work.
- Regression-test reference: none — these are open UX findings, not code defects with a test to write.
- Resolution status: open (items 6, 7, 8) — carried forward as genuine, named findings for a future UX/copy pass, not silently closed by this review.
