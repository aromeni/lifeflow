# Test-Account Revocation, Disconnect, and Cleanup Plan

**Status:** Designed; rehearsed in dry runs using the fake-provider stack · **Date:** 2026-08-01

Companion: [emergency-stop-plan.md](emergency-stop-plan.md) · [dry-run-results.md](dry-run-results.md) · [real-provider-data-boundary.md](real-provider-data-boundary.md)

## OAuth revocation

- Revoke LifeFlow's access through Google (Google Account → Security → Third-party apps & services → LifeFlow → Remove access), or through LifeFlow's own `POST /connected-accounts/google/disconnect`, which already calls the provider's revoke endpoint where reachable (`ConnectedAccountService.disconnect`, `accounts.py`).
- Record the **truthful** provider result: `test_disconnect_google_never_requires_google_reachable` (existing) already proves LifeFlow's local disconnect succeeds even when Google's revoke endpoint is unreachable — the plan must record which actually happened (local disconnect only, vs. local disconnect + confirmed Google-side revocation), never claim revocation succeeded without checking Google's own "Third-party access" page.

## LifeFlow disconnect

- `POST /connected-accounts/google/disconnect` stops credential use, and per Phase 4A's account-deletion design, nulls `encrypted_access_token`/`encrypted_refresh_token` and the two `*_key_id` columns together (`account_deletion.py`'s `_PHASE_CREDENTIALS`).
- Verify zero stored credentials afterwards: `credential_connection_gate` reports the disconnected account's fields as absent (no envelope → excluded from every bucket, per `test_connection_gate_ignores_rows_with_no_stored_credential`).
- Verify no migration job can resurrect them: the rotation service (`rotate_batch`) only ever operates on rows with a non-null envelope and a stale key id — a disconnected row (both null) is never selected as a candidate (`_select_candidates`'s `isnot(None)` guards), matching the existing Phase 4A proof `test_disconnect_clears_key_id_columns`.

## Imported-data deletion

- Remove imported Gmail/Calendar content via the existing imported-data deletion operation (Stage 9 privacy tooling) — this is unchanged by Phase 4B; the same deletion path already proven for synthetic-connector data applies identically to real-provider-sourced `SourceItem` rows, since both flow through the same repository/model.
- Preserve only justified content-free evidence (ids, counts, timestamps) per [evidence-handling-plan.md](evidence-handling-plan.md).

## Inferred-preference deletion

- Remove learned preferences via the existing separate inferred-preference deletion operation — unaffected by this phase.

## Full LifeFlow account deletion

- Remove or anonymise owner data via the existing full-account-deletion flow; confirmed by Phase 4A's `test_full_account_deletion_removes_key_id_columns_with_the_row` that credential material (including the two key-id columns) is removed with the row, not left as residue.
- Retain only permitted content-free tombstones, per the existing Stage 9 retention design.

## Google-account cleanup (end of testing programme)

1. Remove fictional messages and events from both accounts (Gmail trash/delete, Calendar delete).
2. Remove any drafts LifeFlow created (Decision 2 testing only).
3. Remove any inserted events (Decision 2 testing only).
4. Revoke LifeFlow's app access from both accounts' Google Account security settings (belt-and-braces, even after LifeFlow-side disconnect).
5. Delete the OAuth client credentials from the Google Cloud Console.
6. Delete the dedicated Google Cloud project when the testing programme ends (Cloud Console → project settings → Shut down).
7. Delete the disposable Account A and Account B themselves after the retention period the owner sets (not before revocation/project deletion above, to avoid any window where a deleted account's tokens might still resolve — though Google itself invalidates tokens on account deletion regardless).

## Post-cleanup verification

After any cleanup step, inspect directly (not merely trust the operation's return value):

- **Database**: `SELECT * FROM connected_accounts WHERE user_id = '<owner-user-id>'` shows no credential fields populated.
- **Redis**: no residual rate-limit or session keys referencing the disconnected account beyond ordinary TTL-bound entries unrelated to credentials.
- **Browser**: dev-tools storage inspection shows no token-shaped value (existing Phase 2/3 sentinel methodology).
- **Logs**: sentinel scan (existing methodology) finds no token or key material.

## Cleanup order note

Steps are ordered to avoid a partial-cleanup window where a credential could still be technically valid but LifeFlow no longer tracks it (revoke before delete-locally is safer than the reverse, since a local-only disconnect with no Google-side revocation leaves the token technically alive until it separately expires per the 7-day Testing-status rule documented in [google-platform-requirements.md](google-platform-requirements.md)).
