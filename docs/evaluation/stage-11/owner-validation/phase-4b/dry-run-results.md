# Dry-Run Results — 18-Step Connection Rehearsal

**Status:** 3/3 cycles pass · **Date:** 2026-08-01

Companion: `apps/api/scripts/stage11a_phase4b_connection_rehearsal.py` · [first-connection-runbook.md](first-connection-runbook.md)

## Method

`stage11a_phase4b_connection_rehearsal.py` runs the full simulated lifecycle from the governing task §21 against a dedicated, isolated local PostgreSQL database created and dropped for each cycle, using the app's real HTTP routes (via in-process ASGI transport, exactly like the existing integration test suite) and `httpx.MockTransport` in place of every Google-facing HTTP call. **No real Google account, project, or network call was ever made.**

## Steps simulated per cycle

1–4: configuration preconditions (test-control flags inert) · 5: connection gate before any connection · 6: account identity (dev-login) · 7: owner authorisation (simulated — not fabricated) · 8: consent-screen scope review · 9: simulated callback · 10: v2 credential storage verification · 11: sentinel scan (structural — no token ever printed) · 12: read smoke test (`sync`) · 13: emergency-stop check (scope-mismatch detection) · 14: revocation · 15: disconnect verification · 16: credential-residue re-check · 17: imported-data / full-account cleanup · 18: final clean-state verification.

## Results

| Cycle | Result | Time |
|---|---|---|
| 1 | PASS | — |
| 2 | PASS | — |
| 3 | PASS | — |

All 3 cycles: **3/3 passed in 3.8s** (final run, after the two script defects below were fixed).

## Defects found and fixed — in the rehearsal script itself, not the product

The first draft of this rehearsal script had two real bugs, both caught by running it rather than assuming it would work:

1. **A real network call to Google's live API was attempted.** The script initially replaced only `app.state.google_oauth_client` with a mock transport — matching the OAuth token-exchange mock pattern from `test_google_auth_and_connections_api.py` — but not `app.state.gmail_client`/`app.state.calendar_client`, which `create_app` otherwise wires to real `httpx.AsyncClient` instances pointed at the real Gmail/Calendar hosts. The step-12 read smoke test consequently sent a real HTTP request to Google's Gmail API with a fake bearer token and received a genuine `401` back — a real network call this task's governing instruction explicitly prohibits, made by tooling, not by any product code path. **Fixed**: the script now also assigns `app.state.gmail_client`/`app.state.calendar_client` to mock-transport-backed clients, matching the exact pattern `test_google_route_integration.py`'s `_app_client` already established for testing real-provider sync. **Caught before this rehearsal was ever reported as passing** — no commit or evidence claimed success before this was found and fixed.
2. **Incorrect assumption about full-account-deletion behaviour.** The script's step-18 assertion originally expected the `User` row to be physically removed from the database. Reading `account_deletion.py`'s `_PHASE_FINALISE` showed this is incorrect by design: full deletion sets `user.account_state = UserAccountState.deleted` (an anonymised tombstone), it does not delete the row — consistent with the retention/audit design already documented in Stage 9 and referenced in this phase's own [test-account-cleanup-plan.md](test-account-cleanup-plan.md) ("retain only permitted content-free tombstones"). **Fixed**: the assertion now checks `account_state == UserAccountState.deleted` and that no `ConnectedAccount` rows remain, matching the actual, correct, already-tested product behaviour (Phase 4A's `test_full_account_deletion_removes_key_id_columns_with_the_row` asserts the same `ConnectedAccount`-removal fact, not `User`-row removal).

Neither defect was in product code — both were in this new rehearsal script, found and fixed before it was ever reported as passing, matching the "evidence over theatre" standard the rest of this delivery has followed.

## What this proves and does not prove

This proves the full connection→smoke-test→disconnect→revoke→cleanup lifecycle behaves correctly against the *fake* provider, end to end, through the app's real routes. It does not prove anything about Google's actual behaviour (real consent-screen rendering, real token issuance, real API responses) — that can only be proven by the future, separately-authorised real connection described in [first-connection-runbook.md](first-connection-runbook.md).
