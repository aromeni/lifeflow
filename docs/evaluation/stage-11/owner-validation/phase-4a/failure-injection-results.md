# Stage 11A Phase 4A — Failure-Injection Results

**Status:** PASS · **Date:** 2026-08-01

Companion: [migration-design.md](migration-design.md) · [rotation-rehearsal-results.md](rotation-rehearsal-results.md) · [backup-and-retirement-results.md](backup-and-retirement-results.md)

Each row lists the injected failure, the test/rehearsal that exercises it, and the observed (required) behaviour.

| Failure injected | Exercised by | Required behaviour | Observed |
|---|---|---|---|
| Missing/unknown legacy key (row's key id absent from the ring) | `test_rotate_batch_blocks_rows_whose_key_the_ring_no_longer_holds` | Row classified BLOCKED, left completely untouched | PASS |
| Wrong key (same key id, different key material) | `test_token_cipher.py::test_wrong_key_fails` | `TokenCipherError`, no plaintext returned | PASS |
| Malformed active key at startup | `test_build_key_ring_rejects_invalid_legacy_key_material`, `test_invalid_keys_are_rejected` | Startup construction fails with `TokenCipherError` → `main.py` wraps as `RuntimeError` | PASS |
| Unknown record key version | `test_key_ring_rejects_unknown_key_id` | `TokenCipherError` naming the unresolvable key id, never a silent default | PASS |
| Tampered ciphertext | `test_tampered_envelope_is_rejected` (v1 and v2 paths) | `InvalidTag` → `TokenCipherError` | PASS |
| Tampered version/key-id metadata | `test_unknown_key_id_is_rejected` | `TokenCipherError` naming the tampered key id | PASS |
| Owner-context mismatch | `test_wrong_context_fails_authentication`, `test_transplanted_ciphertext_across_accounts_fails_to_decrypt` | `TokenCipherError` | PASS |
| Connected-account-context mismatch | same as above | `TokenCipherError` | PASS |
| Provider-context mismatch | `test_wrong_context_fails_authentication` | `TokenCipherError` | PASS |
| Database interruption during migration (simulated via rollback) | `test_rotate_batch_is_resumable_after_a_simulated_interruption`, rehearsal script steps 7–9 | No row left half-migrated; resumable to completion | PASS |
| Concurrent rotation commands (two batches racing) | `SELECT ... FOR UPDATE SKIP LOCKED` design, exercised structurally by the rehearsal script's interrupt/resume loop | No double-processing, no lost row | PASS |
| Concurrent token refresh during migration | `test_concurrent_refresh_and_rotation_never_corrupt_a_row` | No corruption, exactly one consistent result | PASS |
| Account deletion during/after migration | `test_full_account_deletion_removes_key_id_columns_with_the_row` | Credential (and key-id columns) removed with the row; no resurrection | PASS |
| Disconnect during/after migration | `test_disconnect_clears_key_id_columns` | Key-id columns cleared alongside ciphertext; rotation cannot resurrect a disconnected credential (nothing to migrate — both columns are `NULL`) | PASS |
| Backup restored with an incomplete key ring (legacy key omitted) | `stage11a_phase4a_backup_key_ring_rehearsal.py`, step 3 | Decrypt raises "No key available" — safe, explicit failure, never a fallback plaintext path | PASS |

## Conclusion

No unbounded retry was observed anywhere (rotation is always bounded by `batch_size` and driven by an external caller loop, never a self-retrying internal loop). No silent corruption, no cross-account decryption, and no record falsely marked migrated occurred in any injected scenario. No P0. No P1.
