# First-Connection Runbook

**Status:** Designed; not executed · **Date:** 2026-08-01

Companion: [provider-write-authorisation-gate.md](provider-write-authorisation-gate.md) · [emergency-stop-plan.md](emergency-stop-plan.md) · [first-connection-success-criteria.md](first-connection-success-criteria.md)

**This task does not execute this runbook.** It is the exact controlled sequence a future, separately-authorised connection task must follow, verbatim, per the governing instruction §13.

1. Confirm approved `main` SHA.
2. Confirm clean working tree.
3. Confirm all required CI checks green.
4. Confirm no test or participant data in the repository.
5. Run the credential connection gate (`rotate_credential_keys.py --connection-gate`).
6. Confirm zero blocked or stored credential rows.
7. Confirm active v2 key configuration (`TokenKeyRing`, `TOKEN_KEY`/`TOKEN_KEY_ID` set, not the `dev-1` default).
8. Confirm local services healthy (`docker compose ps` shows `db`/`redis` healthy; API `/health`/`/ready` green).
9. Confirm fake-provider and test-control settings are disabled for the real provider flow (`E2E_TEST_CONTROLS_ENABLED=false`, `GOOGLE_API_ORIGIN_OVERRIDE` unset).
10. Confirm production mode remains off (`ENVIRONMENT=development` or `test`, never `production`).
11. Confirm exact Google Cloud project (the dedicated project from [google-cloud-project-plan.md](google-cloud-project-plan.md), by project id/number, not by name alone).
12. Confirm exact OAuth client (the connector-consent client id matches `GOOGLE_CONNECTOR_CLIENT_ID` in the local `.env`).
13. Confirm exact test user (Account A only, per [test-account-specification.md](test-account-specification.md)).
14. Confirm exact scopes (the four scopes in [oauth-scope-matrix.md](oauth-scope-matrix.md), no more, no fewer).
15. Confirm exact callback URI (`http://localhost:8010/connected-accounts/google/callback`, matching both the registered Cloud Console value and `GOOGLE_CONNECTOR_REDIRECT_URI`).
16. Record owner authorisation (Decision 1 — see [provider-write-authorisation-gate.md](provider-write-authorisation-gate.md)) — a dated, explicit statement, not an inferred approval.
17. Begin OAuth (`GET /connected-accounts/google/connect`, signed in as the LifeFlow user representing the owner).
18. Review the Google consent screen presented in the browser.
19. Verify the displayed scopes match [oauth-scope-matrix.md](oauth-scope-matrix.md) exactly.
20. **Abort immediately** when any unexpected scope appears (see [emergency-stop-plan.md](emergency-stop-plan.md)).
21. Complete consent only for Account A — never any other Google account, even if already signed into the browser.
22. Verify LifeFlow stores exactly one `v2`-encrypted credential set for the connection (`credential_connection_gate` reports zero unversioned/legacy fields for the new account; the stored envelope's version prefix is `v2`).
23. Verify no token appears in browser storage, application logs, Redis, Prometheus metrics, or Audit History (repeat the existing Phase 3 sentinel-scan methodology against this one real connection).
24. Verify the connected-account identity matches Account A (email/subject, not merely "a Google account").
25. Perform read-only provider smoke tests (`POST /connected-accounts/google/sync` with the existing bounded sync window) — confirm messages/events import without error.
26. **Stop before any real provider write** — do not create a Gmail draft or insert a Calendar event under Decision 1.
27. Record results in a dated addendum to [first-connection-success-criteria.md](first-connection-success-criteria.md).
28. Require a second, separate, explicit owner approval (Decision 2, [provider-write-authorisation-gate.md](provider-write-authorisation-gate.md)) before testing Gmail draft creation or Calendar event insertion.

## What this document is not

This is a script for a future task, reviewed and readiness-tested by the three dry runs in [dry-run-results.md](dry-run-results.md) using only the fake-provider infrastructure. No step above has been executed against a real Google account by this task.
