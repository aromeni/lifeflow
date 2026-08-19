# Stage 11A — Owner-Validation Exit Decision

**Status:** Filled in — Stage 11A execution complete through Phase 8 · **Date:** 2026-08-19 (template created 2026-07-30)

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

Four explicit, non-safety P2 conditions keep this from an unqualified
READY (see "Conditions" below). None implicates safety, privacy, duplicate
writes, cross-user isolation, or any deletion path — each is a scope gap
against the original Stage 11A plan's assumptions, honestly recorded rather
than silently reconciled, per
[owner-validation-success-criteria.md](owner-validation-success-criteria.md)'s
2026-08-19 changelog entry and
[phase-8/gm12-deferral.md](owner-validation/phase-8/gm12-deferral.md).

The soak itself ran 10 days (257.9 hours), on the project owner's own
explicit authorisation (`AUTHORISE A 10-DAY STAGE 11A OWNER-ONLY SOAK`),
not the 14–30 days `stage-11a-owner-validation-plan.md` §C originally
envisioned. This is treated as the owner exercising their own authority to
set scope, not as a shortfall — the "soak period... completed" READY
condition is considered met on the terms the owner actually set.

**Conditions (CONDITIONAL READINESS):**

1. **GM-12 / fresh-trigger stale-follow-up re-verification.** The
   deterministic detector logic is already proven correct independent of
   live Gmail (`test_overdue_follow_ups`); what remains unconfirmed is
   whether real Gmail's `SENT`/`INBOX` labels and thread IDs propagate
   correctly through the real connector. A fresh trigger
   (`P8-FOLLOWUP-TEST-01`) was sent 2026-08-17; re-verifiable any time from
   2026-08-23 onward. No fixed deadline — see
   [phase-8/gm12-deferral.md](owner-validation/phase-8/gm12-deferral.md)
   for the exact re-verification steps.
2. **Daily brief generation under real elapsed time was not measured.**
   Phase 7's soak deliberately ran read-only sync only, never brief
   generation, to avoid running extraction/proposal-composition
   unattended against the live account for 10 days. Re-verification would
   require a separate, bounded, owner-attended exercise (not a repeat of
   the full soak) that runs brief generation against a real connected
   account across at least several real days and confirms stable,
   consistent output with no unexplained failures.
3. **No formal owner-usability self-review (§F) was conducted** using
   [owner-observation-template.md](owner-observation-template.md)'s
   structured, labelled format. Substantively similar content exists
   scattered across phase defect registers (e.g. D-6B-02 session
   invalidation on restart, D-6B-03 deletion-control UI gating, Turbopack
   cache contamination, the Phase 7/8 revoke-token intermittent failure),
   but was never consolidated into the prescribed
   `OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE` format. Re-verification:
   a dedicated pass through §F's evaluation list, recorded in that
   template, whenever convenient.

4. **§D's "low disk space" failure/recovery exercise was never run.**
   Checked directly against Phase 2's evidence pack (`owner-validation/phase-2/`)
   — no mention of a disk-space exercise anywhere in it; every other §D
   item (API/web/worker/scheduler restart, Redis/PostgreSQL outage,
   provider-timeout before/after write, token expiry, revoked consent,
   backup/restore, rollback) is present, this one specifically is not. Not
   safety-blocking on its own (no code path in this application writes
   unbounded local data outside the database/Redis containers, which have
   their own operational monitoring), but it is a genuine, named gap
   against §D's original list rather than a silently-assumed pass.
   Re-verification: a bounded local exercise filling the disk (or a
   constrained test volume) and confirming the API degrades safely rather
   than corrupting data.

**Evidence citations:** see
[owner-validation-evidence-register.md](owner-validation-evidence-register.md)
for the full phase-by-phase evidence-pack index this decision is built on.

**Decided by:** Produced by Claude Code per the project owner's explicit
instruction ("Proceed with Stage 11A Phase 8 — Closure and Exit... Produce
a final Stage 11A owner-validation exit decision"), for project-owner
review.

**Date:** 2026-08-19
