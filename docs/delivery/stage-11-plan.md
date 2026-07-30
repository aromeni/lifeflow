# Stage 11 Plan — Evaluation and Pilot Readiness

**Status:** Planning complete, implementation not begun · **Date:** 2026-07-30

Companion documents: [stage-plan.md](stage-plan.md) · [ADR 0002 — evaluation targets](../architecture/adr/0002-evaluation-targets.md) · [assumptions-and-decisions.md](assumptions-and-decisions.md) · [docs/evaluation/stage-11/](../evaluation/stage-11/)

## 1. Purpose

Stage 11 is the evidence gate between a technically complete, visually polished product (Stage 10, `stage-10-complete`) and packaging, deployment, and a later controlled pilot (Stages 12–14). It exists to answer one question with evidence, not opinion: **is LifeFlow ready to justify the cost of packaging and deployment?**

Stage 11 determines whether LifeFlow:

- addresses a meaningful recurring problem;
- is understandable without engineering assistance;
- presents useful and correctly prioritised information;
- communicates its safety boundaries accurately;
- earns sufficient user trust;
- produces action proposals users consider useful;
- is ready to justify packaging and future deployment costs.

Passing technical tests (unit, integration, E2E, accessibility, visual regression — all green as of Stage 10) is a precondition for Stage 11, not a substitute for it. A product can be fully tested and still fail Stage 11 if real people do not understand it, do not trust it, or do not find it useful.

Stage 11 has three parallel tracks, all required before the pilot-readiness gate (§12) can be evaluated:

