# Stage 11A Phase 6A — Separate Google Sign-In and Connector-Consent Enablement

**Status:** Complete · **Date:** 2026-08-05

Governed by [engineering-acceptance-contract.md](engineering-acceptance-contract.md). Follows Phase 6 (`CONDITIONAL PASS`) and the project owner's authorisation: **AUTHORISE THE SHARED-INITIATION-FLAG ARCHITECTURAL FIX**.

## Objective

Separate Google OIDC sign-in enablement from Google connector-consent enablement into two independent, fail-closed configuration controls, closing the real gap D-6-02 (`docs/evaluation/stage-11/owner-validation/phase-6/defect-register.md`) identified: enabling one flow for an authorised purpose necessarily armed the other.

## Root cause (not operator error)

`require_google_oauth_initiation` (`oauth_initiation.py`) was one function, backed by one flag (`google_oauth_initiation_enabled`), called by both the OIDC sign-in routes (`auth.py`) and the connector-consent routes (`connected_accounts.py`). This is a structural coupling: there was no way to authorise one flow without the flag also authorising the other, regardless of how carefully an operator used it. The real Phase 6 incident is exactly this design working as built, not a misuse of it.

Checked directly before any edit: OAuth *state* isolation (`oauth_state.py`'s `purpose` field, checked in `consume_oauth_flow`) already made cross-flow state substitution structurally impossible — this was true before Phase 6A and is unchanged by it. The actual, sole defect was at the initiation-gating layer.

## What changed

- `config.py`: `google_oauth_initiation_enabled` removed outright (no backward-compatible fallback) and replaced with `google_oidc_signin_enabled` and `google_connector_oauth_enabled`, both default `false`.
- `oauth_initiation.py`: one shared guard replaced with two, `require_google_oidc_signin` and `require_google_connector_oauth`, each checking only its own flag (plus the unchanged `google_oauth_enabled` master prerequisite).
- `auth.py` / `connected_accounts.py`: each now calls only its own guard, at both its initiation and callback routes.
- `main.py`: startup validation now rejects either new flag being enabled without the master `google_oauth_enabled`, mirroring the original single check.
- `scripts/preconnection_readiness_check.py`: reports four distinct states (`GOOGLE_PROVIDER_CONFIGURED`, `GOOGLE_OIDC_SIGNIN_ENABLED`, `GOOGLE_CONNECTOR_OAUTH_ENABLED`, `GOOGLE_PROVIDER_WRITES_ENABLED`) instead of one combined check.
- Both connection-rehearsal scripts and every affected test file updated to the new flag names.

## What did not change

- PKCE, state generation/consumption, owner/session binding, redirect matching, token security, and the master `google_oauth_enabled` configuration-completeness check — all unchanged, all reconfirmed working.
- No new frontend capability-exposure API — the "Sign in with Google"/"Connect Google" buttons remain static links; the route itself remains the sole enforcement point, exactly as before this phase (a scope-discipline choice, not an oversight — see `existing-coupling-analysis.md`).
- No real Google account was reconnected, no OAuth flow was initiated, no credential was stored, and no ingestion or provider write occurred at any point in this phase.

## Evidence pack

See [docs/evaluation/stage-11/owner-validation/phase-6a/](../evaluation/stage-11/owner-validation/phase-6a/), especially [phase-6a-decision.md](../evaluation/stage-11/owner-validation/phase-6a/phase-6a-decision.md).

## Exit decision

See the evidence pack's decision record. A PASS here does not itself authorise a corrected Calendar-write trigger attempt, GM-12's deferred evaluation, the soak period, or recruitment — each remains separately gated.
