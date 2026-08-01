# Stage 11A Phase 4A — Secret-Sentinel Results

**Status:** PASS · **Date:** 2026-08-01

Companion: [failure-injection-results.md](failure-injection-results.md) · [observability-results.md](observability-results.md) · [backup-and-retirement-results.md](backup-and-retirement-results.md)

## Sentinel values used

Distinctive, never-reused, obviously-synthetic values for: access-token plaintext, refresh-token plaintext, active key material (base64), and legacy key material (base64) — never a real credential or a real key, anywhere in this project.

## Surfaces searched

| Surface | Method | Result |
|---|---|---|
| PostgreSQL ordinary columns | Direct ciphertext-column scan after a full migration cycle (rehearsal step 12); real-row transplant tests | No plaintext or key material found outside the one encrypted-envelope column, and even there only as ciphertext |
| Redis | N/A this phase — the rotation service performs no Redis reads or writes; nothing new to scan | Not applicable |
| Structured logs | `test_rotation_never_logs_plaintext_or_key_material` captures real `JsonFormatter` output across a dry-run + batch-migration cycle carrying sentinel plaintext and both key materials | Zero occurrences of either sentinel or either key |
| Metrics output | `credential_key_rotation_total` has exactly one label (`outcome`), a 4-value closed vocabulary (`migrated`/`skipped_current`/`blocked`/`failed`) — no key id, account id, or content-derived value is ever a label | Not reachable by construction (see [observability-results.md](observability-results.md)) |
| Browser responses | No new API route exists for this phase to expose anything through | Not applicable |
| Audit History | No new audit-event metadata field was added by this phase; existing `record_audit_event` calls in `accounts.py` are unchanged in shape (still `provider`/`scope_count`/`authorisation_revision`, never a token or key) | Unaffected, re-confirmed by inspection |
| Generated evidence (this evidence pack) | Manual review of every new `.md` file in `docs/evaluation/stage-11/owner-validation/phase-4a/` | No key material or real credential; all examples are visibly synthetic placeholders |
| Temporary files | Both rehearsal scripts use `tempfile.TemporaryDirectory` for dump files, deleted automatically at scope exit; no dump file was ever written outside that directory | Confirmed by code inspection |
| Backup inspection output | `stage11a_phase4a_backup_key_ring_rehearsal.py`'s `_scan_dump_for_secrets` greps the `pg_restore -l` table-of-contents text for `TOKEN_KEY`/`SESSION_SECRET`/`-----BEGIN` | Zero matches across 3 cycles |
| Git boundary | Covered by the phase-wide exact-boundary security proof (staged diff inspection, `detect-secrets`, Gitleaks) rather than repeated here | See the final report's exact-boundary section |

## Conclusion

No plaintext credential or key material was found outside the one controlled decryption boundary at any surface searched. No P0. No P1.
