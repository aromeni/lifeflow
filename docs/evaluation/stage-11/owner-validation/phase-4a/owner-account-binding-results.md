# Stage 11A Phase 4A — Owner/Account Cryptographic Binding Results (S11A-P4A-003–010)

**Status:** PASS · **Date:** 2026-08-01

Companion: [envelope-format.md](envelope-format.md) · [defect-register.md](defect-register.md)

## What was tested

Every dimension of the AAD context (`connected_account_id`, `user_id`, `provider`, `field`) was independently varied while holding the ciphertext and key fixed, at two levels:

1. **Unit level** (`test_token_cipher.py::test_wrong_context_fails_authentication`): synthetic context strings, four independent wrong-context attempts (wrong account, wrong owner, wrong provider, wrong field), each asserted to raise `TokenCipherError`.
2. **Real-database level** (`test_stage11a_phase4a_credential_rotation.py`): `test_transplanted_ciphertext_across_accounts_fails_to_decrypt` physically copies one real `ConnectedAccount` row's `encrypted_access_token` ciphertext and attempts to decrypt it using a second, real account's derived context; `test_transplanted_ciphertext_across_fields_fails_to_decrypt` attempts to decrypt an account's own `encrypted_access_token` envelope using its `refresh_token` context.

## Result

Every transplant attempt failed with `TokenCipherError` (AES-GCM `InvalidTag` under the hood). Zero successful cross-account, cross-owner, cross-provider, or cross-field decryption occurred in any test run. This is the exact property the governing task requires to be treated as P0 if it ever succeeded — it did not succeed in any of the above scenarios.

## Backward compatibility

`test_v1_envelope_decrypts_regardless_of_context` proves a genuine, hand-built `v1`-format envelope (no AAD, matching the format every already-encrypted synthetic record in this project uses) still decrypts correctly regardless of what context string is supplied — the new binding requirement applies only to newly-produced `v2` envelopes, never breaking a pre-existing record.

## Conclusion

Owner/account cryptographic binding is implemented and verified at both the unit and real-database-integration level. No P0 finding. No P1 finding.
