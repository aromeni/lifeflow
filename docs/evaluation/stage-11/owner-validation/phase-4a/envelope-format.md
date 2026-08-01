# Stage 11A Phase 4A — Credential Envelope Format

**Status:** Implemented and verified · **Date:** 2026-08-01

Companion: [key-ring-design.md](key-ring-design.md) · [owner-account-binding-results.md](owner-account-binding-results.md)

## Two envelope versions, one wire shape

Both `v1` and `v2` share the four-colon-separated-field shape `<version>:<key_id>:<base64 nonce>:<base64 ciphertext>`. The version prefix is the only thing that changes decrypt behaviour:

- **`v1`** (pre-Phase-4A): AES-256-GCM, no associated authenticated data (AAD). Every already-encrypted synthetic record in this project (there is no real credential anywhere) is in this shape. `decrypt()` still accepts and correctly handles `v1` envelopes — a `context` argument is accepted for API uniformity but ignored, since `v1` never made a binding promise to break.
- **`v2`** (Phase 4A onward): AES-256-GCM with AAD bound to a caller-supplied `context` string. **Every new encryption always produces a `v2` envelope** — there is no code path left that produces a new `v1` envelope.

The envelope format itself does not carry the context — AAD is authenticated, not embedded; the caller must supply the identical context string at both encrypt and decrypt time, exactly as the row's own identity implies.

## The context string

`security/credential_context.py`'s `credential_context()` is the single, shared definition:

```
f"{connected_account_id}:{user_id}:{provider}:{field}"
```

`field` is one of the two closed constants `ACCESS_TOKEN_FIELD` (`"access_token"`) / `REFRESH_TOKEN_FIELD` (`"refresh_token"`). Every production call site (`accounts.py`, `google_wiring.py`) and every new test/rehearsal script derives the context through this one function — never a locally-reconstructed format string — so a typo or drift cannot silently produce a context that "happens to" still match.

## Why this closes the cross-account gap (F-P3-03's second, previously undocumented finding)

Before Phase 4A, `AesGcmTokenCipher.encrypt()`/`decrypt()` used no AAD (`self._aesgcm.encrypt(nonce, plaintext.encode(), None)`). An envelope's authentication tag was bound only to the key and nonce — nothing tied a specific ciphertext to the specific database row it was meant to live in. Copying `encrypted_access_token` from one `ConnectedAccount` row into a different row's column (same or different owner), or into the row's own `encrypted_refresh_token` column, would decrypt successfully under either the correct or the "wrong" row, since the cipher had no way to tell the difference.

Binding `connected_account_id:user_id:provider:field` into the AAD closes this: the AES-GCM authentication tag now cryptographically depends on all four identity components. Changing any one of them — a different account, a different owner, a different provider, or the sibling field of the same row — causes `AESGCM.decrypt()` to raise `InvalidTag`, which `AesGcmTokenCipher.decrypt()` wraps as `TokenCipherError`.

## Verified by

`test_wrong_context_fails_authentication` (`test_token_cipher.py`) proves all four dimensions (account, owner, provider, field) independently. `test_transplanted_ciphertext_across_accounts_fails_to_decrypt` and `test_transplanted_ciphertext_across_fields_fails_to_decrypt` (`test_stage11a_phase4a_credential_rotation.py`) prove the same property against real database rows rather than synthetic strings. `test_v1_envelope_decrypts_regardless_of_context` proves backward compatibility is preserved. Zero of these tests found a bypass — no P0 finding exists in this phase.
