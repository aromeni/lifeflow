# Stage 11A Plan — Owner-Only Internal Validation

**Status:** Execution complete (Phases 1–8); Stage 11A exit decision recorded (CONDITIONAL READINESS) · **Date:** 2026-08-19 (originally 2026-07-30)

Companion: [stage-11-plan.md](stage-11-plan.md) · [evaluation-context-decision.md](../evaluation/stage-11/evaluation-context-decision.md) · [owner-validation-success-criteria.md](../evaluation/stage-11/owner-validation-success-criteria.md) · [owner-validation-evidence-register.md](../evaluation/stage-11/owner-validation-evidence-register.md) · [owner-observation-template.md](../evaluation/stage-11/owner-observation-template.md) · [owner-validation-exit-template.md](../evaluation/stage-11/owner-validation-exit-template.md)

## Objective

**Rigorously test, dogfood, and challenge LifeFlow through owner-operated, synthetic, and dedicated-test-account scenarios before any external participant is asked to evaluate it.**

Stage 11A sits before Stage 11's human-participant evaluation track (`docs/evaluation/stage-11/`), not instead of it. It exists because the current operational mode is OWNER-ONLY INTERNAL VALIDATION (see [evaluation-context-decision.md](../evaluation/stage-11/evaluation-context-decision.md)) — participant recruitment remains blocked, but that doesn't mean no evaluation work can happen: it means the evaluation work available right now is the owner's own, not a participant's. Stage 11A's job is to prove the product is stable and safe enough that a future participant isn't the first person to discover a defect.

## Relationship to the rest of Stage 11

- Does not replace, shorten, or substitute for the human-participant evaluation planned in [stage-11-plan.md](stage-11-plan.md) and `docs/evaluation/stage-11/`.
- Its exit decision ([owner-validation-exit-template.md](../evaluation/stage-11/owner-validation-exit-template.md)) is a precondition for *considering* recruitment, not an authorisation of it — [recruitment-authorisation-checklist.md](../evaluation/stage-11/recruitment-authorisation-checklist.md) governs that separately and is not advanced by anything in Stage 11A.
- Owner observations recorded here are engineering evidence about the product, never participant research evidence, and must never be merged into or presented alongside participant statistics (see [owner-observation-template.md](../evaluation/stage-11/owner-observation-template.md)).

## A. Synthetic validation

Owner-operated walkthroughs against the existing deterministic demo dataset (`apps/api/src/lifeflow_api/demo/data/v1/`) and application:

- all deterministic demo scenarios in `docs/evaluation/stage-11/synthetic-scenario-manifest.md` (explicit request, near-deadline, overdue follow-up, calendar conflict, newsletter deprioritisation, prompt injection, ambiguous/low-confidence);
- every Today dashboard category (Needs Attention, Upcoming, Waiting For, Suggested Actions);
- Gmail draft proposals — review, approve, edit, reject;
- Calendar event-insertion proposals — review, approve, edit, reject;
- rejection and editing paths for both proposal types;
- Audit History — read-only confirmation, filtering, plain-language descriptions;
- the four disconnect/deletion distinctions (account disconnect, imported-data deletion, inferred-memory deletion, full account deletion);
- the transient-outage fixture (`apps/web/e2e-resilience/stage10-outage-notice-fixture.spec.ts`);
- the uncertain-execution fixture (`apps/web/e2e-resilience/stage10-uncertain-execution-fixture.spec.ts`);
- rate limiting behaviour (Stage 9 Delivery Phase 4);
- account deletion, exercised in a demo/test context only;
- reset and repeatability — confirming the demo environment returns to an identical starting state across repeated runs.

This track reuses existing automated suites (`./scripts/e2e.sh`, `./scripts/e2e-resilience.sh`, `./scripts/e2e-design.sh`, `uv run pytest`) plus owner-operated manual walkthroughs for anything not already automated. No new synthetic scenario needs to be invented — the manifest already grounds this in real fixtures.

