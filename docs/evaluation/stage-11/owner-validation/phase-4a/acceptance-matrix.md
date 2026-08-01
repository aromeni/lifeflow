# Stage 11A Phase 4A — Acceptance Matrix

**Status:** In execution · **Date:** 2026-07-31 · row 047 added 2026-08-01 during the PR #13 merge-integrity check (see [phase-4b-connection-gate.md](phase-4b-connection-gate.md))

Built before implementation began, per the governing task instruction. Each row is verified by an automated test unless marked "manual"/"script".

| ID | Scenario | Method |
|---|---|---|
| S11A-P4A-001 | `AesGcmTokenCipher` still encrypts/decrypts correctly; v1 envelopes remain readable unchanged | automated |
| S11A-P4A-002 | New encrypts always produce a `v2` envelope | automated |
| S11A-P4A-003 | `v2` envelope binds AAD to `account_id:user_id:provider:field` | automated |
| S11A-P4A-004 | Decrypting a `v2` envelope with the wrong account context fails | automated |
| S11A-P4A-005 | Decrypting a `v2` envelope with the wrong user context fails | automated |
| S11A-P4A-006 | Decrypting a `v2` envelope with the wrong provider context fails | automated |
| S11A-P4A-007 | Decrypting a `v2` envelope with the wrong field (access↔refresh swap) fails | automated |
| S11A-P4A-008 | `v1` envelopes decrypt regardless of context (backward compatibility, not a security regression since v1 never carried context) | automated |
| S11A-P4A-009 | Tampered ciphertext fails authentication (both v1 and v2) | automated |
| S11A-P4A-010 | Tampered key-id metadata fails safely | automated |
| S11A-P4A-011 | `TokenKeyRing` rejects duplicate key ids between active and legacy | automated |
| S11A-P4A-012 | `TokenKeyRing` rejects a missing active key | automated |
| S11A-P4A-013 | `TokenKeyRing` rejects malformed legacy key material | automated |
| S11A-P4A-014 | `TokenKeyRing` decrypts a row still on a legacy key correctly | automated |
| S11A-P4A-015 | `TokenKeyRing` raises "no key available" for a truly unknown key id | automated |
| S11A-P4A-016 | New writes through the key ring always use the active key | automated |
| S11A-P4A-017 | Startup rejects duplicate key versions in configuration | automated |
| S11A-P4A-018 | Startup rejects malformed key material in configuration | automated |
| S11A-P4A-019 | Startup rejects a missing active key when Google OAuth is enabled | automated |
| S11A-P4A-020 | Production startup refuses the known development key-id default | automated |
| S11A-P4A-021 | Configuration values never appear in repr/logs/health/metrics/error responses | automated |
| S11A-P4A-022 | Alembic migration adds key-id columns and backfills them from existing envelopes without needing key material | automated |
| S11A-P4A-023 | Single Alembic head maintained | automated |
| S11A-P4A-024 | Migration downgrade is safe and documented | manual + automated |
| S11A-P4A-025 | Bounded dry-run inventory reports counts without modifying data | automated |
| S11A-P4A-026 | Bounded batch migration re-encrypts only rows not yet on the active key | automated |
| S11A-P4A-027 | Batch migration uses row locking with `SKIP LOCKED` for safe concurrent invocation | automated |
| S11A-P4A-028 | Interrupted migration is resumable without data loss or duplicate processing | automated |
| S11A-P4A-029 | Unknown/unavailable key version blocks that row explicitly rather than deleting or silently skipping | automated |
| S11A-P4A-030 | A record already on the active key is skipped, not re-processed | automated |
| S11A-P4A-031 | Concurrent token refresh and rotation never corrupt a row | automated |
| S11A-P4A-032 | Refreshed tokens are always written under the active key | automated |
| S11A-P4A-033 | Disconnect during migration does not resurrect or corrupt the row | automated |
| S11A-P4A-034 | Full account deletion during/after migration leaves no credential residue | automated |
| S11A-P4A-035 | Imported-data deletion has no credential side effect | automated |
| S11A-P4A-036 | Inferred-preference deletion has no credential side effect | automated |
| S11A-P4A-037 | Legacy-key retirement is blocked while any row still references it | automated |
| S11A-P4A-038 | Legacy-key retirement is permitted once zero rows reference it | automated |
| S11A-P4A-039 | Backup preserves key-version metadata and ciphertext without exposing key material | script |
| S11A-P4A-040 | Restore with the correct key ring can read synthetic credentials | script |
| S11A-P4A-041 | Restore missing a required legacy key fails safely | script |
| S11A-P4A-042 | Rotation observability emits only bounded, content-free metrics | automated |
| S11A-P4A-043 | Sentinel search: no plaintext or key material leaks to DB/Redis/logs/metrics/Git outside the controlled boundary | automated |
| S11A-P4A-044 | Three complete rotation rehearsals (18-step lifecycle each) pass | script (3 cycles) |
| S11A-P4A-045 | No rotation endpoint is exposed publicly; only an internal/operator command exists | manual + automated |
| S11A-P4A-046 | A user-controlled identifier cannot direct rotation to migrate another owner's account | automated |
| S11A-P4A-047 | An explicit, non-decrypting Phase 4B pre-connection gate exists and fails closed unless every stored credential field is on the active key (zero unversioned, zero legacy-known, zero legacy-unknown rows) | automated |

All 47 rows must PASS for this phase's decision to be PASS or CONDITIONAL PASS; any FAIL on a P0-class row (001–016, 026–038, 043, 045–047) forces FAIL — TEST-ACCOUNT CONNECTION REMAINS BLOCKED.
