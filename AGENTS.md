
# LifeFlow AI — Codex Repository Instructions

## Required reading order

Before planning or modifying code, read:

1. `CLAUDE.md`
2. `.claude/skills/lifeflow-mvp-builder/SKILL.md`
3. `docs/project/project-foundation.md`
4. `docs/product/mvp-scope.md`
5. `docs/architecture/adr/0001-architecture.md`
6. `docs/architecture/adr/0002-evaluation-targets.md`
7. `docs/security/threat-model.md`
8. `docs/delivery/stage-plan.md`
9. `docs/delivery/reports/stage-05.md`
10. Relevant source code and tests

Treat the SKILL.md stage definitions and the Project Foundation as binding
project instructions even though they were originally created for Claude Code.

## Current build status

Stages 0–5 are complete.

The active stage is:

**Stage 6 — Action proposals and approval inbox**

Do not implement Stage 7 or later functionality.

## Permanent rules

- Preserve existing architecture and naming conventions.
- Optimise for maintainability over cleverness.
- Prefer explicit, readable and testable code.
- Do not introduce new frameworks without a measured need.
- Do not allow LLM output to execute external actions directly.
- Do not send emails or create real calendar events.
- Use simulated executors during Stage 6.
- External side effects always require exact user approval.
- Edited payloads invalidate previous approval.
- Approved and executed payloads must match exactly.
- Every action must pass deterministic policy validation.
- Every state transition and execution attempt must be audited.
- Preserve user ownership enforcement.
- Run tests before and after implementation.
- Never disable or weaken tests to make the build pass.
- Do not create a commit unless explicitly instructed.
- Stop after the Stage 6 Completion Report.

## Stage-gated behaviour

Before editing:

1. Inspect the repository.
2. Run the existing baseline checks.
3. Summarise the current architecture.
4. Explain the Stage 6 implementation plan.
5. Identify security and migration risks.
6. Confirm that no Stage 7 functionality is included.

Then implement Stage 6, run every required quality gate, produce the defined
Stage 6 Completion Report and stop for explicit approval.
