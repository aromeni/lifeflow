# Stage 11A — Owner-Validation Exit Decision

**Status:** Filled in — Stage 11A execution through Phase 10, plus Stage 11B (pre-recruitment UX hardening); all seven conditions now closed, verdict reassessment recorded below, pending the project owner's explicit decision · **Date:** 2026-09-03 (originally recorded 2026-08-19, template created 2026-07-30)

Companion: [owner-validation-success-criteria.md](owner-validation-success-criteria.md) · [owner-validation-evidence-register.md](owner-validation-evidence-register.md) · [recruitment-authorisation-checklist.md](recruitment-authorisation-checklist.md)

**This template must not be filled in until Stage 11A execution — synthetic validation, failure/recovery exercises, the security/privacy review, and (if reached) the soak period — has actually run.** No decision has been made as of this document's creation.

## Decision options

### READY FOR INDEPENDENT ETHICS AND RECRUITMENT PREPARATION

Requires all of:

- [ ] All mandatory thresholds in [owner-validation-success-criteria.md](owner-validation-success-criteria.md) met.
- [ ] No unresolved P0 or P1 finding in the owner-validation issue log.
- [ ] The soak period (§C, 14–30 days) completed, if it was reached.
- [ ] All failure/recovery exercises (§D) completed.
- [ ] Any test-account cleanup (§B) verified — no residual test-account data.
- [ ] The product is stable enough that a participant would not be acting as a defect-finder for problems Stage 11A should have already caught.

### CONDITIONAL READINESS

Permitted only when every safety/privacy/core-task-completion condition above is met, but one or more explicit, testable, non-safety P2 conditions remain. Every condition must state: what must change, by when, and how it will be re-verified.

### NOT READY

Triggered by any of:

- An unresolved safety or privacy issue.
- An unreliable core workflow (brief generation, approval, or execution).
- A repeated duplicate-write or uncertain-write defect.
- Inadequate deletion (imported-data, inferred-memory, or account).
- A cross-user isolation concern.
- Unstable daily operation during the soak period.
- Insufficient internal evidence to make any of the above determinations confidently.

A NOT READY outcome is valid and must not be reframed as partial success.

## What this decision does not do

**This decision does not itself authorise recruitment.** Even a READY verdict only means Stage 11A's own bar has been met — [recruitment-authorisation-checklist.md](recruitment-authorisation-checklist.md) and [evaluation-context-decision.md](evaluation-context-decision.md)'s outstanding items (ethics/privacy/lawful-basis resolution for the INDEPENDENT PRODUCT EVALUATION route) remain separate, unresolved gates.

## Decision record

**Decision:** **CONDITIONAL READINESS**

**Rationale:**

Every safety, privacy, core-task-completion, duplicate/uncertain-write, and
cross-user-isolation condition is met, with zero unresolved P0 or P1
findings across all 8 phases (1, 2, 3, 4A, 4B, 4C, 4D, 5, 6, 6A, 6A.1, 6B,
7, 8 — see [owner-validation-evidence-register.md](owner-validation-evidence-register.md)):

- Gmail send capability and Calendar edit/delete capability are both
  confirmed structurally absent, not merely policy-absent (Phase 4B, Phase
  6B).
- Zero duplicate provider writes and zero automatic uncertain-write
  retries were observed across every failure/recovery exercise (Phase 2)
  and across the entire 10-day soak (Phase 7) — including several genuine,
  unplanned real-world Docker/DB/Redis outages that all self-recovered
  cleanly with no flag drift and no data loss.
