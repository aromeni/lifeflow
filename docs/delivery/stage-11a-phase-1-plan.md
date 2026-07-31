# Stage 11A Phase 1 Plan — Synthetic Acceptance Validation

**Status:** Plan complete; execution recorded in [the evidence pack](../evaluation/stage-11/owner-validation/phase-1/) · **Date:** 2026-07-30

Companion: [stage-11a-owner-validation-plan.md](stage-11a-owner-validation-plan.md) · [owner-validation-success-criteria.md](../evaluation/stage-11/owner-validation-success-criteria.md) · [owner-validation-evidence-register.md](../evaluation/stage-11/owner-validation-evidence-register.md)

## Objective

**Prove that LifeFlow's complete owner-facing workflow behaves safely, correctly and repeatably under deterministic synthetic scenarios before any external Google account or long-running owner dogfooding is introduced.**

## Scope

Everything reachable in demo mode against the existing synthetic dataset (`apps/api/src/lifeflow_api/demo/data/v1/`) and the existing test-only fake-Google-server resilience stack: landing/onboarding, Today/brief generation, Gmail draft proposals, Calendar event proposals, Approvals, Audit History, Connections/privacy controls, all four deletion/disconnect paths, temporary-outage and uncertain-execution handling, rate limiting, and synthetic-environment reset/repeatability.

## Explicit exclusions

No real Google account is connected. No test-only Google account (Stage 11A §B) is created. No 14–30 day soak period (Stage 11A §C) is started. No participant is recruited or contacted. No paid infrastructure is provisioned. No Stage 12 work occurs. No Stage 11 completion tag is created.

## Method

Rather than re-inventing scenarios, this phase treats the existing, already-CI-green backend/frontend/E2E suites as authoritative automated evidence — re-run fresh on this branch, not merely trusted from memory — and adds two genuinely new pieces of coverage this phase specifically needs and that didn't previously exist:

1. **A reset-repeatability harness** (`apps/api/tests/test_stage11a_phase1_reset_repeatability.py`): no production "wipe and reseed" endpoint exists (the only reset endpoint, `POST /__control__/reset` in `apps/api/src/lifeflow_api/testing/fake_google_server.py`, is scoped to the resilience test harness, not general demo state). Ten cycles of create-synthetic-user → import demo dataset → generate brief → create and execute one proposal → verify counts → run the already-tested full-account-deletion path as the reset → verify zero residual content-bearing records, using the same service layer the API routes call, so behaviour is identical to going through HTTP.
2. **An owner-operated Playwright walkthrough script** (`apps/web/e2e-owner-validation/phase1-walkthrough.spec.ts`) driving the real running application through every journey in §16 of the Phase 1 instruction, capturing screenshots of synthetic-data-only screens that are inspected directly (not merely asserted against) to produce genuine owner observations.

Every other required area (Gmail draft-only enforcement, Calendar insert-only enforcement, approval binding/tamper resistance, audit history read-only/pagination, all four deletion paths, outage/uncertain-execution handling, rate limiting/proxy-spoofing resistance, cross-user isolation) already has dedicated, passing automated tests from Stages 6, 7, 9, and 10 — see [the acceptance matrix](../evaluation/stage-11/owner-validation/phase-1/acceptance-matrix.md) for the exact file:function citation backing each row. This phase's job for those areas is to actually re-run them now and confirm they still pass, not to assume they do.

## Repetition requirements

Reset-repeatability: 10 complete cycles (§14 of the instruction), each independently verified for zero residual content-bearing data and zero duplicate/uncontrolled provider-side writes. Full suite re-run: once, in full, sequentially where infrastructure (Postgres/Redis) is shared, per the existing scripts' own concurrency constraints (`scripts/e2e.sh` and `scripts/e2e-design.sh` share a stack; `scripts/e2e-resilience.sh` uses a dedicated stack and must not run concurrently with either).

## Pass/fail rules

A scenario row passes only when its cited automated test is green on this branch (re-run, not assumed) and, where a manual/owner-observed row exists, the corresponding walkthrough screenshot confirms the expected UI state. See [owner-validation-success-criteria.md](../evaluation/stage-11/owner-validation-success-criteria.md) for the underlying thresholds this phase is scoped against.

## Defect-severity rules

P0 (safety/privacy) and P1 (core-task) findings pause closure, get root-caused, fixed, regression-tested, and the affected workflow is rerun — no unresolved P0/P1 at Phase 1 exit. P2 findings are fixed where practical or recorded with an explicit rationale and future condition. P3 findings are documented only. See [issue-register-template.md](../evaluation/stage-11/issue-register-template.md) for the shared severity definitions this phase reuses rather than redefining.

## Evidence requirements

Per [owner-validation-evidence-register.md](../evaluation/stage-11/owner-validation-evidence-register.md): automated-test output, synthetic scenario results, anonymised screenshots containing only synthetic data, and an owner-observation log labelled `OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE`. No raw database, Redis dump, runtime log with private content, browser trace, unredacted screenshot, credential, or token is ever committed.

## Reset requirements

The reset-repeatability harness (above) must: remove prior synthetic state safely (via the tested account-deletion path, not raw SQL); recreate the expected fixtures identically each cycle (the demo dataset's fixture IDs — `em-001`, `ev-001`, etc. — are static, so identity is guaranteed by construction); preserve no previous cycle's user-specific state (each cycle uses a fresh synthetic user, deleted at cycle end); avoid real credentials and provider calls (uses the synthetic connectors, never a live Google API); be idempotent (delete-then-recreate is safe to repeat); and fail loudly on partial completion (a pytest assertion failure, not a silent skip).

## Exit decision

Recorded in [phase-1-decision.md](../evaluation/stage-11/owner-validation/phase-1/phase-1-decision.md): PASS — READY FOR PHASE 2, CONDITIONAL PASS, or FAIL — NOT READY, per the criteria in the Phase 1 instruction. Phase 2 (if reached) means controlled failure/recovery exercises (Stage 11A §D) — never test accounts or soak testing (§B/§C), which remain separately gated.
