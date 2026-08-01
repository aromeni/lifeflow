# Stage 11A Phase 4A — Key-Ring Design

**Status:** Implemented and verified · **Date:** 2026-08-01

Companion: [existing-credential-boundary.md](existing-credential-boundary.md) · [envelope-format.md](envelope-format.md) · [acceptance-matrix.md](acceptance-matrix.md)

## Shape

`TokenKeyRing` (`apps/api/src/lifeflow_api/security/token_cipher.py`) holds exactly one **active** `AesGcmTokenCipher` (used for every new encryption) plus zero or more **legacy** ciphers (retained only long enough to decrypt not-yet-migrated rows). It implements the same `TokenCipher` protocol (`encrypt`/`decrypt`) as a single `AesGcmTokenCipher`, so it is a drop-in replacement — no consumer of `TokenCipher` (`ConnectedAccountService`, `GoogleTokenService`, `build_account_revoker`) needed to change its own type signature.

## Startup validation (S11A-P4A-011/012/013/017/018/019/020)

- **Duplicate-version rejection**: constructing a `TokenKeyRing` with a key id shared between the active key and any legacy key, or between two legacy keys, raises `TokenCipherError` immediately.
- **Invalid-key rejection**: each legacy key is constructed through the same `AesGcmTokenCipher.__init__` validation as the active key (non-empty base64, exactly 32 bytes, non-empty key id with no `:`).
- **Missing-active-key rejection**: `build_key_ring()` requires `active_key_b64`/`active_key_id`; there is no code path that produces a `TokenKeyRing` without an active cipher.
- **Configuration source**: `main.py`/`worker_app.py` build the ring from `TOKEN_KEY`/`TOKEN_KEY_ID` (active) and `TOKEN_KEY_LEGACY_JSON` (a JSON array of `{"key": ..., "key_id": ...}` objects, empty string meaning no legacy keys) — the same env-var-only secret-sourcing convention every other secret in this project follows.
- **Production dev-default guard**: `main.py`'s `create_app` refuses to start if `environment == "production"` and `TOKEN_KEY_ID == "dev-1"` (the literal `.env.example` default), the same "must never be true/default in production" idiom `E2E_TEST_CONTROLS_ENABLED` already uses.
- **No secret in config/logs**: `TokenCipherError` messages never include key material (only a key *id*, itself non-secret); `TokenKeyRing`/`AesGcmTokenCipher` have no `__repr__` override, so Python's default identity-based repr is used (no field is ever serialised into a log line, health response, or metrics label).

## Why not store keys in the database

Encryption keys must never be recoverable from the same store the ciphertext they protect lives in — storing a key in PostgreSQL, Redis, browser state, logs, or Git would defeat the point of encrypting at all. Keys live only in process configuration (environment variables / `.env`, never committed), constructed once at process startup and held only in memory for the life of the process.

## Verified by

`apps/api/tests/test_token_cipher.py` (`TokenKeyRing`/`build_key_ring` sections, 13 tests) and `apps/api/tests/test_stage11a_phase4a_credential_rotation.py`.