- Cross-user isolation, private-content redaction, secret hygiene, and all
  four deletion paths (imported-data, inferred-memory, account, full
  disconnect) were independently verified by inspection, repeatedly, not
  merely trusted from UI success messages (Phase 3, and re-confirmed at
  every subsequent phase's teardown through Phase 8).
- The soak period (Phase 7) directly observed and correctly handled the
  previously-undecided Google Testing-status 7-day refresh-token boundary
  — a single, non-retried `409`, a truthful audit trail, and an
  independently-verified controlled reconnection — resolving
  `soak-period-decision.md`'s Option A in practice, not just on paper.

Four explicit, non-safety P2 conditions originally kept this from an
unqualified READY (see "Conditions" below). **All four are now closed**:
GM-12 (Phase 9, 2026-08-23), §D's low-disk-space exercise (Phase 10,
2026-08-24), the owner-usability self-review (Phase 10, 2026-08-24), and
daily brief generation under real elapsed time (Phase 10, 2026-08-31).
None of the four implicated safety, privacy, duplicate writes, cross-user
isolation, or any deletion path — each was a scope gap against the
original Stage 11A plan's assumptions, honestly recorded rather than
silently reconciled, per
[owner-validation-success-criteria.md](owner-validation-success-criteria.md)'s
2026-08-19 changelog entry and
[phase-8/gm12-deferral.md](owner-validation/phase-8/gm12-deferral.md).

Closing the usability-review condition itself surfaced **three new,
separate, genuine P2 findings** (not exit conditions at the time — a
completed review does not require zero findings): deletion-choice
clarity, outage guidance, and — most significantly — uncertain-outcome
guidance, where the owner reported consistently disregarding `uncertain`
results rather than acting on them. See
[owner-observation-template.md](owner-observation-template.md)'s "§F
walkthrough" entry.

**Verdict re-affirmed, not upgraded (decided 2026-09-01):** with all four
originally-named conditions closed, the project owner was asked to choose
between an upgraded verdict (treating the three new findings as
carried-forward improvement items) or continuing `CONDITIONAL READINESS`
with the three new findings as its named conditions, and explicitly chose
the latter. The reasoning: the template's own READY bar requires "the
product is stable enough that a participant would not be acting as a
defect-finder for problems Stage 11A should have already caught," and the
uncertain-outcome finding is exactly that — a real, owner-demonstrated
point of confusion in a design that assumes a human resolves an uncertain
outcome. Recommending READY here would knowingly carry a known, unfixed
gap into a future human-participant evaluation instead of treating it as
what Stage 11A is for: catching this before a participant does. The three
findings become this document's new conditions below; the original four
are kept, struck through, for the historical record.

The soak itself ran 10 days (257.9 hours), on the project owner's own
explicit authorisation (`AUTHORISE A 10-DAY STAGE 11A OWNER-ONLY SOAK`),
not the 14–30 days `stage-11a-owner-validation-plan.md` §C originally
envisioned. This is treated as the owner exercising their own authority to
set scope, not as a shortfall — the "soak period... completed" READY
condition is considered met on the terms the owner actually set.

**Original conditions (all closed — kept for the historical record):**

1. ~~**GM-12 / fresh-trigger stale-follow-up re-verification.**~~ **CLOSED
   2026-08-23 (Phase 9).** `P8-FOLLOWUP-TEST-01`, sent 2026-08-17, was
   reconnected, synced, and briefed 6 days later: it correctly imported
   with `folder: "sent"` and was correctly identified by
   `detect_follow_ups` as an unanswered follow-up
   (`reason_codes: ["no_reply_6d"]`, confidence 0.85) — confirming real
   Gmail's `SENT`/`INBOX` labels and thread IDs propagate correctly through
   the real connector into the exact shape the detector expects. See
   [phase-9/verification-results.md](owner-validation/phase-9/verification-results.md)
   and [phase-9/phase-9-decision.md](owner-validation/phase-9/phase-9-decision.md).
2. ~~**Daily brief generation under real elapsed time was not measured.**~~
   **CLOSED 2026-08-31 (Phase 10).** Three independently-verified
   check-ins (Day 0 2026-08-24, Day 3 2026-08-27, Day 7 2026-08-31)
   spanning just under 7 real days against the real reconnected Account A,
   each running the full protocol (sync → brief generation → duplicate
   checks → write checks): zero duplicates, zero unauthorised writes, and
   only expected, explainable variation (per-day version numbering,
   date-relative extraction counts, newly-due proposals appearing as
   calendar time genuinely advanced). See
   [phase-10/brief-generation-daily-log.md](owner-validation/phase-10/brief-generation-daily-log.md)
   and [phase-10/phase-10-decision.md](owner-validation/phase-10/phase-10-decision.md).
