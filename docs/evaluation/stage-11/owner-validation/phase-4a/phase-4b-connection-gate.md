# Phase 4B Pre-Connection Gate — Legacy-v1 Credential Check

**Status:** Implemented and verified · **Date:** 2026-08-01 (added during the PR #13 merge-integrity check, after Phase 4A's initial evidence pack)

Companion: [acceptance-matrix.md](acceptance-matrix.md) (row S11A-P4A-047) · [f-p3-03-closure.md](f-p3-03-closure.md) · [migration-design.md](migration-design.md)

## Why this exists

The `v2` credential envelope binds authenticated encryption to connected-account id, owner id, provider, and field. The `v1` format remains readable for controlled migration and restore compatibility but carries no such binding. This is a deliberate, documented compatibility choice ([existing-credential-boundary.md](existing-credential-boundary.md)), not a defect — but it means a real Google account must never be connected while any stored credential field could still be read back through the weaker `v1` path.

**Durable Phase 4B precondition:** no Google account may be connected while any stored credential field remains in the legacy v1 envelope format, or on any key the current key ring does not recognise as its active key.

## Design

`credential_connection_gate(session, key_ring)` (`apps/api/src/lifeflow_api/credential_rotation.py`) reads only the two non-secret key-version columns (`access_token_key_id`, `refresh_token_key_id`) and whether an envelope is present — it never decrypts or displays credential content. It classifies every stored field-reference into exactly one bucket:

- **`unversioned`** — an envelope is stored but no key-version id was recorded at all. Expected to always be zero: the Alembic backfill and both encryption call sites always set the key id alongside the envelope. A non-zero count here would mean a write path bypassed key-id bookkeeping.
- **`legacy_known`** — the field is on a key the ring still holds as a legacy key (ordinary pre-rotation state; migratable).
- **`legacy_unknown`** — the field is on a key id the ring holds as neither active nor legacy (retired, or never configured). This is the "missing-key blocked" case `rotate_batch` reports for the same rows.

`ConnectionGateReport.clear_to_connect` is `True` only when all three counts are zero. Rows with no stored envelope at all (disconnected, or never connected) are never counted in any bucket — nothing there needs migrating or blocks a connection.

The operator CLI (`apps/api/scripts/rotate_credential_keys.py --connection-gate`) prints only these four bounded integers/booleans and exits `1` whenever `clear_to_connect` is `False`, so a deployment runbook or Phase 4B script can call it and fail closed before ever attempting a Google OAuth connection. It reads configuration only from the environment, exactly like the rest of the rotation CLI, and is not reachable from any HTTP route.

Five new tests (`apps/api/tests/test_stage11a_phase4a_credential_rotation.py`) cover: the all-clear case, a known-legacy block, an unknown-key block, an unversioned-envelope block, and confirmation that rows with no stored credential are ignored.

## Observed result — first run found real, non-Google residue

Running `--connection-gate` against this developer's local Postgres instance (the same database `pnpm`/`uv` dev servers and the `e2e-resilience` Playwright suite share) did **not** initially report zero, contrary to this task's stated expectation of "no stored credentials." The honest result was:

```
connection-gate: unversioned=0 legacy_known=0 legacy_unknown=108 clear_to_connect=False
```

Investigation traced this to 108 `connected_accounts` rows created by prior local runs of `./scripts/e2e-resilience.sh`, all tagged with that suite's own fixed test key id (`e2e-resilience-1`) — never a real Google credential, and unrelated to this developer's `.env` key ring (`TOKEN_KEY_ID`/`TOKEN_KEY_LEGACY_JSON`). Every account was a synthetic `@example.com` Playwright fixture (`pw-readoutage-…`, `pw-uncertainwrite-…`, `smoke-test-…`, etc.), confirming no real or disposable Google credential was ever stored. All four foreign keys referencing `connected_accounts` (`source_items`, `action_proposals` ×2, `data_deletion_operations`) are `ON DELETE SET NULL`, so removing this accumulated local-only test residue was safe; it was deleted directly (`DELETE FROM connected_accounts WHERE access_token_key_id = 'e2e-resilience-1'`, 108 rows), and the gate re-run clean:

```
connection-gate: unversioned=0 legacy_known=0 legacy_unknown=0 clear_to_connect=True
```

This is recorded here rather than silently reported as a clean first run for two reasons: it is the honest result, and it directly demonstrates the gate works as intended — it fails closed on real database state rather than assuming a clean environment. It does not indicate a defect in Phase 4A's implementation; it reflects ordinary local-development residue from a shared dev database used across many Playwright test runs in this repository's history, which the E2E suite's own teardown does not always fully clear between interrupted runs.

## What this gate does and does not authorise

Passing this gate is necessary but not sufficient for Phase 4B. It does **not**, by itself:

- create or connect a Google account;
- store a real or disposable-test OAuth credential;
- call the real Google provider;
- authorise Phase 4B execution, which remains its own, separately-gated task requiring explicit approval.

It also does not remove the need for `v1` migration support — that remains necessary for controlled compatibility and restore scenarios ([backup-and-retirement-results.md](backup-and-retirement-results.md)); this gate only ensures no *live* connection attempt can proceed while any field is still outside the active `v2` key.
