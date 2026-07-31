# Stage 11A Phase 3 Plan — Security, Privacy and Residual-Data Validation

**Status:** Complete — CONDITIONAL PASS — READY FOR PHASE 4 READINESS GATE (see [phase-3-decision.md](../evaluation/stage-11/owner-validation/phase-3/phase-3-decision.md)) · **Date:** 2026-07-31

Companion: [stage-11a-owner-validation-plan.md](stage-11a-owner-validation-plan.md) · [stage-11a-phase-2-plan.md](stage-11a-phase-2-plan.md) · [docs/security/threat-model.md](../security/threat-model.md) · [docs/evaluation/stage-11/owner-validation/phase-3/](../evaluation/stage-11/owner-validation/phase-3/)

## Objective

Inspect every place LifeFlow may store, expose, transmit, cache, log, render, back up or retain information, and prove that the resulting data footprint is owner-scoped, minimised, privacy-safe and justified. Where Phase 1 proved the happy path is safe and Phase 2 proved failure/recovery never duplicates a side effect, Phase 3 proves the data itself — at rest, in motion, and after deletion — never exceeds what is justified and never crosses an owner boundary.

## Scope

Owner-only, synthetic-data-only inspection and testing of: database owner-scoping, session/authentication security, OAuth credential handling, secret rotation capability, log privacy, metrics privacy, Redis residual data, browser-side storage, API response minimisation, input/injection resistance, action-proposal tamper resistance, rate-limit privacy, the four privacy operations (disconnect, imported-data deletion, inferred-preference deletion, account deletion) at required repetition counts, residual-data analysis, backup-vs-deletion interaction, account-deletion tombstones, generated artefacts, dependency/container security posture, test-control isolation, and repository secret hygiene.

## Exclusions

No real or dedicated-test Google account is created or connected. No personal Gmail/Calendar data is used. No participant is recruited, contacted, or evaluated. The 14–30 day soak period does not start. No paid infrastructure is provisioned. No production deployment occurs. Stage 12 is not started. No Stage 11 or Stage 11A completion tag is created. This phase does not merge, tag, or begin Phase 4.

## Method note: reuse before rebuild

