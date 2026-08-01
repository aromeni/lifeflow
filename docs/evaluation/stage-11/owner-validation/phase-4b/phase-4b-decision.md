# Stage 11A Phase 4B — Decision

**Status:** Decision recorded · **Date:** 2026-08-01

Companion: [acceptance-matrix.md](acceptance-matrix.md) · [defect-register.md](defect-register.md) · [dry-run-results.md](dry-run-results.md) · [manual-walkthrough.md](manual-walkthrough.md)

## Decision

**PASS — READY FOR OWNER CONNECTION AUTHORISATION**

## Criteria checked

- [x] **Every mandatory acceptance row verified** — all 60 rows in [acceptance-matrix.md](acceptance-matrix.md) checked by automated test, inspection, or scripted dry run; no P0-class row failed.
- [x] **Current official Google requirements documented** — [google-platform-requirements.md](google-platform-requirements.md), dated and sourced 2026-08-01, including the honestly-recorded Testing-status 7-day refresh-token/100-test-user constraints and Gmail-restricted/Calendar-sensitive scope classifications.
- [x] **Exact minimum OAuth scopes approved** — [oauth-scope-matrix.md](oauth-scope-matrix.md), all four scopes traced to an implemented, tested product operation; no speculative scope.
- [x] **Test-account design complete** — [test-account-specification.md](test-account-specification.md), two disposable accounts, neither created.
- [x] **Google Cloud project plan complete** — [google-cloud-project-plan.md](google-cloud-project-plan.md), no project created.
- [x] **Redirect URI and origin plan complete** — [redirect-uri-and-origin-plan.md](redirect-uri-and-origin-plan.md), verified against the actual implementation.
- [x] **OAuth state/account binding verified** — [oauth-state-and-binding-results.md](oauth-state-and-binding-results.md), 6 new regression tests closing coverage gaps found this phase; zero cross-owner binding defects found.
- [x] **Credential connection gate clear** — [credential-preconnection-results.md](credential-preconnection-results.md), 3/3 clean runs, `clear_to_connect=true`, zero stored credentials.
- [x] **Active v2 key configuration verified** — unchanged from Phase 4A, re-confirmed via the preconnection readiness command.
- [x] **Synthetic Gmail and Calendar datasets defined** — [synthetic-gmail-dataset-plan.md](synthetic-gmail-dataset-plan.md) (18 scenarios), [synthetic-calendar-dataset-plan.md](synthetic-calendar-dataset-plan.md) (12 scenarios); none created.
- [x] **Emergency-stop plan complete** — [emergency-stop-plan.md](emergency-stop-plan.md), all 19 required conditions.
- [x] **Revocation and cleanup plan complete** — [test-account-cleanup-plan.md](test-account-cleanup-plan.md).
- [x] **Three dry runs pass** — [dry-run-results.md](dry-run-results.md), 3/3 cycles, including 2 test-script defects found and fixed before being reported as passing.
- [x] **Preconnection readiness command passes** — [preconnection-readiness-results.md](preconnection-readiness-results.md), all 11 checks pass against current local state.
- [x] **No unresolved P0/P1** — [defect-register.md](defect-register.md): 0 P0, 0 P1; 3 P2 findings found and fixed this phase; 2 P2 findings recorded with explicit non-blocking closure conditions.
- [x] **All required CI checks green** — see the final report's required-check results.
- [x] **No-live-network guard in place** — [dry-run-results.md](dry-run-results.md)'s "No-live-network guard" section, `test_stage11a_phase4b_no_live_network_guard.py` (12/12), added during this phase's boundary correction after the exact-boundary classification below was recorded.
- [x] **Exact-boundary classification of the accidental outbound attempt recorded** — [dry-run-results.md](dry-run-results.md), reconciling this document's own accurate defect entry with the unqualified "no real Google API call" phrasing that previously appeared elsewhere in the evidence pack and cross-cutting docs.
- [x] **Soak-period decision framed, not made** — [soak-period-decision.md](soak-period-decision.md), Option A (Testing re-authorisation cadence) vs. Option B (reviewed publishing-status change), neither chosen.

## What this decision does not do

This decision does **not** create or connect a Google account, create a Google Cloud project, configure live OAuth credentials, begin OAuth, call Google, or start the soak period. It does not authorise Decision 1 or Decision 2 in [provider-write-authorisation-gate.md](provider-write-authorisation-gate.md) — those remain the project owner's own, separate, future decisions. Stage 12 remains unstarted. No Stage 11/11A completion tag is created by this decision.

## Decided by

This task's execution (Stage 11A Phase 4B dedicated test-account readiness). Authority to authorise creation of the disposable Google test environment, and subsequently Decisions 1 and 2, rests with the project owner.

## Date

2026-08-01
