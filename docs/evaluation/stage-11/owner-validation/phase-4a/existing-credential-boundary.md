# Stage 11A Phase 4A — Existing Credential Boundary (recorded before editing)

**Status:** Recorded · **Date:** 2026-07-31

This documents the credential lifecycle exactly as it existed at `main@754890c`, before any Phase 4A change, so the design in [key-ring-design.md](key-ring-design.md) and [envelope-format.md](envelope-format.md) can be evaluated against a known baseline.

## Encryption primitive

`apps/api/src/lifeflow_api/security/token_cipher.py`. `AesGcmTokenCipher(key_b64, key_id)` — AES-256-GCM, one key per instance, envelope `v1:<key_id>:<base64 nonce>:<base64 ciphertext>`. `encrypt()`/`decrypt()` use **no associated authenticated data** (`self._aesgcm.encrypt(nonce, plaintext.encode(), None)`) — the ciphertext's authentication tag is bound only to the key and nonce, not to which database row it lives in.

**The limitation this phase closes (F-P3-03)**: `decrypt()` raises `TokenCipherError("No key available for key id '...'")` whenever the envelope's `key_id` doesn't match the single key the cipher instance holds. There is no code anywhere that holds two keys at once, so a real key rotation today has no supported path other than a manual, ad-hoc, one-off script.

**A second, previously undocumented limitation this phase also closes**: because there is no AAD, an envelope string copied from one `connected_accounts` row's `encrypted_access_token` column into a different row's column (same or different owner) decrypts successfully under either row, since nothing binds the ciphertext to the row it belongs to. This was never flagged as an exploitable defect (it requires direct database write access, which implies a much larger compromise already), but Phase 4A's governing instruction explicitly requires proving this cannot happen through the credential-encryption boundary itself, so it is closed as part of the same envelope-format change rather than left as a second latent gap.

## Wiring

Exactly one `AesGcmTokenCipher` instance is constructed in each of two places: `main.py:123` (API process, `app.state.token_cipher`) and `worker_app.py:90` (ARQ worker, captured inside `ctx["revoker"]`). `main.py` raises `RuntimeError` at startup if `GOOGLE_OAUTH_ENABLED=true` and `TOKEN_KEY` is empty; `worker_app.py` silently skips wiring instead (an existing asymmetry, not something this phase needed to fix to close F-P3-03, but noted for completeness).

## Schema

`connected_accounts.encrypted_access_token`/`encrypted_refresh_token` are nullable `Text` columns holding the full envelope string. No key-id column exists separately — the only place a key id is recorded is inside the envelope string itself.

## Service layer

`ConnectedAccountService.store_tokens()`/`get_access_token()`/`disconnect()` and `GoogleTokenService.get_valid_access_token()`/`get_valid_access_token_for_execution()`/`_decrypt_or_refresh()` (`apps/api/src/lifeflow_api/accounts.py`) are the only production call sites of `cipher.encrypt()`/`cipher.decrypt()`, plus one more in `google_wiring.py`'s revocation helper. Token refresh takes a real `SELECT ... FOR UPDATE` row lock (`accounts.py`, via `ConnectedAccountRepository.get_by_provider(..., for_update=True)`), proven safe for 10 rounds × 5 concurrent callers by `test_stage11a_phase2_concurrent_oauth_refresh.py`. There is no existing concurrency test for a rotation-vs-refresh race, since no rotation code existed to race against.

## Deletion interaction

Disconnect nulls both ciphertext columns. Full account deletion (`account_deletion.py`, `_PHASE_CREDENTIALS`) best-effort revokes with the provider, nulls both columns defensively, then hard-deletes the row. Imported-data and inferred-preference deletion never touch credential columns.

## Backup

`apps/api/scripts/stage11a_phase3_backup_deletion_rehearsal.py` already proves a conventional backup preserves the envelope byte-for-byte and that restoring it later still yields the same `v1:`-prefixed ciphertext — i.e. backups are envelope-format-agnostic snapshots. No existing rehearsal exercises a multi-key scenario.

## Conclusion

The primitive (AES-256-GCM) is sound and is not replaced by this phase. What is missing, and what this phase adds, is: (1) a way to hold more than one key at once, (2) a way to know which key a given row is currently on without depending on successful decryption, (3) a controlled, resumable service to move rows from an old key to a new one, and (4) binding each envelope's authentication tag to the row it belongs to.