## B. Dedicated owner-controlled test accounts

**Planning only. No account is connected by this document or this task.** Actual connection of any test account requires a separate, explicit approval — this section defines the requirements that approval would need to confirm, not a green light to proceed.

Requirements for any future test-account connection:

- newly created test-only Google accounts, never the owner's personal account;
- no personal inbox or Calendar data of any kind imported or referenced;
- no third-party confidential information (e.g., real correspondence from real people) placed into a test account;
- only disposable, synthetic messages and events authored specifically for testing;
- clear, documented separation from any personal account (separate credentials, separate OAuth consent grant, never reused);
- a documented account-deletion and cleanup procedure, executed and verified after each test-account use, before the credentials are considered "done with."

## C. Long-running dogfooding (soak period)

**Planning only. No soak period is started by this document.**

A future owner-only soak period of **14–30 days**, once test accounts (§B) or continued demo-mode use makes it meaningful, would measure:

- daily brief generation reliability (success rate, latency, degraded-mode fallback correctness);
- worker and scheduler reliability (arq + Redis, per Stage 8 Phase 2);
- OAuth refresh behaviour, using approved test accounts only — never a personal account;
- duplicate-prevention correctness under real elapsed time and real retries;
- stale-execution recovery;
- Redis interruption recovery;
- database restart recovery;
- accumulated Audit History correctness over many real events, not just a seeded demo set;
- deletion completion (imported-data, inferred-memory, account) verified after real accumulated use;
- storage growth over the soak period;
- error frequency and classification;
- owner-perceived usefulness (recorded per [owner-observation-template.md](../evaluation/stage-11/owner-observation-template.md), explicitly not participant evidence);
- owner trust and friction, same caveat.

## D. Failure and recovery exercises

**Planning only. No exercise is run by this document.** Controlled, owner-triggered tests for:

