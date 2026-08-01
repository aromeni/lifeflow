# Dedicated Google Cloud Project Plan

**Status:** Designed, not created · **Date:** 2026-08-01

Companion: [google-platform-requirements.md](google-platform-requirements.md) · [oauth-scope-matrix.md](oauth-scope-matrix.md) · [oauth-secret-handling-plan.md](oauth-secret-handling-plan.md)

**This task does not create the project described here.**

## Project purpose

A single Google Cloud project used only to issue the two OAuth clients (OIDC sign-in, connector-consent — matching LifeFlow's existing two-client design, ADR 0003 D10) needed to connect the two disposable test accounts defined in [test-account-specification.md](test-account-specification.md) to a locally-run LifeFlow instance.

## Environment classification

**OWNER-ONLY DISPOSABLE-ACCOUNT TESTING.** Not a staging or production environment; not shared with any other application.

## Project naming convention

A name that clearly signals disposability and scope, e.g. `lifeflow-owner-test` — never a name reused from, or resembling, a personal/production/university project.

## Project ownership

The project owner's own Google Cloud identity (or a dedicated Google Cloud-only account created for this purpose, at the owner's discretion) — never a client's, employer's, or university's Google Cloud organisation.

## Billing expectations

**No paid service is enabled to complete this phase or the eventual soak period.** The Gmail API and Calendar API do not require billing to be enabled for the request volumes involved (development-tier quota is more than sufficient for 2 test accounts and the bounded call budgets in [provider-call-budget.md](provider-call-budget.md)). Where Google's own account/project creation flow requires billing or another account-level prerequisite the owner has not already satisfied, this must be documented and escalated for owner review rather than enabled automatically — this phase makes no assumption that no such prerequisite will ever appear.

## API enablement

Enable exactly two APIs on the project: **Gmail API** and **Google Calendar API**. No other Google API is required by LifeFlow's implementation (confirmed by the current-implementation inspection underlying [oauth-scope-matrix.md](oauth-scope-matrix.md)).

## OAuth consent configuration

- User type: **External** (the disposable accounts are ordinary consumer Google accounts, not a Workspace organisation, so **Internal** user type is not available).
- Publishing status: **Testing**, kept at Testing throughout Phase 4B and the eventual soak period (see the 7-day refresh-token consequence documented in [google-platform-requirements.md](google-platform-requirements.md)).
- Test users: Account A and Account B only (§ [test-account-specification.md](test-account-specification.md)).
- Scopes: exactly the four scopes in [oauth-scope-matrix.md](oauth-scope-matrix.md), added to the consent screen's scope list.

## Support/contact information

A support email and developer-contact email must be supplied on the consent screen — use an address the owner controls and monitors, not a placeholder that bounces (see [oauth-consent-screen-copy.md](oauth-consent-screen-copy.md) for factual proposed wording; no real address is placed in this repository).

## Developer-contact information

Same email as support contact is acceptable for a single-owner testing project.

## Test-user configuration

Add Account A and Account B as OAuth consent-screen test users. Do not add any other account, including the owner's personal account, even for a quick check.

## Redirect-URI configuration

Register exactly the two redirect URIs LifeFlow already uses (see [redirect-uri-and-origin-plan.md](redirect-uri-and-origin-plan.md)) on the corresponding OAuth client — no additional or wildcard URI.

## Client-credential storage

Per [oauth-secret-handling-plan.md](oauth-secret-handling-plan.md): local `.env` only, never committed, never logged.

## Secret rotation

If a client secret is ever suspected exposed, rotate it immediately in the Google Cloud Console (which invalidates the old secret) and update the local `.env`; no LifeFlow code change is required since the client id/secret are read from configuration, not hard-coded.

## Shutdown and deletion procedure

At the end of the testing programme (per [test-account-cleanup-plan.md](test-account-cleanup-plan.md)): delete the OAuth client credentials, then delete the Google Cloud project itself via the Cloud Console's project-deletion flow (which schedules the project for permanent deletion after Google's standard retention window). Do not leave the project active "just in case" once testing concludes.

## Isolation requirements

This project must not share credentials with: another application, a production environment, a personal experiment, a university project, or a client system. It exists solely for this testing programme and is deleted when the programme ends.
