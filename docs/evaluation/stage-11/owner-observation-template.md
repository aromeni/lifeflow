# Stage 11A — Owner Observation Template

**Status:** Template, no entries yet — Stage 11A execution has not begun · **Date:** 2026-07-30

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

_(No entries — Stage 11A execution has not begun.)_
