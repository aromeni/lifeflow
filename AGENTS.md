
# LifeFlow AI — Codex Repository Instructions

## Required reading order

Before planning or modifying code, read:

1. `CLAUDE.md`
2. `docs/delivery/engineering-acceptance-contract.md`
3. `.claude/skills/lifeflow-mvp-builder/SKILL.md`
4. `docs/project/project-foundation.md`
5. `docs/product/mvp-scope.md`
6. `docs/architecture/adr/0001-architecture.md`
7. `docs/architecture/adr/0002-evaluation-targets.md`
8. `docs/security/threat-model.md`
9. `docs/delivery/stage-plan.md`
10. `docs/delivery/reports/stage-05.md`
11. Relevant source code and tests

Treat the SKILL.md stage definitions and the Project Foundation as binding
project instructions even though they were originally created for Claude Code.

**The Engineering Acceptance Contract governs every delivery phase, regardless
of which coding model performs the work.** It defines the requirement
inventory, implementation loop, evidence rules, negative-control requirement,
and completion-report format a phase must satisfy before it can be reported
as done. It supersedes ad hoc judgement about when a phase is "done enough"
to hand back for review — see its authority order (§2) for how it interacts
with this file, `CLAUDE.md`, and the phase specification.

## Current build status

Stages 0–8 are complete and approved. Stage 8 is merged to `main`
(`c5b60b1`) and tagged `stage-8-complete`.

**Stage 9 — privacy, audit UX, and resilience — is in progress but is not
complete.** Delivery Phase 1 is remotely preserved at `49f121a`. Delivery
Phase 2 is remotely finalised at `fdb4636` on
`origin/stage-9-deletion-retention`. Delivery Phase 3 (audit history) is
remotely finalised at `a50cf06` on `origin/stage-9-audit-history`.

Delivery Phase 4 (rate limiting) is committed locally as six commits on
`stage-9-rate-limiting` from the approved parent `a50cf06`, and awaits remote
finalisation — not pushed, not tagged. Delivery Phase 5 (resilience and
telemetry) has not begun. No `stage-9-complete` tag exists, and Stage 9 has
not been merged to `main`. Do not begin a Delivery Phase without explicit
approval.

## Permanent rules

- Preserve existing architecture and naming conventions.
- Optimise for maintainability over cleverness.
- Prefer explicit, readable and testable code.
- Do not introduce new frameworks without a measured need.
- Do not allow LLM output to execute external actions directly.
- Do not send email; Gmail writes remain draft-only.
- Preserve the approval-bound Stage 7 calendar-event creation path and the
  simulated demo executors; do not add external side effects in Stage 9.
- External side effects always require exact user approval.
- Edited payloads invalidate previous approval.
- Approved and executed payloads must match exactly.
- Every action must pass deterministic policy validation.
- Every state transition and execution attempt must be audited.
- Preserve user ownership enforcement.
- Run tests before and after implementation.
- Never disable or weaken tests to make the build pass.
- Do not create a commit unless explicitly instructed.
- Complete only the explicitly approved Delivery Phase, produce its completion
  report, and stop for explicit approval.

## Stage-gated behaviour

Before editing:

1. Inspect the repository.
2. Run the existing baseline checks.
3. Summarise the current architecture.
4. Explain the approved Delivery Phase implementation plan.
5. Identify security and migration risks.
6. Confirm that no later Delivery Phase functionality is included.

Then implement only the explicitly approved Delivery Phase, run every required
quality gate, produce its defined completion report, and stop for explicit
approval.
