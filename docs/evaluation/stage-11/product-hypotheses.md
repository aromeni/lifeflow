# Stage 11 — Product Hypothesis Register

**Status:** Planning document · **Date:** 2026-07-30

Companion: [stage-11-plan.md](../../delivery/stage-11-plan.md) · [success-criteria.md](success-criteria.md) · [task-protocol.md](task-protocol.md)

Each hypothesis below is written to be falsified, not confirmed. "Evidence required" names the specific observation; "evaluation task" points to the task-protocol.md item(s) that produce it; "metric" and thresholds are drawn from [success-criteria.md](success-criteria.md); "decision consequence" states what changes if the hypothesis fails.

## Problem hypotheses

| ID | Hypothesis | Evidence required | Evaluation task(s) | Metric | Success threshold | Failure threshold | Decision consequence |
|---|---|---|---|---|---|---|---|
| P-H1 | Users experience meaningful cognitive overload from Gmail and Calendar | Participant self-report of pre-existing overwhelm/anxiety about missed items | T20, interview guide | % participants affirming the problem unprompted or on direct question | ≥ 70% | < 40% | If failed: target-user hypothesis (§2 of stage-11-plan.md) needs revision before further investment |
| P-H2 | Important commitments are missed or identified too late without LifeFlow | Participant recounts a specific past incident of a missed/late commitment | Interview guide | % participants citing a concrete incident | ≥ 60% | < 30% | If failed: reconsider "Waiting For" and priority-scoring value proposition |
| P-H3 | Users spend repeated effort deciding what deserves attention | Participant describes manual triage effort in current workflow | Interview guide | Qualitative theme presence | Theme present in majority of sessions | Theme absent | If failed: brief's core value proposition (orientation speed) is weaker than assumed |
| P-H4 | Existing tools do not adequately combine evidence, priority and safe action | Participant names a gap in current tools when prompted with alternatives | Interview guide | Qualitative theme presence | Theme present in majority of sessions | Theme absent | If failed: differentiation messaging on the landing page needs rework |

## Value hypotheses

| ID | Hypothesis | Evidence required | Evaluation task(s) | Metric | Success threshold | Failure threshold | Decision consequence |
|---|---|---|---|---|---|---|---|
| V-H1 | The Today brief reduces orientation time | Participant reports/estimates faster orientation than their current method | T4, post-session questionnaire | Brief comprehension rating | Avg ≥ 4/5 | Avg < 3/5 | If failed: brief layout/section design needs revision before Stage 12 |
| V-H2 | Explanations improve confidence in prioritisation | Participant correctly restates "why this matters" for the top item | T5, T6, T7 | Priority-relevance / explanation-usefulness rating | ≥ 80% correct restatement | < 50% | If failed: reason-code copy needs rework |
| V-H3 | Waiting For items help users track external dependencies | Participant correctly interprets a Waiting For item's meaning and status | T8 | Task success rate | ≥ 80% | < 50% | If failed: Waiting For section needs a redesign or clearer copy |
| V-H4 | Proposed actions reduce follow-up effort | Participant judges a shown draft/event proposal as saving them time | T9, T11, post-session questionnaire | % proposals judged useful | ≥ 70% | < 40% | If failed: action-proposal generation quality, not just UI, needs Stage-11-track-2 attention |
| V-H5 | Audit History increases trust | Participant reports increased confidence after viewing Audit History | T15, post-session questionnaire | Trust rating delta pre/post | Positive median shift | Neutral or negative | If failed: Audit History presentation needs revision |
| V-H6 | Explicit approval provides sufficient control | Participant reports feeling in control when reviewing a proposal | T10, T12, post-session questionnaire | Perceived-control rating | Avg ≥ 4/5 | Avg < 3/5 | If failed: approval UI needs revision before Stage 12 |

## Usability hypotheses

| ID | Hypothesis | Evidence required | Evaluation task(s) | Metric | Success threshold | Failure threshold | Decision consequence |
|---|---|---|---|---|---|---|---|
| U-H1 | Onboarding is understandable without assistance | Participant completes onboarding (T2) without facilitator intervention | T2 | Onboarding completion without help | ≥ 80% | < 50% | If failed: onboarding copy/flow needs redesign before Round 2 |
| U-H2 | Today can be scanned quickly | Participant identifies top priority within a short time budget | T5 | Time-to-identify | Median ≤ target set after Round 1 baseline | Median exceeds target by >2x | If failed: Today information density needs review |
| U-H3 | Priority labels are interpreted correctly | Participant correctly explains what a priority label means | T5, T6 | Correct-interpretation rate | ≥ 80% | < 50% | If failed: priority-label copy/iconography needs revision |
| U-H4 | Evidence and "why this matters" are useful | Participant reports evidence links helped them trust the item | T7 | Usefulness rating | Avg ≥ 4/5 | Avg < 3/5 | If failed: evidence-surfacing UI needs revision |
| U-H5 | Approval payloads are understood | Participant correctly states exactly what will happen if they approve | T9, T10, T11 | Exact-consequence-understood rate | ≥ 90% | < 70% | If failed: this is treated as a P0/P1 issue, not merely a usability finding — see safety hypotheses below |
| U-H6 | Privacy and deletion choices are distinguishable | Participant correctly distinguishes disconnect / imported-data deletion / memory deletion / account deletion | T16–T19 | Correct-distinction rate | ≥ 90% | < 70% | If failed: Connections & Privacy screen copy needs redesign before Stage 12 |

## Safety hypotheses

| ID | Hypothesis | Evidence required | Evaluation task(s) | Metric | Success threshold | Failure threshold | Decision consequence |
|---|---|---|---|---|---|---|---|
| S-H1 | Users understand that Gmail actions create drafts only, never send | Safety questionnaire item answered correctly | Safety questionnaire, T9 | % correct | 100% | Any incorrect answer | Any failure is P0 (§ issue-register-template.md); evaluation pauses |
| S-H2 | Users understand that Calendar actions create new events only | Safety questionnaire item answered correctly | Safety questionnaire, T11 | % correct | 100% | Any incorrect answer | P0; evaluation pauses |
| S-H3 | Users understand existing events are never edited or deleted | Safety questionnaire item answered correctly | Safety questionnaire | % correct | 100% | Any incorrect answer | P0; evaluation pauses |
| S-H4 | Users understand approval is bound to the exact payload shown | Safety questionnaire item + T10 | Safety questionnaire, T10 | % correct | ≥ 90% | < 70% | P1 if below threshold; must fix before Stage 11 closure |
| S-H5 | Users do not blindly retry an uncertain external outcome | Behavioural observation during T13 | T13 | % participants pausing/checking before retry | 100% unsafe-retry avoidance | Any unsafe retry | Any unsafe retry is P0; evaluation pauses |
| S-H6 | Users understand disconnect vs. imported-data deletion | Safety questionnaire + T17 | Safety questionnaire, T17 | % correct | ≥ 90% | < 70% | P1 if below threshold |
| S-H7 | Users understand inferred-memory deletion vs. account deletion | Safety questionnaire + T18 | Safety questionnaire, T18 | % correct | ≥ 90% | < 70% | P1 if below threshold |
| S-H8 | Users understand Audit History is read-only | Safety questionnaire + T15 | Safety questionnaire, T15 | % correct | 100% | Any incorrect answer | P0; evaluation pauses |

Every hypothesis maps to at least one task-protocol.md item and at least one success-criteria.md threshold, mirroring the traceability convention already used in [mvp-scope.md](../../product/mvp-scope.md).
