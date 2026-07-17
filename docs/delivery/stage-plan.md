# Delivery Stage Plan

**Status:** Stage 6 complete pending approval (Stages 0–5 approved) · **Date:** 2026-07-16

**Active stage: 6 (complete pending approval).** Stage 7 is not active and cannot begin without explicit human approval of the Stage 6 completion report. Silence is never approval. Commits are made only when explicitly requested.

Guiding rule: *build one trustworthy end-to-end loop, prove it with tests and evidence, then expand deliberately.* The first end-to-end path is:

```text
Gmail + Calendar → Daily Brief → Proposed Action → Approval → Execution → Audit
```

…delivered **first in demo mode** (Stages 3–6) and only then against real Google APIs (Stage 7).

## Stage summary and gates

| Stage | Goal | Key exit criterion | Depends on |
|---|---|---|---|
| 0 — Discovery & plan (approved) | Precise, buildable MVP plan | Product explainable in one page; first E2E path unambiguous; risks documented | — |
| 1 — Scaffold & foundations (approved) | Reproducible monorepo runs locally | Clean clone → configure → run → test → stop, predictably | 0 |
| 2 — Domain model, auth, isolation (approved) | Secure data foundation | Cross-user isolation proven; migrations stable; token encryption path exists | 1 |
| 3 — Demo mode & synthetic connectors (approved) | First vertical slice, no credentials | Demo user sees coherent normalised information | 2 |
| 4 — Signals & priority engine (approved) | Defensible prioritised signals | Requests/deadlines/follow-ups/conflicts ranked with evidence; injection fixtures safe | 3 |
| 5 — Daily brief (approved) | First genuinely useful outcome | Brief understandable in < 2 min; every actionable statement evidenced | 4 |
| **6 — Proposals & approval inbox** (complete pending approval) | Safe, editable next steps | Inspect/edit/approve/reject/trace with zero hidden side effects | 5 |
| 7 — Real Google integration | Proven workflow on real data | Test user connects Google, gets brief, approves draft/event, sees audit | 6 |
| 8 — Preferences, memory, schedule | Transparent adaptation | Scheduled brief at configured time reflecting visible preferences | 7 |
| 9 — Privacy, audit UX, resilience | Trust features operational | Users control data; product fails safely in outages | 8 |
| 10 — Evaluation & pilot readiness | Evidence of usefulness | Acceptance targets met or exceptions documented; pilot pack ready | 9 |
| 11 — Packaging & commercial base | Demonstrable, pilotable, extensible | Staging deploy passes smoke tests; editions via configuration | 10 |

Each stage ends with: all required checks run, implementation inspected (not just exit codes), docs and decision log updated, a completion report in the standard format, then **stop**. Every completion report is archived in [reports/](reports/) as `stage-NN.md` — the project's engineering log.

## Quality gates at every stage

Formatter · linter · type checker · unit tests · relevant integration tests · stage-appropriate security checks · build · documentation check. Tests are never disabled to obtain a green build.

## External setup the user will eventually need (none blocks demo-mode development)

| Item | Needed by stage | Notes |
|---|---|---|
| Docker Desktop (or compatible) locally | 1 | Postgres via compose |
| Git hosting + CI (GitHub assumed) | 1 | CI config lands with the scaffold |
| Google Cloud project with OAuth consent screen (External, test users), Gmail + Calendar APIs enabled, OAuth client (web) credentials | 7 | Scopes: `gmail.readonly`, `gmail.compose`, `calendar.readonly`, `calendar.events`; test with a sandbox Google account, never a primary mailbox first |
| Anthropic API key | 4 (optional) | Only for LLM-assisted extraction; mock provider covers demo/CI |
| UK/EU hosting provider account | 11 | Chosen in ADR 0004; nothing earlier depends on it |
| Qualified professional review of privacy notice/terms | 10 | Drafts produced in stage 10 |

## Risk register (implementation risks, Stage 0)

| Risk | Impact | Mitigation |
|---|---|---|
| Google OAuth verification friction (restricted Gmail scopes require review for production) | Delays real-user pilot | Develop against test users on an unverified consent screen; scope-minimal design; begin verification paperwork during Stage 7, pilot with ≤100 test users meanwhile |
| LLM extraction quality below targets | Weak briefs | Deterministic detectors are the floor; targets ratified only after baseline (ADR 0002); degraded mode is a feature |
| Two-toolchain drift (TS/Python) | Contract bugs | Generated contracts in `packages/contracts`; contract tests in CI |
| Prompt-injection regressions | Safety failure | Closed action-type enum, policy engine, adversarial fixtures in CI from Stage 4 |
| Scope creep toward editions/connectors | MVP never ships | Out-of-scope list in [../product/mvp-scope.md](../product/mvp-scope.md); extension points recorded, not built |
| Timezone/DST defects (Europe/London) | Wrong deadlines/schedules | UTC storage + tz-aware rendering; DST boundary tests from Stage 3 |
| Solo-developer bus factor / stall | Delivery risk | Stage gates keep the repo always in a documented, runnable state |

## Decision log and documentation index

North Star (long-term vision, permanent principles, guard rails): [../project/project-foundation.md](../project/project-foundation.md). Architecture decisions: [../architecture/adr/0001-architecture.md](../architecture/adr/0001-architecture.md). Assumptions and open decisions: [assumptions-and-decisions.md](assumptions-and-decisions.md). Product scope: [../product/mvp-scope.md](../product/mvp-scope.md). Threats: [../security/threat-model.md](../security/threat-model.md). When scope or design questions arise, the Project Foundation document is the single source of truth.
