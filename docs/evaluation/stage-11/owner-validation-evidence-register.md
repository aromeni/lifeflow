# Stage 11A — Owner-Validation Evidence Register

**Status:** Planning document, no evidence yet exists — execution has not begun · **Date:** 2026-07-30

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

## Register status

No row above has any evidence yet — Stage 11A execution has not begun as of this document's creation.
