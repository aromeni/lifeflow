# Stage 11A Phase 4C — Defect Register

**Status:** 0 P0 · 0 P1 · 0 open P2 · 4 closed P2 · **Date:** 2026-08-02

## P0 findings

None.

## P1 findings

None.

## P2 findings

### F-P4C-01 — Pre-existing local OAuth client configuration contradicts the literal Phase 4C starting-state assertion

The ignored repository-root `.env` has `GOOGLE_OAUTH_ENABLED=true` and non-placeholder values present in every logical Google client field. The values were classified only as present/non-placeholder; no value, length, prefix, suffix, identifier, or secret was displayed. PostgreSQL contains zero encrypted access/refresh credentials, and the credential connection gate is clear.

This configuration predates the dedicated Phase 4C environment and is consistent with the repository's historical Stage 7 real-Google verification record. It must not be mistaken for, or silently reused as, the new Phase 4C client. With the current `main` code, enabling the configuration also exposes both Google initiation routes, so an accidental browser click could begin OAuth before the phase's explicit owner authorisation.

**Impact:** no token, account binding, provider data, API call, or Git exposure was found; however, the local runtime does not satisfy the phase prompt's literal “no OAuth client is configured” assertion and lacks the required Phase 4C initiation block.

**Closure conditions:**

1. add and verify a default-deny `GOOGLE_OAUTH_INITIATION_ENABLED=false` guard covering both initiation and callback routes without weakening the OAuth implementation;
2. owner directly replaces/retires the pre-existing local client configuration during the approved Phase 4C local-install checkpoint, without disclosing either old or new values;
3. presence-only validation confirms the new client configuration is installed and initiation remains blocked;
4. exact-boundary scans confirm no secret/identifier entered Git or output.

**Verification:** all four closure conditions are complete. The default-deny route/callback guard is implemented and tested; the owner confirmed replacement with the new one-client configuration; the redacted readiness check reports the one-client mapping, exact callbacks, and blocked initiation; and pre-commit, detect-secrets, staged and 108-commit Gitleaks, private-key, real-email/domain, identifier, token/client/project/callback, sentinel, environment-example, ignore-boundary, and diff checks all pass. OAuth itself remains blocked.

**Current state:** CLOSED.

### F-P4C-02 — First zero-state readiness assertion incorrectly included synthetic/demo account rows

The first post-installation extension of the readiness command required the entire `connected_accounts` table to contain zero rows. That is broader than the Phase 4C safety requirement: the long-lived development database legitimately contains synthetic/demo account rows, while the relevant real-connection boundaries are Google identity binding and stored credential presence. The over-broad check therefore returned `NOT READY` even though the credential-specific check reported zero.

**Impact:** verification false negative only. No credential, identity, provider call, callback, secret exposure, or production behaviour was affected.

**Fix:** replace the table-emptiness assertion with two precise, content-free checks: zero users bound to a Google subject and zero connected-account rows holding an encrypted access or refresh credential.

**Verification:** Ruff passes; the corrected readiness command reports `google_identity_bindings=0`, `stored_credential_rows=0`, every other Phase 4C configuration/guard check passing, and `READY`.

**Current state:** CLOSED.

### F-P4C-04 — Resilience E2E left encrypted fake-provider fixture rows in the shared development database

The final post-suite credential gate reported four `legacy_unknown` credential fields. Count-only and source inspection traced them to the resilience Playwright suite's direct synthetic `ConnectedAccount` seeding under its fixed `e2e-resilience-1` key. The suite used a fake Google server and obviously synthetic credentials, but did not remove those rows when it exited; the real preconnection gate correctly refused to treat them as safe under the active local key ring.

**Impact:** local test-residue blocker, not real-provider exposure. No real Google identity, token, endpoint, account, API interaction, or private content was involved. The gate failed closed exactly as designed.

**Fix:** add a locally/known-database-guarded `cleanup-accounts` operation that deletes only rows carrying the dedicated resilience fixture key; invoke it from the resilience suite's EXIT cleanup; explicitly keep OAuth initiation false in the resilience API environment; and make the support script import its repository source path reliably when run directly.

**Verification:** a new integration regression test proves cleanup deletes its fixed-key row while preserving an unrelated key row (1/1); the full resilience E2E suite passes 6/6 and reports four fixture accounts cleaned; the immediate direct gate returns all three counts zero and `clear_to_connect=true`; the final redacted readiness command reports zero Google identity bindings, zero credential rows, blocked OAuth, and `READY`.

**Current state:** CLOSED.

### F-P4C-03 — One independent mocked-route fixture did not explicitly enable the new initiation gate

The first exhaustive backend coverage run produced 11 failures (969 passes). Every failure was a 409 where an existing integration test expected its fully-mocked OAuth flow to redirect. The affected modules imported a shared override from `test_google_route_integration.py`; unlike the already-updated Google-auth fixture, that independently-declared override enabled `google_oauth_enabled` but omitted the new, separate initiation flag, so it correctly inherited the default-deny value.

**Impact:** test-configuration isolation only. The real Phase 4C environment and production default behaved correctly; no network call, redirect, callback, credential, or product-path defect occurred.

**Fix:** add `google_oauth_initiation_enabled=True` only to the mocked route-integration settings override. The application default and real local value remain false.

**Verification:** all three affected modules pass (24/24). The complete coverage suite is re-run as a phase quality gate rather than treating the targeted pass as the final suite result.

**Current state:** CLOSED.

## Non-defects

- The initial `pnpm exec prettier --check .` baseline command failed because Prettier is workspace-scoped; the repository's documented `pnpm web:format:check` command immediately passed. No formatting or product defect existed.
- The first sandboxed frontend build failed because Turbopack could not bind a local build port; the same unchanged build passed outside the sandbox. No repository defect existed.