3. ~~**No formal owner-usability self-review (§F) was conducted.**~~
   **CLOSED 2026-08-24 (Phase 10).** The four already-known friction
   points were reformatted into
   [owner-observation-template.md](owner-observation-template.md)'s
   prescribed format, and the project owner then conducted a genuine,
   direct, conversational walkthrough of all ten §F dimensions with Claude,
   giving their own impressions in their own words for each. Seven
   dimensions surfaced no defect (two carried a visual-design suggestion
   only); **three surfaced genuine, open P2 findings, carried forward as
   product-improvement items, not silently closed**: deletion-choice
   clarity (the owner does not feel the difference between the four
   deletion options is clear enough to act on confidently), outage
   guidance (has not always been clear when seen), and — the most
   significant — uncertain-outcome guidance (the owner has consistently
   disregarded `uncertain` results rather than acting on them, which cuts
   against the product's own design assumption that a human resolves an
   uncertain outcome). Closing this condition required conducting the
   review, not achieving zero findings — see
   [phase-10/owner-usability-review-status.md](owner-validation/phase-10/owner-usability-review-status.md).

4. ~~**§D's "low disk space" failure/recovery exercise was never run.**~~
   **CLOSED 2026-08-24 (Phase 10).** Run against an isolated, throwaway
   48MB-tmpfs Postgres container — never the real dev database or host
   disk. Confirmed the app degrades safely under genuine disk exhaustion
   (a clean `500` with no leaked internals, zero partial/corrupted rows, no
   crash) and recovers automatically the instant space frees, with no
   restart required. See
   [phase-10/low-disk-space-results.md](owner-validation/phase-10/low-disk-space-results.md).

**Conditions 5–7 (all closed — kept for the historical record):**

5. ~~**Deletion-choice clarity.**~~ **CLOSED 2026-09-03 (Stage 11B).** A
   comparison table added to the Connections page states removes/keeps/
   reversible for all four controls in one place; disconnect and both
   memory-delete controls now require an explicit confirm step naming the
   consequence before firing. Re-verified: the owner, walking through the
   real UI, stated the distinction and consequence of each option without
   hesitation ("its a yes, makes sense"). See
   [phase-11b/owner-walkthrough.md](owner-validation/phase-11b/owner-walkthrough.md).