1. **Human evaluation** (this plan's primary focus) — two-round formative usability/trust/safety-comprehension evaluation with representative participants, detailed in [docs/evaluation/stage-11/](../evaluation/stage-11/).
2. **Technical evaluation** — the blind holdout + adversarial evaluation set and the real-provider (`det+anthropic`) run, both already scoped in [ADR 0002](../architecture/adr/0002-evaluation-targets.md)'s "Development-set status and holdout plan." This closes the "dev-set only" caveat that has applied to every quoted quality metric since Stage 4.
3. **Privacy/terms review** — a qualified professional review of the draft privacy notice and terms (see [stage-plan.md](stage-plan.md)'s External Setup table), required before any real user's data is processed in a pilot.

This document plans track 1 in full and cross-references tracks 2 and 3 so a reader sees the complete Stage 11 scope in one place. Tracks 2 and 3 are pre-existing, already-approved scope (ADR 0002; External Setup table) — this planning pass does not re-litigate them, only schedules them alongside track 1.

Stage 11 is **not** the controlled production pilot. The controlled pilot with real, consenting users and real inboxes is Stage 14, gated on Stage 11 evidence plus Stage 12 packaging plus Stage 13 production deployment.

## 2. Target-user hypothesis

LifeFlow's MVP was designed for a specific, evidence-tied profile (see [project-foundation.md](../project/project-foundation.md) §1, [mvp-scope.md](../product/mvp-scope.md)). Stage 11 tests, rather than assumes, that this profile is correct.

**Primary-user hypothesis:** *A busy knowledge worker who coordinates commitments through Gmail and Google Calendar loses time identifying priorities, remembering follow-ups, and translating communications into safe next actions.*

This is a hypothesis to test, not an established fact. It is deliberately narrow — tied to the product's actual workflow — rather than a decorative persona with invented biographical detail.

| Dimension | Definition for recruitment |
|---|---|
| Role/professional profile | Busy UK-based professional, consultant, postgraduate student, or freelancer who manages their own inbox and calendar without an assistant |
| Work context | Coordinates meetings, requests, and deadlines primarily through Gmail and Google Calendar; no dedicated executive-assistant support |
| Typical Gmail/Calendar usage | Checks email multiple times daily; calendar holds both fixed commitments and self-scheduled work; receives a mix of actionable requests and low-signal noise |
| Recurring coordination problems | Misses or delays follow-ups; forgets promises made in passing; discovers scheduling conflicts late; struggles to separate urgent from routine |
| Current alternatives | Manual triage, calendar reminders, personal to-do apps, mental tracking — no existing tool combines evidence, priority, and safe action |
| Existing frustrations | Time lost to re-reading old threads; anxiety about "what am I forgetting"; distrust of tools that act autonomously |
| Privacy concerns | Wary of a third-party tool reading email content; wants to know exactly what is stored and for how long |
| Reasons to trust LifeFlow | Read-only by default; every action requires explicit approval with an exact payload preview; full audit trail |
| Reasons to reject LifeFlow | Perceives it as "just another inbox tool"; distrusts AI summarisation accuracy; concerned about scope creep into autonomous sending |
| Adoption conditions | Brief must be faster to read than triaging manually; proposed actions must be correct often enough to be worth reviewing; safety model must be immediately legible |
| Exclusion criteria | Does not personally manage their own Gmail/Calendar (e.g., has a dedicated assistant); does not use Gmail or Google Calendar as a primary tool; unwilling to complete a session using synthetic demo data |

## 3. Evaluation design

A two-round formative evaluation, run entirely in deterministic demo mode against synthetic data. See [docs/evaluation/stage-11/](../evaluation/stage-11/) for full materials.

| | Round 1 | Round 2 |
|---|---|---|
| Participants | 3–5 | 5–8 |
| Purpose | Identify major comprehension, trust and usability failures; discover unexpected interpretations; validate the evaluation script itself | Verify Round 1 issues were resolved; establish pilot-readiness evidence; produce the Stage 11 go/no-go decision |
| Data | Deterministic demo mode, synthetic data only | Deterministic demo mode, synthetic data only (real data requires separate approval, not assumed here) |
| Method | Facilitated, think-aloud, qualitative discovery emphasis | More structured task completion, limited facilitator intervention, quantitative threshold measurement |
| Materials | Draft [task-protocol.md](../evaluation/stage-11/task-protocol.md) and questionnaires, expected to be revised after Round 1 | Corrected product (if P0/P1 fixes were needed) and corrected evaluation materials |
| Real Gmail/Calendar connection | None | None |

Round 1 findings that surface P0/P1 issues (§10) pause the evaluation until fixed and regression-tested, per the engineering acceptance contract's completion conditions — this plan does not authorise shipping a fix without its own test coverage.

## 4. Participant journeys

Twenty scripted journeys, defined in full in [task-protocol.md](../evaluation/stage-11/task-protocol.md), cover onboarding comprehension, brief interpretation, evidence inspection, action-proposal review and approval semantics, uncertain-outcome and outage comprehension, audit history, and the full disconnect/deletion distinction set (account disconnect vs. imported-data deletion vs. inferred-memory deletion vs. permanent account deletion).

## 5. Safety-comprehension protocol

A dedicated questionnaire ([safety-questionnaire.md](../evaluation/stage-11/safety-questionnaire.md)) tests, independently of task success, whether participants can correctly state: Gmail actions create drafts only; Calendar actions create new events only, never edit or delete existing ones; approval is bound to the exact payload shown; disconnect differs from imported-data deletion; inferred-memory deletion differs from account deletion; Audit History is read-only. Zero critical safety misunderstandings is a hard threshold (§6), consistent with S1/S2 in [mvp-scope.md](../product/mvp-scope.md).

## 6. Success thresholds

See [success-criteria.md](../evaluation/stage-11/success-criteria.md) for the full table. Thresholds are fixed before Round 1 begins and are not lowered after seeing results.

## 7. Issue severity

P0 (safety/privacy blocker) through P3 (minor), defined in [issue-register-template.md](../evaluation/stage-11/issue-register-template.md). No unresolved P0 or P1 issue is permitted at Stage 11 exit.

## 8. Analysis and evidence

See [findings-template.md](../evaluation/stage-11/findings-template.md) for the analysis method (task-success rates, comprehension rates, SUS-equivalent score, Round 1 vs. Round 2 comparison, hypothesis-by-hypothesis evidence, limitations). Given sample sizes of 3–8 and 5–8, results are reported descriptively; this plan explicitly rejects presenting them as statistically generalisable.

## 9. Data governance

See [data-governance.md](../evaluation/stage-11/data-governance.md). Defaults: no recording, pseudonymous participant IDs, minimal demographic data, synthetic product data only, short retention. No real Gmail or Calendar data is used in the initial (Round 1/Round 2) evaluation under this plan.

If this evaluation is conducted in connection with university research, the relevant university ethics approval and supervisor sign-off must be obtained before participant recruitment begins — this plan does not claim, and must not be read as claiming, that such approval already exists.

## 10. Pilot-readiness gate

Defined in full in [go-no-go-template.md](../evaluation/stage-11/go-no-go-template.md):

- **GO** — all mandatory thresholds met, no unresolved P0/P1, pilot materials complete, Stage 12 packaging justified by evidence.
- **CONDITIONAL GO** — no unresolved safety blocker, but bounded, time-boxed P2 remediation or evidence collection required before Stage 12 spend.
- **NO-GO** — a valid outcome, triggered by unresolved safety misunderstanding, poor core-task completion, low perceived usefulness, inability to recruit suitable participants, or inadequate privacy/consent arrangements. A NO-GO must not be reframed as partial success.

## 11. Cost policy

- Stage 11 does not require permanent paid cloud infrastructure. Deterministic local demo mode (already built, Stage 3+) is the default and sole evaluation environment under this plan.
- Participant incentives are optional and require separate, explicit approval before any spend — none is authorised by this document.
- Temporary hosting is considered only if local evaluation cannot meet a specific, justified requirement, and requires separate approval — none is provisioned by this document.
- No cloud production account (hosting provider, etc.) is provisioned during Stage 11 planning or execution.
- Stage 12 and Stage 13 spending decisions depend on Stage 11 evidence, not on Stage 11 merely having started.

| Item | Provisional cost | Approval authority |
|---|---|---|
| Local evaluation (demo mode, existing infra) | £0 | Already approved (existing dev environment) |
| Participant incentives (optional) | Not budgeted here | Requires explicit user approval before any offer is made |
| Room/travel (optional, if in-person) | Not budgeted here | Requires explicit user approval |
| Temporary hosting (only if local proves insufficient) | Not budgeted here | Requires explicit user approval; must be justified in writing first |

## 12. Stage 11 exit criteria

Stage 11 is complete when: both evaluation rounds have run, the findings report and go/no-go decision are recorded, all P0/P1 issues raised during evaluation are resolved and regression-tested, the holdout+adversarial evaluation set (track 2) has been run and recorded in ADR 0002, and the privacy-notice professional review (track 3) is complete. None of this work is performed by this planning document — it defines how that work will be done and is filed for review before any of it begins.