- API process restart;
- web process restart;
- worker crash;
- scheduler interruption;
- Redis loss (already partially covered by `journey-c-worker-outage-recovery.spec.ts` and `journey-d-dependency-health.spec.ts` — this section extends manual/owner-operated coverage, it doesn't duplicate the automated suite);
- PostgreSQL interruption;
- provider timeout before a write is attempted;
- provider timeout after a write is attempted (the uncertain-execution case, already fixture-covered — extended here to a real test-account context once §B is approved);
- token expiry;
- revoked consent;
- low disk space;
- failed-deployment rollback, where locally reproducible (no production deployment exists yet — this is a local/demo-environment exercise);
- backup creation and restore, in a local/test environment only.

## E. Security and privacy review

**Planning only. No review is executed by this document.**

- secret-rotation rehearsal (rotating a local `.env` value and confirming the app picks it up correctly, without ever handling a real production secret);
- access-token exposure checks (confirming tokens never appear in logs, per the redaction rules in `docs/security/threat-model.md`);
- log and metric inspection for private-content leakage;
- Redis key inspection for private-content leakage;
- database owner-scoping review (every table's `user_id` enforcement, re-confirmed manually against the automated isolation tests);
- cross-user isolation, re-confirmed manually;
- account-disconnect cleanup, verified by inspection, not just by the UI reporting success;
- imported-data deletion, verified by inspection;
- inferred-memory deletion, verified by inspection;
- full account deletion, verified by inspection;
- residual-data inspection after every deletion path above;
- dependency and container scanning where applicable (existing `gitleaks`/`detect-secrets`/pre-commit tooling, run and reviewed, not merely assumed green).

## F. Owner usability self-review

The owner may record personal observations using [owner-observation-template.md](../evaluation/stage-11/owner-observation-template.md). **Every such entry must be visibly labelled `OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE`** and must never be combined with, averaged into, or presented alongside later participant statistics.

Evaluate:

- onboarding clarity;
- Today scanability;
- priority relevance;
- evidence usefulness;
- approval comprehension;
- deletion-choice clarity;
- outage guidance;
- uncertain-outcome guidance;
- navigation and responsive behaviour;
- recurring friction.

## What Stage 11A does not do

It does not recruit, contact, or collect data from any participant. It does not provision paid infrastructure. It does not connect a personal production Gmail or Calendar account. It does not begin Stage 12. It does not create a Stage 11 completion tag. It does not, by being planned or even executed, advance any row of [recruitment-authorisation-checklist.md](../evaluation/stage-11/recruitment-authorisation-checklist.md).

## Exit

Governed by [owner-validation-exit-template.md](../evaluation/stage-11/owner-validation-exit-template.md): READY FOR INDEPENDENT ETHICS AND RECRUITMENT PREPARATION, CONDITIONAL READINESS, or NOT READY — none of which themselves authorise recruitment.

## Phase 1 status (updated 2026-07-31)

**Phase 1 — Synthetic Acceptance Validation is complete: PASS — READY FOR PHASE 2.** See [stage-11a-phase-1-plan.md](stage-11a-phase-1-plan.md) and the full evidence pack in [docs/evaluation/stage-11/owner-validation/phase-1/](../evaluation/stage-11/owner-validation/phase-1/). Phases B (dedicated test accounts) and C (the soak period) remain planning-only — no test account was created or connected, and the soak period has not started. Phase 2 (failure and recovery exercises, §D) requires its own separate, explicit-approval task; it is not authorised by Phase 1's PASS decision.

## Phase 2 status (updated 2026-07-31)

**Phase 2 — Controlled Failure and Recovery Validation is complete: PASS — READY FOR PHASE 3.** See [stage-11a-phase-2-plan.md](stage-11a-phase-2-plan.md) and the full evidence pack in [docs/evaluation/stage-11/owner-validation/phase-2/](../evaluation/stage-11/owner-validation/phase-2/). This is the first execution of §D's failure/recovery exercises — API/web/worker/scheduler restart, Redis/PostgreSQL outage and recovery, provider-timeout and uncertain-write handling at the required repetition counts, token-expiry/revoked-consent handling, cross-user isolation under failure, and (genuinely new infrastructure this phase built) a local backup/restore rehearsal and a local rollback rehearsal. Phases B and C remain planning-only — no test account was created or connected, and the soak period has not started. Phase 3 (proposed: security, privacy, and residual-data validation) requires its own separate, explicit-approval task; it is not authorised by Phase 2's PASS decision and does not itself authorise Google test accounts or the soak period.

## Phase 3 status (updated 2026-07-31)

**Phase 3 — Security, Privacy and Residual-Data Validation is complete: CONDITIONAL PASS — READY FOR PHASE 4 READINESS GATE.** See [stage-11a-phase-3-plan.md](stage-11a-phase-3-plan.md) and the full evidence pack in [docs/evaluation/stage-11/owner-validation/phase-3/](../evaluation/stage-11/owner-validation/phase-3/). This is the first execution of §E's security-and-privacy review — owner-scoping under attack across 6 resource families, session/authentication edge cases, a real token sentinel lifecycle search, an honest secret-rotation-capability rehearsal, an end-to-end log-privacy sentinel scan, browser-storage inspection, injection resistance, the four privacy operations at required repetition counts, residual-data and tombstone analysis, a genuinely new backup-vs-deletion compliance rehearsal, and this project's first-ever dependency-vulnerability and container-hardening scans (which found and fixed two real gaps: a loopback-only local-service-binding fix and several Next.js/postcss/sharp CVEs). Zero product-code defects were found. All 44 acceptance-matrix scenarios PASS and zero P0/P1 findings exist; the decision is **conditional**, not failed, because two P2 findings remain open with an explicit closure condition each rather than fixed (`TOKEN_KEY` rotation capability — a direct Phase 4 connection blocker; `brace-expansion` dev-tooling exposure). Phases B and C remain planning-only — no test account was created or connected, and the soak period has not started. Phase 4 (proposed: Dedicated Test-Account Readiness and Controlled Connection Gate) requires its own separate, explicit-approval task; it is not authorised by Phase 3's decision and does not itself authorise Google test accounts or the soak period. **No Google test account may be connected until the project owner resolves the `TOKEN_KEY` rotation blocker** — see the "TOKEN_KEY rotation — Phase 4 connection blocker" section of [phase-3-decision.md](../evaluation/stage-11/owner-validation/phase-3/phase-3-decision.md).

## Phase 4A status (updated 2026-08-01)

**Phase 4A — Key-Versioned Credential Encryption and Rotation is complete: PASS — READY FOR PHASE 4B TEST-ACCOUNT READINESS.** See [stage-11a-phase-4a-plan.md](stage-11a-phase-4a-plan.md) and the full evidence pack in [docs/evaluation/stage-11/owner-validation/phase-4a/](../evaluation/stage-11/owner-validation/phase-4a/). The project owner selected Path A (key-versioned migration) for the `TOKEN_KEY` rotation blocker Phase 3 recorded; this phase implemented and verified it: a `TokenKeyRing` (one active key plus zero-or-more legacy keys, drop-in compatible with the existing `TokenCipher` protocol), a context-bound (AAD) `v2` credential envelope closing a previously-undocumented cross-account/cross-field ciphertext-transplant gap, a resumable, row-locked, `SKIP LOCKED`-based rotation/migration service, an Alembic migration adding queryable key-version columns, and two new rehearsal scripts (an 18-step key-rotation lifecycle and a backup/key-ring-retirement rehearsal), each run 3/3 cycles clean. **F-P3-03 is now closed** (see [f-p3-03-closure.md](../evaluation/stage-11/owner-validation/phase-4a/f-p3-03-closure.md)). **F-P3-04 (`brace-expansion`) was independently reassessed and is also closed** with fresh evidence (see [f-p3-04-reassessment.md](../evaluation/stage-11/owner-validation/phase-4a/f-p3-04-reassessment.md)) — no open P2/P3 condition remains from Phase 3. One implementation-time defect (a context-derivation ordering bug affecting brand-new OAuth connections) was found and fixed before any commit. Phases B and C remain planning-only — no test account was created or connected, and the soak period has not started. **Phase 4B (proposed: Dedicated Test-Account Readiness and Controlled Connection Gate) requires its own separate, explicit-approval task; it is not authorised by Phase 4A's decision and does not itself create or connect a Google account.**

## Phase 4B status (updated 2026-08-01)

**Phase 4B — Dedicated Test-Account Readiness and Controlled Connection Gate is complete: PASS — READY FOR OWNER CONNECTION AUTHORISATION.** See [stage-11a-phase-4b-plan.md](stage-11a-phase-4b-plan.md) and the full evidence pack in [docs/evaluation/stage-11/owner-validation/phase-4b/](../evaluation/stage-11/owner-validation/phase-4b/). This phase is readiness and planning only — it created no Google account, no Google Cloud project, no OAuth credential, and no authenticated or successful Google API interaction has ever occurred (one unintended, unauthenticated, tooling-only outbound attempt reached `gmail.googleapis.com` in an uncommitted early draft of this phase's own rehearsal script and was rejected by Google with HTTP 401 before any credential exchange — found and fixed before any pass was reported; a durable no-live-network guard now also prevents a recurrence — see the evidence pack's dry-run-results.md). It verified current official Google OAuth/Cloud/Gmail/Calendar requirements (dated 2026-08-01), including the honestly-recorded Testing-status constraint that a soak period will need a re-consent cadence or production-publishing decision the project owner has not yet made; derived and structurally proved the exact minimum OAuth scope set (Gmail send and Calendar update/delete remain impossible by construction, not merely by policy); designed a disposable two-account test-account model and dedicated Google Cloud project plan (neither created); closed 6 OAuth-callback state/binding test-coverage gaps and 3 production-guard test-coverage gaps found by inspection (all guards already worked — only their regression coverage was missing); built a new Phase 4B pre-connection gate and a broader preconnection-readiness command; ran an 18-step connection rehearsal 3/3 clean against only the existing fake-provider infrastructure (catching and fixing two rehearsal-script defects — including a real, tooling-only network call to Google's live API — before ever reporting a pass); and produced synthetic Gmail/Calendar dataset plans, a first-connection runbook, a two-decision (connect vs. write) authorisation gate, an emergency-stop plan, and a cleanup/revocation plan. Zero unresolved P0/P1. **This decision does not create or connect a Google account.** It allows the project owner to consider **AUTHORISE CREATION OF THE DISPOSABLE GOOGLE TEST ENVIRONMENT**, and, separately and later, the two further decisions in [provider-write-authorisation-gate.md](../evaluation/stage-11/owner-validation/phase-4b/provider-write-authorisation-gate.md).

## Phase 4C status (updated 2026-08-02)

**Phase 4C — Disposable Google Test Environment Creation is complete: PASS — READY FOR FIRST OAUTH CONNECTION AUTHORISATION.** See [stage-11a-phase-4c-plan.md](stage-11a-phase-4c-plan.md) and its [content-free evidence pack](../evaluation/stage-11/owner-validation/phase-4c/). `ACCOUNT_A` and `ACCOUNT_B`, one dedicated test-only Cloud project, exactly the Gmail and Calendar APIs, an External/Testing OAuth app, `ACCOUNT_A` as the sole test user, the exact approved four connector scopes, and one web client with the two approved localhost callbacks now exist. The one-client configuration is installed in the ignored local `.env`, values never entered Git/chat, the credential gate and redacted readiness checks are green, and a new default-deny initiation/callback flag keeps OAuth blocked.

No OAuth consent has been completed; no Google account is connected; stored credential/token count, Phase 4C Google data imports, successful Google API interactions, and provider writes are all zero. **SOAK PERIOD REMAINS BLOCKED**; recruitment remains not authorised; Stage 11A is not complete; Stage 12 is unstarted. The Phase 4C verdict does not authorise connection; it permits only the owner to consider `AUTHORISE FIRST OAUTH CONNECTION OF ACCOUNT A — READ-ONLY SMOKE TESTS ONLY` as a separate decision.

## Phases 4D–7 status (updated 2026-08-19, consolidated)

This section brings the phase log up to date — Phases 4D through 7 each ran under their own separate, explicit owner authorisation, with their own detailed plan and evidence pack; this entry indexes them rather than re-narrating each in full.

- **Phase 4D — First Real OAuth Connection** (`stage-11a-phase-4d-plan.md`, [evidence](../evaluation/stage-11/owner-validation/phase-4d/)): **PASS.** The first real, read-only OAuth connection, storage, and revocation of Account A.
- **Phase 5 — Synthetic Dataset Population** (`stage-11a-phase-5-plan.md`, [evidence](../evaluation/stage-11/owner-validation/phase-5/)): **PASS.** Manual population of Accounts A/B with the synthetic Gmail/Calendar dataset (GM-18/CAL-12 deliberately withheld at the time).
- **Phase 6 — First Real Ingestion and Gmail Draft** (`stage-11a-phase-6-plan.md`, [evidence](../evaluation/stage-11/owner-validation/phase-6/)): **CONDITIONAL PASS**, later closed. First real ingestion and first real Gmail-draft write validated end-to-end; Calendar write not validated this pass; found and fixed D-6-01, deferred D-6-02 (shared OIDC/connector-consent flag coupling) to a dedicated follow-up.
- **Phase 6A — Split OAuth Flags** (`stage-11a-phase-6a-plan.md`, [evidence](../evaluation/stage-11/owner-validation/phase-6a/)): **PASS.** Split the shared OAuth flag into independent `GOOGLE_OIDC_SIGNIN_ENABLED`/`GOOGLE_CONNECTOR_OAUTH_ENABLED`, closing D-6-02 at its root cause.
- **Phase 6A.1 — Frontend Flag Alignment** (`stage-11a-phase-6a1-plan.md`, [evidence](../evaluation/stage-11/owner-validation/phase-6a1/)): **PASS.** Aligned the frontend's capability flags and UI gating with the Phase 6A split (no backend change).
- **Phase 6B — First Real Calendar Insertion** (`stage-11a-phase-6b-plan.md`, [evidence](../evaluation/stage-11/owner-validation/phase-6b/)): **PASS.** First real Calendar-event insertion validated with a corrected, dedicated trigger (P6-CAL-TEST-02), closing the one gap Phase 6 left open.
- **Phase 7 — 10-Day Owner-Only Soak** (`stage-11a-phase-7-plan.md`, [evidence](../evaluation/stage-11/owner-validation/phase-7/)): **CONDITIONAL PASS**, addressed by Phase 8. Ran 257.9 hours (10.75 days) — the project owner's own explicit duration, not §C's originally-envisioned 14–30 days (see `owner-validation-success-criteria.md`'s 2026-08-19 changelog). Directly observed and correctly handled the Google Testing-status 7-day refresh-token boundary with an independently-verified controlled reconnection. Two open items: GM-12's stale-follow-up evaluation never reached, and Google-side revocation not objectively confirmed at teardown.

Across Phases 4D–7, Phase B (dedicated test accounts) and Phase C (the soak period) — both "planning only" through Phase 4C — moved to full execution: two disposable test accounts were created and used exactly per §B's requirements (never the owner's personal account, no personal data, documented cleanup after every use), and the soak period (§C) ran to completion, with the two scope deviations noted above recorded honestly rather than reconciled silently.

## Phase 8 status (updated 2026-08-19)

**Phase 8 — Closing Phase 7's Open Items and the Stage 11A Exit Decision is complete: PASS.** See [stage-11a-phase-8-plan.md](stage-11a-phase-8-plan.md) and the evidence pack in [docs/evaluation/stage-11/owner-validation/phase-8/](../evaluation/stage-11/owner-validation/phase-8/). Revocation: closed — the owner independently found LifeFlow's access still genuinely active on Google's own permissions page (confirming Phase 7's uncertain result was a real failure) and removed it there directly. GM-12: explicitly deferred, not closed — a fresh trigger (`P8-FOLLOWUP-TEST-01`) is in flight, re-verifiable from 2026-08-23 onward, carried forward as a named condition rather than forced or silently dropped. No application code changed. `GOOGLE_PROVIDER_WRITES_ENABLED` stayed `false` throughout every live action this phase performed.

## Stage 11A Exit Decision (recorded 2026-08-19)

**CONDITIONAL READINESS.** See [owner-validation-exit-template.md](../evaluation/stage-11/owner-validation-exit-template.md) for the full decision record, rationale, and four named non-safety conditions (GM-12 re-verification, daily-brief-generation-under-real-load not measured during the soak, no formal §F owner-usability self-review conducted, §D's low-disk-space exercise never run). Zero unresolved P0/P1 across all 14 phase executions (1 through 8, including sub-phases). Every safety, privacy, duplicate/uncertain-write, cross-user-isolation, and deletion-path criterion in [owner-validation-success-criteria.md](../evaluation/stage-11/owner-validation-success-criteria.md) is met.

**This decision does not authorise recruitment.** [recruitment-authorisation-checklist.md](../evaluation/stage-11/recruitment-authorisation-checklist.md) remains **RECRUITMENT NOT AUTHORISED** — items 5–20 are untouched by anything in Stage 11A, exactly as this document's own "Relationship to the rest of Stage 11" section states. It does not begin Stage 12, which continues to depend on the fuller Stage 11 evidence base (human-participant evaluation, the dataset-v2 blind holdout/adversarial evaluation set, and the professional privacy-notice review — none of which are Stage 11A's scope).
