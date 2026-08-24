# Stage 11A — Owner Observation Template

**Status:** Template, plus four entries consolidated from existing phase defect registers (Phase 10, 2026-08-24) — see the note at the top of the Log section for what that does and does not mean · **Date:** 2026-07-30 (log entries added 2026-08-24)

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

None of these four cover the purely subjective dimensions §F also lists
(onboarding clarity, Today scanability, priority relevance, evidence
usefulness, approval comprehension, deletion-choice clarity, outage
guidance, uncertain-outcome guidance, navigation/responsive behaviour) —
those were never separately, deliberately walked through and recorded by
the owner as a self-review exercise, and are not addressed by this
consolidation.

### Observation — Session invalidated by an API restart

OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE

- Date and build SHA: 2026-08-05, Stage 11A Phase 6B (`stage-11a-phase-6b-calendar-write-trigger` branch)
- Scenario: mid-live-session, the local API process was restarted to apply a configuration-flag change.
- Expected result: the owner's browser session would remain valid across the restart.
- Observed result: the owner was logged out (`✕ Not signed in`) — every API restart with no fixed `SESSION_SECRET` in the local `.env` generates a fresh ephemeral signing key, which is documented, intentional dev-only behaviour, not a bug.
- Objective evidence: `docs/evaluation/stage-11/owner-validation/phase-6b/defect-register.md`, D-6B-02.
- Owner impression: not yet provided.
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
- Owner impression: not yet provided.
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
- Owner impression: not yet provided.
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
- Owner impression: not yet provided.
- Severity: P3 (a single observed instance; the product's own behaviour throughout — proceeding with local disconnect regardless, and recording `false` truthfully rather than assuming success — was correct by design).
- Repeatability: once, not yet reproduced (three other attempts across three different phases all succeeded).
- Corrective action: the owner manually revoked access via Google's own interface when this was found still active; no application code changed, since the app's behaviour on a revoke failure was already correct.
- Regression-test reference: `test_accounts_service.py` already asserts all three of `revocation_confirmed`'s truthful outcomes (`True`, `False`, `None`); no new test was needed, since this was a live external-service result, not a code defect.
- Resolution status: accepted-as-is (transient, correctly handled, independently confirmed closed via the owner's own Google-side check).
