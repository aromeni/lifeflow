# Stage 11A Phase 4B — Dedicated Test-Account Readiness and Controlled Connection Gate

**Status:** In execution · **Date:** 2026-08-01

Companion: [docs/evaluation/stage-11/owner-validation/phase-4b/](../evaluation/stage-11/owner-validation/phase-4b/) · [stage-11a-phase-4a-plan.md](stage-11a-phase-4a-plan.md) · [engineering-acceptance-contract.md](engineering-acceptance-contract.md)

## Objective

Prove that the project, procedures, account design, OAuth configuration, scope selection, synthetic test data, safety controls, emergency-stop processes, and cleanup procedures are ready for a tightly controlled first connection to disposable Google test accounts. This phase is readiness and planning only.

## Scope

- Inspecting and documenting the actual, already-implemented OAuth/Gmail/Calendar code paths against current official Google requirements.
- Designing (not creating) a disposable two-account test-account model and a dedicated Google Cloud project model.
- Deriving the minimum OAuth scope set from implemented product operations, with evidence the implementation cannot exceed the product's closed action model.
- Reviewing and closing gaps in OAuth state/callback security test coverage.
- Verifying and hardening the Phase 4A credential connection gate as the mandatory pre-connection check.
- Designing synthetic Gmail/Calendar datasets, a first-connection runbook, a two-decision authorisation gate (connect vs. write), an emergency-stop plan, and a cleanup/revocation plan.
- Building a content-free preconnection readiness command.
- Three scripted dry runs of the full lifecycle using only the existing fake-provider/synthetic infrastructure — no real Google call.
- A full evidence pack and a Phase 4B decision.

## Exclusions

This phase does not authorise and must not perform: creating a Google account or Google Cloud project; configuring live OAuth credentials; completing OAuth consent; connecting Gmail or Calendar; storing a Google OAuth token; calling a real Google API; creating a Gmail draft or Calendar event through Google; the 14–30 day soak period; participant recruitment, contact, or evaluation; paid infrastructure; production deployment; Stage 12 work; a Stage 11 or Stage 11A completion tag.

## Prerequisites

- Stage 11A Phases 1–3 complete (PASS / PASS / historical CONDITIONAL PASS).
- F-P3-03 and F-P3-04 CLOSED.
- Stage 11A Phase 4A complete: PASS, merged to `main` at `ad484ce9df573182606a903f9025cd7d8cb363b0`.
- The Phase 4A credential connection gate reporting `clear_to_connect=true` against current local state.

## Account model

Exactly two disposable, owner-controlled Google accounts, never the owner's personal/business/academic/client accounts: **Account A** (primary — connects to LifeFlow, owns synthetic Gmail/Calendar content and any created drafts/events) and **Account B** (synthetic correspondent/attendee only, never connected to LifeFlow). See [test-account-specification.md](../evaluation/stage-11/owner-validation/phase-4b/test-account-specification.md).

## Google Cloud and OAuth readiness model

A single dedicated, unbilled Google Cloud project used only for this testing programme, kept on OAuth consent-screen **Testing** publishing status throughout Phase 4B and the eventual soak period (see [google-cloud-project-plan.md](../evaluation/stage-11/owner-validation/phase-4b/google-cloud-project-plan.md) for the honest 7-day-refresh-token / 100-test-user consequences of that status, which this phase documents but does not resolve).

## Scope-selection principles

Every requested scope must map to an implemented, approved LifeFlow operation; no scope is requested for future or speculative use. See [oauth-scope-matrix.md](../evaluation/stage-11/owner-validation/phase-4b/oauth-scope-matrix.md).

## Redirect-URI model

Server-controlled, fixed configuration values only (`GOOGLE_OIDC_REDIRECT_URI`, `GOOGLE_CONNECTOR_REDIRECT_URI`); never accepted from a client request. See [redirect-uri-and-origin-plan.md](../evaluation/stage-11/owner-validation/phase-4b/redirect-uri-and-origin-plan.md).

## Test-user model

Account A and Account B are added as OAuth consent-screen test users on the dedicated project; no other Google account may be added.

## Synthetic-data model

Fictional Gmail and Calendar content only, defined in [synthetic-gmail-dataset-plan.md](../evaluation/stage-11/owner-validation/phase-4b/synthetic-gmail-dataset-plan.md) and [synthetic-calendar-dataset-plan.md](../evaluation/stage-11/owner-validation/phase-4b/synthetic-calendar-dataset-plan.md); not created during this phase.

## Credential-storage gate

The Phase 4A `credential_connection_gate()` / `rotate_credential_keys.py --connection-gate` is the mandatory automated pre-connection check; extended in this phase with a preconnection readiness command covering the broader set of prerequisites in [preconnection-readiness-results.md](../evaluation/stage-11/owner-validation/phase-4b/preconnection-readiness-results.md).

## First-connection procedure

The exact 28-step controlled sequence in [first-connection-runbook.md](../evaluation/stage-11/owner-validation/phase-4b/first-connection-runbook.md), gated behind two separate owner decisions defined in [provider-write-authorisation-gate.md](../evaluation/stage-11/owner-validation/phase-4b/provider-write-authorisation-gate.md).

## Emergency-stop conditions

18 conditions with detection/action/evidence/severity in [emergency-stop-plan.md](../evaluation/stage-11/owner-validation/phase-4b/emergency-stop-plan.md).

## Cleanup and revocation procedure

[test-account-cleanup-plan.md](../evaluation/stage-11/owner-validation/phase-4b/test-account-cleanup-plan.md).

## Evidence requirements

See [evidence-handling-plan.md](../evaluation/stage-11/owner-validation/phase-4b/evidence-handling-plan.md) for permitted/prohibited evidence categories.

## Severity rules

The approved P0–P3 framework (see acceptance-matrix.md and defect-register.md); no connection-readiness requirement may be lowered to obtain PASS.

## Readiness decision

Exactly one of PASS — READY FOR OWNER CONNECTION AUTHORISATION / CONDITIONAL PASS / FAIL — GOOGLE CONNECTION REMAINS BLOCKED, recorded in [phase-4b-decision.md](../evaluation/stage-11/owner-validation/phase-4b/phase-4b-decision.md).

## Explicit owner-authorisation requirement

A PASS or CONDITIONAL PASS decision from this phase does not create or connect any account. It only allows the project owner to consider the next explicit decision: **AUTHORISE CREATION OF THE DISPOSABLE GOOGLE TEST ENVIRONMENT**. That decision, and the two further decisions in `provider-write-authorisation-gate.md` (connection authorisation, write authorisation), remain the project owner's alone.
