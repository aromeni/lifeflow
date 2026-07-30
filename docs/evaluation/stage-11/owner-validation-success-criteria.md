# Stage 11A — Owner-Validation Success Criteria

**Status:** Planning document, thresholds fixed before Stage 11A execution begins · **Date:** 2026-07-30

Companion: [stage-11a-owner-validation-plan.md](../../delivery/stage-11a-owner-validation-plan.md) · [owner-validation-evidence-register.md](owner-validation-evidence-register.md) · [owner-validation-exit-template.md](owner-validation-exit-template.md)

Thresholds below apply to Stage 11A (owner-only internal validation) and are distinct from — and a precondition for — the participant-facing thresholds in [success-criteria.md](success-criteria.md). They are not weakened after observing results merely to declare readiness; any revision requires a written, dated rationale in this file's changelog.

## Measurable thresholds

| Dimension | Metric | Threshold | Pass | Failure | Remediation consequence |
|---|---|---|---|---|---|
| Automated suites | `./scripts/e2e.sh`, `./scripts/e2e-resilience.sh`, `./scripts/e2e-design.sh`, `uv run pytest`, `pnpm web:test` | All green | All pass | Any failure | Fix and re-run before continuing; failure blocks Stage 11A exit |
| Open defects | P0/P1 count in the owner-validation issue log | 0 unresolved | 0 | ≥ 1 unresolved | Fix, add regression coverage, re-verify before exit |
| Gmail send capability | Code-path audit + manual confirmation | 0 — no send capability exists | Confirmed absent | Any send path found | P0; blocks exit; matches the MVP's hard prohibition (`docs/product/mvp-scope.md`) |
| Calendar edit/delete capability | Code-path audit + manual confirmation | 0 — only new-event creation exists | Confirmed absent | Any edit/delete path found | P0; blocks exit |
| Duplicate provider writes under repeated failure | Failure/recovery exercises (§D) | 0 duplicates across all repeated-failure runs | 0 | ≥ 1 duplicate | P0; blocks exit; idempotency-key logic must be fixed and regression-tested |
| Automatic uncertain-write retries | Uncertain-execution fixture + manual test-account exercise | 0 automatic retries | 0 | ≥ 1 automatic retry | P0; blocks exit |
| Synthetic reset reliability | Repeated demo-environment resets | 100% across repeated runs | 100% | < 100% | Fix reset mechanism before relying on it for any further validation |
| Service-interruption recovery | Each exercise in §D | Successful recovery after every defined interruption | All recover | Any fails to recover | Fix and re-test the specific failure mode |
| Cross-user data exposure | Manual + automated isolation review (§E) | 0 exposures | 0 | ≥ 1 exposure | P0; blocks exit |
| Imported-data deletion | Manual inspection after deletion | Successful, no residual data | Confirmed | Residual data found | P0; blocks exit |
| Inferred-memory deletion | Manual inspection after deletion | Successful, no residual data | Confirmed | Residual data found | P0; blocks exit |
| Account anonymisation/deletion | Manual inspection after deletion | Successful, no residual identifiable data | Confirmed | Residual data found | P0; blocks exit |
| Private content in logs/metrics/Redis keys | Manual inspection (§E) | 0 instances | 0 | ≥ 1 instance | P0; blocks exit; matches threat-model redaction requirement |
| Secrets detected | `detect-secrets`, `gitleaks` | 0 | 0 | ≥ 1 | Fix immediately; treat as a security incident per `docs/security/threat-model.md` |
| Unexplained database records after cleanup | Manual inspection after each test-account/soak exercise | 0 | 0 | ≥ 1 | Investigate and fix before further use of that test account |
| Daily brief generation stability | Soak-period measurement (§C) | Stable generation across the full soak period, no unexplained failures | Stable | Unexplained failures | Investigate root cause; may require extending the soak period after a fix |
| Owner friction | [owner-observation-template.md](owner-observation-template.md) entries | Documented with remediation or explicit, reasoned acceptance | Documented | Undocumented | Every friction entry must reach a stated resolution or acceptance before exit |
| Participant-facing P0/P1 risk | Cross-check against [product-hypotheses.md](product-hypotheses.md) safety hypotheses | 0 unresolved before recruitment is even considered | 0 | ≥ 1 | Blocks not just Stage 11A exit but any future move toward recruitment |

## Threshold consistency

These thresholds are specific to owner-only validation and do not replace or lower any threshold in [success-criteria.md](success-criteria.md) (the participant-facing set). A defect found here that also implicates a participant-facing hypothesis (e.g., a safety-comprehension risk) must be fixed here first — Stage 11A exists precisely so participants are never the first to find it.

## Changelog

- 2026-07-30 — Initial owner-validation thresholds set during Stage 11A planning, before execution begins. No revisions yet.
