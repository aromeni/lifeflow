# Stage 11A — Owner-Validation Evidence Register

**Status:** Execution complete through Phase 8; Stage 11A exit decision recorded · **Date:** 2026-08-19 (originally 2026-07-30)

Companion: [stage-11a-owner-validation-plan.md](../../delivery/stage-11a-owner-validation-plan.md) · [owner-validation-success-criteria.md](owner-validation-success-criteria.md) · [owner-observation-template.md](owner-observation-template.md)

## Permissible evidence

| Evidence type | Notes |
|---|---|
| Automated-test results | `pytest`, Playwright suite output, CI run logs |
| Synthetic scenario results | Manual walkthrough outcomes against `synthetic-scenario-manifest.md` |
| Test-account identifiers | Stored outside Git (see Prohibited content below) — only a non-identifying label may ever appear here (e.g., "test account A"), never the credential or the account email itself |
| Service recovery records | Outcome of each §D failure/recovery exercise |
| Backup/restore results | Local/test-environment only |
| Security-scan summaries | `gitleaks`, `detect-secrets`, dependency-scan output — summaries and pass/fail status, not raw scan dumps that might contain matched secret fragments |
| Anonymised screenshots containing synthetic data | Must contain only fictional demo-dataset content; never a real test-account inbox even if fictional messages were sent through it |
| Owner observation log | Per [owner-observation-template.md](owner-observation-template.md), labelled `OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE` |
| Issue-register entries | Following the same P0–P3 framework as [issue-register-template.md](issue-register-template.md) |
| Remediation commits | Normal commits fixing anything Stage 11A finds |
| Soak-period summary | Aggregated stability metrics from §C, no raw account content |
| Final readiness decision | [owner-validation-exit-template.md](owner-validation-exit-template.md), filled in |

## Prohibited repository content

None of the following may ever be committed to this repository, at any point in Stage 11A:

- real credentials of any kind;
- OAuth tokens (test-account or otherwise);
- personal inbox content;
- personal Calendar content;
- third-party confidential information;
- raw database dumps;
- Redis dumps;
- runtime logs containing private content;
- unredacted screenshots (i.e., screenshots not confirmed to contain only synthetic content);
- participant data (Stage 11A has no participants, but this rule is stated here too since Stage 11A materials sit alongside the participant-track materials in the same directory);
- signed forms;
- recordings;
- transcripts.

## Storage

Test-account credentials and any raw evidence containing account-specific detail (even synthetic) are stored outside this Git repository, in a location the owner controls — the same principle as [data-governance.md](data-governance.md)'s rule for participant data, applied here to test-account material.

## Register entries (filled in 2026-08-19, after Phase 8)

| Phase | Evidence pack | Decision |
|---|---|---|
| 1 — Synthetic Acceptance Validation | [phase-1/](owner-validation/phase-1/) | PASS |
| 2 — Controlled Failure and Recovery | [phase-2/](owner-validation/phase-2/) | PASS |
| 3 — Security, Privacy, Residual-Data | [phase-3/](owner-validation/phase-3/) | CONDITIONAL PASS (closed by Phase 4A) |
| 4A — Key-Versioned Credential Encryption | [phase-4a/](owner-validation/phase-4a/) | PASS |
| 4B — Test-Account Readiness | [phase-4b/](owner-validation/phase-4b/) | PASS |
| 4C — Disposable Google Test Environment | [phase-4c/](owner-validation/phase-4c/) | PASS |
| 4D — First Real OAuth Connection | [phase-4d/](owner-validation/phase-4d/) | PASS |
| 5 — Synthetic Dataset Population | [phase-5/](owner-validation/phase-5/) | PASS |
| 6 — First Real Ingestion and Gmail Draft | [phase-6/](owner-validation/phase-6/) | CONDITIONAL PASS (closed by Phase 6A) |
| 6A — Split OAuth Flags | [phase-6a/](owner-validation/phase-6a/) | PASS |
| 6A.1 — Frontend Flag Alignment | [phase-6a1/](owner-validation/phase-6a1/) | PASS |
| 6B — First Real Calendar Insertion | [phase-6b/](owner-validation/phase-6b/) | PASS |
| 7 — 10-Day Owner-Only Soak | [phase-7/](owner-validation/phase-7/) | CONDITIONAL PASS (two items addressed by Phase 8) |
| 8 — Closure and Stage 11A Exit | [phase-8/](owner-validation/phase-8/) | PASS |
| 9 — GM-12 Fresh-Trigger Follow-Up | [phase-9/](owner-validation/phase-9/) | PASS (closes one of Phase 8's four exit conditions) |
| 10 — Closing the Remaining Three Exit Conditions | [phase-10/](owner-validation/phase-10/) | PASS (closes the remaining three of Phase 8's four exit conditions) |

Automated-suite results, security-scan summaries, and failure/recovery
outcomes are recorded within each phase's own evidence pack rather than
duplicated here, per the "Permissible evidence" table above. No prohibited
content (real credentials, tokens, personal content, raw dumps) was
committed at any point — every phase's evidence hygiene was independently
scanned before that phase's PR was opened.

## Register status

Execution ran from 2026-07-31 (Phase 1) through 2026-08-19 (Phase 8). The
Stage 11A exit decision is recorded in
[owner-validation-exit-template.md](owner-validation-exit-template.md).