A dedicated codebase audit (mirroring Phase 2's approach) found the large majority of Phase 3's required controls already correctly implemented and tested across Stages 7–9: encrypted OAuth credentials (`AesGcmTokenCipher`), owner-scoped repositories with a cascading `user_id` FK on every user-owned table (`test_ownership.py`), the closed `FailureCode`/metrics-label vocabularies (T31), the rate limiter's HMAC-pseudonymised Redis subjects, the deletion engine's content-free tombstones and audit trail, action-proposal tamper resistance (`test_action_policy_tamper.py`), and the fake-Google server's production-refusal guard (ADR 0005 D92). This phase's real contribution is: (1) re-verifying that evidence fresh, (2) extending automated coverage to the specific gaps the audit found — a consolidated API-level IDOR test across every proposal/execution/audit/deletion/preference/scheduled-brief route, two missing session-security edge cases, an end-to-end log-privacy sentinel capture, a dedicated injection-resistance test file, repetition counts for the four privacy operations that no prior test met (5x/5x/10x/10x), and a genuinely new backup-vs-deletion validation — and (3) building the two pieces of infrastructure this project had never attempted: a secret-rotation rehearsal and a dependency/container security review.

## Security and privacy assumptions

- All connector content remains untrusted data (§11.1 of the threat model); Phase 3 does not change the prompt-injection boundary, only exercises classic web-injection vectors (XSS/SQLi-shaped strings) against it.
- The rate limiter is defence-in-depth, not the source of correctness (fail-open is by design, ADR 0005 D64).
- A circuit breaker was evaluated and deliberately not built (ADR 0005 D85); Phase 3 does not revisit that decision.
- Encryption-at-rest key rotation was documented as "manual procedure in MVP, automated rotation post-MVP" (threat model §"Encryption and key management assumptions"); Phase 3 rehearses what the manual procedure actually requires and records what remains a genuine gap, rather than pretending a capability exists.

## Data-surface inventory

See [data-flow-inventory.md](../evaluation/stage-11/owner-validation/phase-3/data-flow-inventory.md) for the full per-data-type trace and [storage-surface-inventory.md](../evaluation/stage-11/owner-validation/phase-3/storage-surface-inventory.md) for the per-storage-layer inventory (PostgreSQL, Redis, browser, process/filesystem).

## Threat categories

Extends the existing closed threat-model table (T1–T31) — Phase 3 does not introduce new threat IDs, it exercises and extends evidence for T1, T2, T6, T7, T8, T10, T12, T13, T15, T16, T18, T19, T21, T24, T31, plus the untracked areas the audit found open: secret-rotation capability, dependency/container hardening, and backup-vs-deletion interaction (extensions of T1/T15/T16).

## Inspection methods

Direct database inspection (`psql`/SQLAlchemy against the isolated dev/test databases), direct Redis inspection (`redis-cli --scan`/`GET`), automated pytest integration tests against real PostgreSQL and Redis, a dedicated owner-operated Playwright privacy walkthrough inspecting browser storage/console/network, `pip-audit`/`pnpm audit` run once against the current lockfiles, manual review of `docker-compose.yml`, and the existing repository-privacy tooling (`detect-secrets`, Gitleaks staged + full-history, private-key detection).

## Scenario inventory

See [acceptance-matrix.md](../evaluation/stage-11/owner-validation/phase-3/acceptance-matrix.md) for the full numbered `S11A-P3-001`–`NNN` inventory.

## Repetition requirements

Per the governing task: owner-scoping attacks 5 per resource family; session tampering/replay 10 attempts; token sentinel search 5 lifecycle cycles; log sentinel scans 5 full workflow runs; Redis residual inspection 5 reset/workflow/deletion cycles; browser cleanup inspection 5 sessions; imported-data deletion 5 cycles; inferred-preference deletion 5 cycles; full account deletion 10 cycles; uncertain execution followed by account deletion 10 cycles; secret/test-control production rejection each control at least once; backup-retention/deletion rehearsal 3 complete cycles; cross-user deletion isolation 5 cycles. Where an existing test already satisfies a count, it is re-run fresh and cited rather than duplicated; where no test meets the count, new parametrized coverage is added following the precedent `test_stage11a_phase2_uncertain_write_repeatability.py` established in Phase 2.

## Severity rules (P0–P3)

As specified by the governing task, unchanged from Phase 2's framework with Phase-3-specific P0/P1 examples (cross-user exposure, plaintext credential exposure, production-accessible test bypass, unauthorised external action, deletion affecting another owner, committed secret = P0; retained sensitive content without justification, sessions usable after deletion, credentials usable after disconnect, unsafe browser storage, incomplete owner scoping, backups able to contact real providers = P1). No unresolved P0/P1 is permitted; thresholds are not lowered after observing findings.

## Remediation rules

Ordinary defects are fixed before being reported, per the engineering acceptance contract. A P0 finding in any of the six categories named by the governing task (cross-user exposure, credential/token exposure, unauthorised external action, deletion failure affecting another owner, production-accessible test control, secret committed to Git) stops closure immediately for owner escalation rather than being silently fixed and folded into the evidence pack as if routine.

## Evidence rules

Every acceptance-matrix row cites either "Existing evidence, re-run" with the exact file, or "New" with the file created this phase. No raw logs, databases, backups, Redis dumps, browser traces, HAR files, Playwright reports, test-results directories, credentials, tokens, session cookies, unredacted screenshots, or absolute local paths are committed.

## Residual-data decision rules

Every row surviving a deletion path in [deletion-residual-analysis.md](../evaluation/stage-11/owner-validation/phase-3/deletion-residual-analysis.md) is classified REQUIRED RESIDUAL, TEMPORARY RESIDUAL, UNJUSTIFIED RESIDUAL, or DEFECT. No item may remain classified only as "miscellaneous" or "internal." An UNJUSTIFIED RESIDUAL that is content-bearing is either removed this phase or recorded as a blocking finding.

## Exit criteria

See [phase-3-decision.md](../evaluation/stage-11/owner-validation/phase-3/phase-3-decision.md) for the applied decision. PASS — READY FOR PHASE 4 READINESS GATE requires every criterion in governing-task §31; CONDITIONAL PASS is reserved for explicit, non-exploitable, deadline-bound P2 conditions; FAIL — NOT READY is required for any of the listed disqualifying conditions. A Phase 3 PASS does not itself create or connect a test account, start the soak period, or authorise recruitment — Phase 4 (proposed: Dedicated Test-Account Readiness and Controlled Connection Gate) requires its own separate approval.
