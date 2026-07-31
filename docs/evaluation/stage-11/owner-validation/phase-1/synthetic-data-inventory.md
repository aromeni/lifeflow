# Stage 11A Phase 1 — Synthetic Data Inventory

**Status:** Complete · **Date:** 2026-07-31

Companion: [../../synthetic-scenario-manifest.md](../../synthetic-scenario-manifest.md) (the Round 1 manifest this phase reuses) · `apps/api/tests/test_stage11a_phase1_reset_repeatability.py`

## Fictional-data confirmation

Every email sender/recipient domain in the demo dataset (`apps/api/src/lifeflow_api/demo/data/v1/emails.json`) resolves to the IANA-reserved `.example` TLD or `lifeflow.local` (the demo user). This was already validated by `apps/api/tests/test_stage11_evaluation_readiness.py::test_no_real_world_email_domain_in_demo_dataset` and `::test_every_demo_domain_is_reserved_or_local` (re-run this phase, both passing).

New synthetic identities introduced by this phase's own harnesses use the same reserved-domain convention, never `.local` for anything but the pre-existing demo default (`.local` triggers `EmailStr`'s reserved-name rejection when explicitly validated — see the desk-note below):

- Reset-repeatability harness (`test_stage11a_phase1_reset_repeatability.py`): `stage11a-phase1-cycle-{1..10}@lifeflow-owner-validation.example`.
- Owner-operated walkthrough (`e2e-owner-validation/phase1-walkthrough.spec.ts`): `owner-walkthrough-{timestamp}@lifeflow-owner-validation.example`.

## Desk note: `.local` rejected by explicit validation

While building the reset-repeatability harness, `dev-login` with an explicitly-passed `...@lifeflow.local` address returned `422` — Pydantic's `EmailStr` (via `email-validator`) rejects `.local` as "a special-use or reserved name" when the address is explicitly supplied and therefore validated (the hardcoded default `dev@lifeflow.local` on `DevLoginRequest` never goes through validation, since Pydantic v2 does not validate field defaults unless `validate_default=True`). This is not a product defect — it is `email-validator` behaving correctly — but it means any *new* synthetic email introduced by test code must use `.example`, not `.local`. Recorded here so a future contributor doesn't rediscover this the hard way.

## Existing scenario inventory (unchanged from Round 1)

No new email/event fixture content was added to `demo/data/v1/`. Phase 1 exercises the existing 24-email/12-event dataset exactly as already catalogued in [synthetic-scenario-manifest.md](../../synthetic-scenario-manifest.md) — this document adds no new scenarios, only new *synthetic user identities* to drive repeated cycles through that same static dataset.

## Confirmation

No real name, organisation, email address, or event appears anywhere in this phase's new code or evidence. No production OAuth credential is configured or required by any new test.
