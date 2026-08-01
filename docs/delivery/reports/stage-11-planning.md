# Stage 11 Planning Gate Report — Evaluation and Pilot Readiness

**Status:** Planning complete; Stage 11 implementation not begun · **Date:** 2026-07-30

## Executive verdict

**PLANNING COMPLETE — SUBMITTED FOR REVIEW, NOT YET APPROVED FOR EXECUTION**

This report covers planning only: the evaluation design, hypotheses, thresholds, participant materials, data-governance plan, and decision templates for Stage 11's human-evaluation track. No participant session has been conducted, no product behaviour has changed, and no paid infrastructure has been provisioned.

## Scope

Stage 11 (Evaluation and Pilot Readiness) is the evidence gate between the technically complete, visually polished Stage 10 product and Stages 12–14 (packaging, production deployment, controlled pilot). This planning gate designs the **human-evaluation track** of Stage 11 in full, and cross-references — without re-planning — the two other tracks already scoped elsewhere: the holdout+adversarial technical evaluation ([ADR 0002](../../architecture/adr/0002-evaluation-targets.md)) and the professional privacy-notice review (stage-plan.md's External Setup table).

## What was delivered

| Document | Purpose |
|---|---|
| [docs/delivery/stage-11-plan.md](../stage-11-plan.md) | Stage 11 purpose, target-user hypothesis, evaluation design summary, cost policy, exit criteria |
| [docs/evaluation/stage-11/product-hypotheses.md](../../evaluation/stage-11/product-hypotheses.md) | 4 problem, 6 value, 6 usability, 8 safety hypotheses, each with evidence/task/metric/threshold/consequence |
| [docs/evaluation/stage-11/success-criteria.md](../../evaluation/stage-11/success-criteria.md) | Fixed measurable thresholds, set before any session |
| [docs/evaluation/stage-11/participant-information.md](../../evaluation/stage-11/participant-information.md) | Participant-facing information sheet template |
| [docs/evaluation/stage-11/consent-form.md](../../evaluation/stage-11/consent-form.md) | Consent form template |
| [docs/evaluation/stage-11/facilitator-guide.md](../../evaluation/stage-11/facilitator-guide.md) | Facilitator script and session-running procedure |
| [docs/evaluation/stage-11/task-protocol.md](../../evaluation/stage-11/task-protocol.md) | 20 scripted participant journeys, each mapped to hypotheses |
| [docs/evaluation/stage-11/observation-sheet.md](../../evaluation/stage-11/observation-sheet.md) | Per-task recording template |
| [docs/evaluation/stage-11/safety-questionnaire.md](../../evaluation/stage-11/safety-questionnaire.md) | Safety-comprehension questionnaire, critical items flagged |
| [docs/evaluation/stage-11/post-session-questionnaire.md](../../evaluation/stage-11/post-session-questionnaire.md) | Trust/usefulness ratings + SUS |
| [docs/evaluation/stage-11/issue-register-template.md](../../evaluation/stage-11/issue-register-template.md) | P0–P3 severity framework and register |
| [docs/evaluation/stage-11/data-governance.md](../../evaluation/stage-11/data-governance.md) | Full data-governance plan |
| [docs/evaluation/stage-11/findings-template.md](../../evaluation/stage-11/findings-template.md) | Analysis-report template |
| [docs/evaluation/stage-11/go-no-go-template.md](../../evaluation/stage-11/go-no-go-template.md) | GO / CONDITIONAL GO / NO-GO decision template |

## Documents updated

- [docs/delivery/stage-plan.md](../stage-plan.md) — added a note that human-evaluation planning is complete, without changing Stage 11's status (still "next, has not begun").
- [docs/delivery/assumptions-and-decisions.md](../assumptions-and-decisions.md) — new decision-log entry recording the two-round evaluation design decision.
- [docs/architecture/tree.md](../../architecture/tree.md) — added `docs/evaluation/` to the tree with an explicit "no participant data ever committed here" note.

## Documents deliberately not changed

- `README.md` — already correctly states "Stage 11 ... is next and has not begun"; no genuine status change occurred.
- `docs/delivery/metrics.md` — current stage (11) and approved-stage count (11/15) are unchanged by planning; regenerating would produce a byte-identical file, so it was left as-is rather than re-run for no effect.
- `CLAUDE.md` / `AGENTS.md` — current-stage statements remain accurate ("Stage 11 ... next, not yet started"); planning does not change this.

## Verification results

- `pre-commit run --all-files` — pass (see commit list below for the exact run associated with each commit).
- `gitleaks protect --staged` and full-history `gitleaks detect` — 0 leaks.
- `detect-secrets scan --baseline .secrets.baseline` — clean.
- `git diff --check` — clean (no whitespace errors).
- Internal-link spot check — every relative link added in the new documents resolves to a file that exists in this branch.
- Terminology consistency — P0/P1/P2/P3 definitions appear identically in `issue-register-template.md` and are referenced, not redefined, everywhere else; threshold numbers in `product-hypotheses.md` and `go-no-go-template.md` are sourced from `success-criteria.md`, not restated independently.
- Repository scan for committed participant data, real credentials, or infrastructure resources — none found; every evaluation document under `docs/evaluation/stage-11/` is a blank template, and `data-governance.md` explicitly states no participant data is ever committed to this repository.
- No `apps/api`, `apps/web`, `prompts/`, `migrations/`, or `infra/` file touched.

## Boundary confirmation

- Branch `stage-11-evaluation-planning` created from `main` at `267dc3518ae930ab468411e0a53088a3cd5d534e` (the roadmap-reconciliation merge commit).
- `stage-10-complete` tag unchanged throughout.
- No Stage 11 completion tag created.
- No participant recruitment, session, or product-behaviour change occurred.
- No paid cloud infrastructure was provisioned.

## Explicit exclusions

This planning gate does not: conduct any evaluation session; change any product behaviour; provision paid infrastructure; connect a real Gmail or Calendar account; begin Stage 12 work; or claim any ethics/institutional approval that has not actually been obtained (see `participant-information.md` and `data-governance.md`'s explicit flags on this point).

## Next authorised action

This plan is submitted for review. Running Round 1 of the evaluation, and any further Stage 11 work, requires separate explicit approval and is not authorised by this report.

## Addendum — Round 1 ethics and execution readiness (added 2026-07-30, after this report was originally written)

This report covered planning only. A follow-on readiness gate then prepared Round 1 for safe execution without authorising it: an evaluation-context decision gate (at that time UNDECIDED — the project owner had not yet selected university-linked research, independent product evaluation, or informal feedback), ethics/privacy enquiry packs for each possible category, a recruitment-authorisation checklist (currently RECRUITMENT NOT AUTHORISED), a participant screener, an operational runbook, a synthetic-scenario manifest with an automated validator, a desk-based protocol rehearsal that found and corrected five ordinary readiness defects, an evidence register, and a readiness decision (READY TO REQUEST RECRUITMENT AUTHORISATION — a materials-readiness statement, not an approval). See [docs/delivery/stage-11-plan.md](../stage-11-plan.md) §12 and the Stage 11 Round 1 Ethics and Execution Readiness Report for the full detail. Nothing in this report's original claims changes as a result — Stage 11 implementation, participant recruitment, and evaluation sessions had not begun when this report was written and still have not begun.

## Addendum — evaluation-context decision and Stage 11A (added 2026-07-30, after the Round 1 readiness addendum above)

The evaluation-context decision referenced as UNDECIDED above is now resolved: the current operational mode is **OWNER-ONLY INTERNAL VALIDATION** (the owner has completed their MSc and the project is not currently university-linked), and the future participant route, if activated, is **INDEPENDENT PRODUCT EVALUATION**, potentially supporting a future journal publication — recorded in [evaluation-context-decision.md](../../evaluation/stage-11/evaluation-context-decision.md), not claimed as an ethics approval or a recruitment authorisation. A **Stage 11A owner-only internal-validation programme** ([stage-11a-owner-validation-plan.md](../stage-11a-owner-validation-plan.md)) was planned to run in the interim: synthetic validation, planned (not executed) dedicated test accounts and a soak period, failure/recovery exercises, a security/privacy review, and an owner usability self-review explicitly separated from any future participant evidence. [recruitment-authorisation-checklist.md](../../evaluation/stage-11/recruitment-authorisation-checklist.md) items 1–4 are now satisfied but recruitment remains **NOT AUTHORISED** — items 5–20 are unchanged and are not silently satisfied by owner-only validation. Nothing in this report's original claims, or the Round 1 addendum above, changes as a result — no participant has been recruited, contacted, or evaluated.

## Addendum — Stage 11A Phase 1 execution (added 2026-07-31, after the two addenda above)

The Stage 11A programme planned above has now had its first phase executed: **Phase 1 — Synthetic Acceptance Validation is complete, decision PASS — READY FOR PHASE 2.** See [docs/delivery/stage-11a-phase-1-plan.md](../stage-11a-phase-1-plan.md) and the full evidence pack in [docs/evaluation/stage-11/owner-validation/phase-1/](../../evaluation/stage-11/owner-validation/phase-1/). This executed synthetic scenarios only, against the existing demo dataset and fixtures — no test-Google-account was created or connected, no soak period was started, and no participant was recruited, contacted, or evaluated. Nothing in this report's original claims, or either addendum above, changes as a result.

## Addendum — Stage 11A Phase 2 execution (added 2026-07-31, after Phase 1's addendum above)

Phase 2 — Controlled Failure and Recovery Validation is now also complete: **decision PASS — READY FOR PHASE 3.** See [docs/delivery/stage-11a-phase-2-plan.md](../stage-11a-phase-2-plan.md) and the full evidence pack in [docs/evaluation/stage-11/owner-validation/phase-2/](../../evaluation/stage-11/owner-validation/phase-2/). This exercised API/web/worker/scheduler restart, real PostgreSQL/Redis outage and recovery, provider-timeout and uncertain-write handling at required repetition counts, token-expiry/revoked-consent handling, cross-user isolation under failure, and two genuinely new local rehearsal tools (backup/restore, rollback) — all against local Docker services, the existing fake-Google test server, and synthetic data only. No test-Google-account was created or connected, no soak period was started, and no participant was recruited, contacted, or evaluated. Nothing in this report's original claims, or any addendum above, changes as a result.

## Addendum — Stage 11A Phase 3 execution (added 2026-07-31, after Phase 2's addendum above)

Phase 3 — Security, Privacy and Residual-Data Validation is now also complete: **decision PASS — READY FOR PHASE 4 READINESS GATE.** See [docs/delivery/stage-11a-phase-3-plan.md](../stage-11a-phase-3-plan.md) and the full evidence pack in [docs/evaluation/stage-11/owner-validation/phase-3/](../../evaluation/stage-11/owner-validation/phase-3/). This exercised owner-scoping under 6 resource families, session/authentication edge cases, a real OAuth-credential sentinel lifecycle search, an honest secret-rotation-capability rehearsal, an end-to-end log-privacy sentinel scan, browser-storage/console/network inspection, injection resistance, the four privacy operations at required repetition counts (5x/5x/10x/10x), a genuinely new backup-vs-deletion compliance rehearsal, and — for the first time in this project's history — dependency-vulnerability and container-hardening scans, which found and fixed two real security gaps (a loopback-only local-service-binding fix, and several Next.js/postcss/sharp CVEs). Zero product-code defects were found; one test-script defect (a leftover Redis key) was found and fixed. No test-Google-account was created or connected, no soak period was started, and no participant was recruited, contacted, or evaluated. Nothing in this report's original claims, or any addendum above, changes as a result.

## Addendum — Stage 11A Phase 3 decision correction (added 2026-07-31, same day, after the Phase 3 addendum above)

The Phase 3 decision recorded immediately above was an unqualified PASS. On review, this was a governance-classification error: two P2 findings from that same run (`TOKEN_KEY` rotation capability, `brace-expansion` dev-tooling exposure) remained open with an explicit closure condition rather than fixed, and the approved Phase 3 decision framework requires unresolved non-exploitable P2 conditions to produce a **CONDITIONAL PASS**, not an unqualified PASS. The decision has been corrected to **CONDITIONAL PASS — READY FOR PHASE 4 READINESS GATE** in [phase-3-decision.md](../../evaluation/stage-11/owner-validation/phase-3/phase-3-decision.md). This is not a failure and no acceptance-matrix row changed — all 44 rows still PASS and zero P0/P1 findings exist anywhere.

This correction also recorded a durable Phase 4 connection blocker: no Google test account may be connected until the project owner resolves the `TOKEN_KEY` rotation gap via a key-versioned migration or a disposable-account destructive rotation (or a formally reviewed replacement) — see the "TOKEN_KEY rotation — Phase 4 connection blocker" section of [phase-3-decision.md](../../evaluation/stage-11/owner-validation/phase-3/phase-3-decision.md). Separately, a same-day revalidation of the `brace-expansion` finding found `pnpm audit` now reports zero vulnerabilities against the unchanged lockfile, cross-checked directly against GitHub's advisory database; this is recorded as new evidence, not a unilateral closure, in [dependency-security-results.md](../../evaluation/stage-11/owner-validation/phase-3/dependency-security-results.md). This correction was carried on PR #12 alongside the original Phase 3 evidence; see the accompanying "Stage 11A Phase 3 Decision Correction and Merge Confirmation" report for the exact merge outcome. Phase 4 is not authorised by this correction; no test account was created or connected, no soak period was started, and no participant was recruited, contacted, or evaluated.

## Addendum — Stage 11A Phase 4A execution (added 2026-08-01, after the Phase 3 decision-correction addendum above)

Phase 4A — Key-Versioned Credential Encryption and Rotation is now also complete: **decision PASS — READY FOR PHASE 4B TEST-ACCOUNT READINESS.** See [docs/delivery/stage-11a-phase-4a-plan.md](../stage-11a-phase-4a-plan.md) and the full evidence pack in [docs/evaluation/stage-11/owner-validation/phase-4a/](../../evaluation/stage-11/owner-validation/phase-4a/). The project owner selected Path A (key-versioned migration) for the `TOKEN_KEY` blocker Phase 3 recorded; this phase built a `TokenKeyRing` (active + legacy keys, drop-in compatible with the existing cipher protocol), a context-bound (AAD) `v2` credential envelope that also closed a previously-undocumented cross-account/cross-field ciphertext-transplant gap, a resumable row-locked (`SELECT ... FOR UPDATE SKIP LOCKED`) migration service with no public route, an Alembic migration adding queryable key-version columns, and two new rehearsal scripts (an 18-step rotation lifecycle and a backup/key-ring-retirement rehearsal), each run 3/3 cycles clean twice. **F-P3-03 is now closed**, and **F-P3-04 (`brace-expansion`) was independently reassessed with fresh evidence and also closed** — no open P2/P3 condition remains from Phase 3. Full automated suite green (947 backend tests, up from 932; 90 frontend tests unaffected), zero unresolved P0/P1. One implementation-time defect (a context-derivation ordering bug that would have affected every brand-new OAuth connection) was found by this phase's own new tests and fixed before any commit — it never shipped and never affected a running deployment. No Google account was created or connected, no soak period was started, and no participant was recruited, contacted, or evaluated. Phase 4B (proposed: Dedicated Test-Account Readiness and Controlled Connection Gate) is not authorised by this decision.

## Addendum — Stage 11A Phase 4B execution (added 2026-08-01, after the Phase 4A addendum above)

Phase 4B — Dedicated Test-Account Readiness and Controlled Connection Gate is now also complete: **decision PASS — READY FOR OWNER CONNECTION AUTHORISATION.** See [docs/delivery/stage-11a-phase-4b-plan.md](../stage-11a-phase-4b-plan.md) and the full evidence pack in [docs/evaluation/stage-11/owner-validation/phase-4b/](../../evaluation/stage-11/owner-validation/phase-4b/). This phase is readiness and planning only: it created no Google account, no Google Cloud project, and no OAuth credential, and made no real Google API call. It verified current official Google requirements (dated 2026-08-01) — including a genuine, unresolved constraint that a Testing-status consent screen's refresh tokens expire after 7 days, meaning the future soak period needs an explicit owner decision (re-consent cadence vs. production publishing) before it begins; derived and structurally proved the exact minimum OAuth scope set; designed (without creating) a disposable two-account test-account model and dedicated Google Cloud project; closed 9 test-coverage gaps found by inspecting the actual OAuth-callback and production-startup code (every underlying guard already worked correctly — only regression coverage was missing); built a new pre-connection gate and a broader preconnection-readiness command; and ran an 18-step connection rehearsal 3/3 clean against only the existing fake-provider infrastructure, which itself caught and fixed two rehearsal-script defects — including a real, tooling-only network call to Google's live API — before ever being reported as passing. Full automated suite green (964 backend tests, up from 953; 90 frontend tests; 42 E2E journeys; 5 eval modes), zero unresolved P0/P1. No Google account was created or connected, no soak period was started, and no participant was recruited, contacted, or evaluated. This decision allows the project owner to consider **AUTHORISE CREATION OF THE DISPOSABLE GOOGLE TEST ENVIRONMENT**, and, separately and later, the connection and provider-write authorisations in [provider-write-authorisation-gate.md](../../evaluation/stage-11/owner-validation/phase-4b/provider-write-authorisation-gate.md).
