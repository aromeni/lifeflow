# Delivery Stage Plan

**Status:** Stage 9 in progress; Delivery Phases 1–4 remotely complete; Delivery Phase 5 fully converged on `stage-9-resilience-telemetry`, not yet committed · **Date:** 2026-07-29

**Stage 9 (privacy, audit UX, resilience) is in progress and is not complete.** The Stage 9 Planning Gate (architecture/discovery) is approved and recorded in [ADR 0005](../architecture/adr/0005-stage9-privacy-hardening.md). Delivery is split into five phases: **Delivery Phase 1 — Privacy & Connections Control Centre** is remotely preserved at `49f121a`; **Delivery Phase 2 — imported-data deletion, retention enforcement, account deletion** is remotely finalised at `fdb4636` on `origin/stage-9-deletion-retention`; **Delivery Phase 3 — audit history** is remotely finalised at `a50cf06` on `origin/stage-9-audit-history`; and **Delivery Phase 4 — rate limiting** is remotely finalised at `481a67b` on `origin/stage-9-rate-limiting`. **Delivery Phase 5 — outage resilience and privacy-safe telemetry** is fully implemented and verified on `stage-9-resilience-telemetry` (base: the Phase 4 tip `481a67b`) — including all four required outage-simulation Playwright journeys (a test-only fake-Google server plus a dedicated resilience stack, `apps/web/e2e-resilience/`), full provider-metrics coverage of the ingestion read path, and a complete 17-item live manual smoke test — but not yet committed, not pushed, not tagged — see [the Phase 5 completion report](reports/stage-09-phase-5.md) for the full acceptance-matrix result and recommended commit split. No `stage-9-complete` tag exists, and Stage 9 has not been merged to `main`. "Delivery Phase 1" always refers to the Privacy Centre, never the planning gate. Stage 8 remains complete/approved/merged (`main` `c5b60b1`; tag `stage-8-complete` → `a29d6ee`).

**Stage 8 (preferences, memory, schedule) is complete and approved.** All three phases — Phase 1 (explicit preferences), Phase 2 (the scheduled brief, arq+Redis), and Phase 3 (inferred memory) — passed the committed-state closure review as one integrated milestone. Phase 3 delivered one narrow typed memory (`preferred_email_signoff`) with a full transparent lifecycle: observed edited-then-approved drafts → visible candidate with deterministic confidence and inspectable evidence → user confirm/edit/dismiss/delete → confirmed value applied only through the explicit preference registry, previewed and approved like any draft (ADR 0004 D51–D58). The Phase 3 implementation commit is `466de179a7af1fe6410ee4e4f661402bec5b8925`; Stage 8 is merged to `main` at `c5b60b1` and tagged `stage-8-complete` at `a29d6ee`.

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
| 6 — Proposals & approval inbox (approved) | Safe, editable next steps | Inspect/edit/approve/reject/trace with zero hidden side effects | 5 |
| 7 — Real Google integration (approved) | Proven workflow on real data | Test user connects Google, gets brief, approves draft/event, sees audit | 6 |
| **8 — Preferences, memory, schedule** (complete, approved) | Transparent adaptation | Scheduled brief at configured time reflecting visible preferences | 7 |
| **9 — Privacy, audit UX, resilience** (in progress) | Trust features operational | Users control data; product fails safely in outages | 8 |
| 10 — Evaluation & pilot readiness | Evidence of usefulness | Acceptance targets met or exceptions documented; pilot pack ready | 9 |
| 11 — Packaging & commercial base | Demonstrable, pilotable, extensible | Staging deploy passes smoke tests; editions via configuration | 10 |

Each stage ends with: all required checks run, implementation inspected (not just exit codes), docs and decision log updated, a completion report in the standard format, then **stop**. Every completion report is archived in [reports/](reports/) as `stage-NN.md` — the project's engineering log.

## Engineering Acceptance Contract

Every delivery phase — regardless of which coding model performs the work — must follow the [Engineering Acceptance Contract](engineering-acceptance-contract.md). It governs how a phase specification becomes a numbered acceptance matrix, the implementation/verification loop the agent runs autonomously, which ordinary engineering gaps must be fixed without a review round-trip, the negative-control and exact-boundary security-proof requirements, and the standard completion-report structure. It applies from Stage 9 Delivery Phase 5 onward; phases delivered before it was adopted (Stages 0–8 and Stage 9 Delivery Phases 1–4) are not retroactively re-audited against it. Every future phase prompt should open with the instruction in the contract's §17.

## Quality gates at every stage

Formatter · linter · type checker · unit tests · relevant integration tests · stage-appropriate security checks · build · documentation check. Tests are never disabled to obtain a green build. From Delivery Phase 5 onward, gates are also governed by the [Engineering Acceptance Contract](engineering-acceptance-contract.md)'s completion conditions (§12).

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

North Star (long-term vision, permanent principles, guard rails): [../project/project-foundation.md](../project/project-foundation.md). Architecture decisions: [../architecture/adr/0001-architecture.md](../architecture/adr/0001-architecture.md). Assumptions and open decisions: [assumptions-and-decisions.md](assumptions-and-decisions.md). Product scope: [../product/mvp-scope.md](../product/mvp-scope.md). Threats: [../security/threat-model.md](../security/threat-model.md). Engineering delivery process: [engineering-acceptance-contract.md](engineering-acceptance-contract.md). Operational runbooks (Stage 9 Delivery Phase 5): [runbooks/outage-response.md](runbooks/outage-response.md), [runbooks/provider-failure.md](runbooks/provider-failure.md), [runbooks/worker-recovery.md](runbooks/worker-recovery.md), [runbooks/health-readiness.md](runbooks/health-readiness.md). When scope or design questions arise, the Project Foundation document is the single source of truth.