6. ~~**Outage guidance.**~~ **CLOSED 2026-09-03 (Stage 11B).** Every
   existing outage/degraded-state surface (Google sync degraded/error,
   Gmail/Calendar partial-read, Today's brief partial/degraded notices)
   revised to explicitly state what's unavailable, what remains safe,
   whether action is needed, and retry guidance — verified against actual
   backend behaviour first, so no copy overclaims. Re-verified: the owner
   confirmed a real outage screenshot was clear ("Outage guidance, yes!").
   See [phase-11b/owner-walkthrough.md](owner-validation/phase-11b/owner-walkthrough.md).
7. ~~**Uncertain-outcome guidance (the most significant of the three).**~~
   **CLOSED 2026-09-03 (Stage 11B).** The uncertain-execution notice now
   explains all five required elements (outcome unknown; why no
   auto-retry; action-type-specific what-to-verify; what's safe next; how
   reconciliation becomes authorised — honestly: no in-product mechanism
   exists today) without adding any new state-mutating capability against
   the no-automatic-retry invariant. Re-verified: the owner, shown a real
   uncertain-execution screenshot and asked directly whether this changes
   what they'd do given their prior admission of always disregarding such
   items, confirmed it does ("yes makes sense"). See
   [phase-11b/owner-walkthrough.md](owner-validation/phase-11b/owner-walkthrough.md).

None of the three implicated safety, privacy, duplicate/uncertain writes,
cross-user isolation, or any deletion path's correctness — they were
clarity/guidance gaps in already-correct, already-safe behaviour, closed
by the smallest coherent UX/copy remediation (Stage 11B), not by lowering
any threshold.

## Verdict reassessment (2026-09-03, Stage 11B)

With all seven conditions across Stage 11A and Stage 11B now closed, this
section walks the READY checklist above against current evidence, as
directed by the project owner's Stage 11B authorisation ("reassess the
Stage 11 exit verdict against the existing exit-template criteria").

- [x] All mandatory thresholds in
  [owner-validation-success-criteria.md](owner-validation-success-criteria.md)
  met — every row of that table's threshold checked against phase
  evidence; the "Owner friction" row's bar ("documented with remediation
  or explicit, reasoned acceptance") is now met in its stronger form
  (remediated and re-verified, not merely accepted).
- [x] No unresolved P0 or P1 finding in the owner-validation issue log —
  unchanged, zero across all phases.
- [x] The soak period (§C) completed — met on the terms the owner set
  (10 days / 257.9 hours), as previously recorded.
- [x] All failure/recovery exercises (§D) completed — Phase 2 plus
  Phase 10's low-disk-space exercise.
- [x] Test-account cleanup (§B) verified — Phase 10's teardown, zero
  residue, independently confirmed on Google's own side.
- [x] The product is stable enough that a participant would not be acting
  as a defect-finder for problems Stage 11A should have already caught —
  this was the specific criterion that justified re-affirming
  `CONDITIONAL READINESS` on 2026-09-01 rather than upgrading. The gap it
  named (the owner would hit unresolved confusion on an uncertain
  outcome) has since been closed and independently re-verified by the
  owner directly. This box is now checked on genuine evidence, not
  assumption.

**Claude's recommendation:** every box above is met. The honest reading of
this document's own decision framework is
**READY FOR INDEPENDENT ETHICS AND RECRUITMENT PREPARATION** — not because
the bar was lowered, but because the specific, named gaps that justified
`CONDITIONAL READINESS` have each been closed and re-verified in turn
(GM-12, low-disk-space, and daily-brief-generation in Stage 11A Phase 10;
deletion clarity, outage guidance, and uncertain-outcome guidance in Stage
11B). As stated throughout this document, **a READY verdict here does not
itself authorise recruitment** — `recruitment-authorisation-checklist.md`
(items 5–20) and `evaluation-context-decision.md`'s outstanding ethics/
privacy/lawful-basis items remain entirely separate, unresolved gates.
This recommendation is not self-executing: the `Decision:` field below is
left as `CONDITIONAL READINESS` until the project owner explicitly
directs otherwise, consistent with how every prior verdict change in this
engagement has been made.

**Evidence citations:** see
[owner-validation-evidence-register.md](owner-validation-evidence-register.md)
for the full phase-by-phase evidence-pack index this decision is built on.

**Decided by:** Produced by Claude Code per the project owner's explicit
instruction ("Proceed with Stage 11A Phase 8 — Closure and Exit... Produce
a final Stage 11A owner-validation exit decision"), for project-owner
review. Condition 1 revised 2026-08-23 following Phase 9's fresh-trigger
verification, at the project owner's request. Conditions 3 and 4 revised
2026-08-24 following Phase 10's low-disk-space exercise and a direct
conversational §F walkthrough with the project owner. Condition 2 revised
2026-08-31 following Phase 10's three-check-in brief-generation exercise.
On 2026-09-01, given Claude's explicit recommendation to re-affirm rather
than upgrade the verdict, the project owner directed exactly that;
conditions 5–7 were added accordingly. On 2026-09-03, per the project
owner's explicit Stage 11B authorisation, conditions 5–7 were closed
following implementation and a real owner re-verification walkthrough of
each; the verdict reassessment above was produced per that same
authorisation's instruction to "reassess the Stage 11 exit verdict against
the existing exit-template criteria." The `Decision:` field itself is left
unchanged pending the project owner's explicit direction.

**Date:** 2026-08-19 (condition 1 closed 2026-08-23; conditions 3 and 4 closed 2026-08-24; condition 2 closed 2026-08-31; conditions 5–7 set 2026-09-01, closed 2026-09-03)
