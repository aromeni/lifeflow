# Stage 11A Phase 4A — Concurrent Refresh/Rotation Results (S11A-P4A-031/032)

**Status:** PASS · **Date:** 2026-08-01

Companion: [migration-design.md](migration-design.md) · [rotation-rehearsal-results.md](rotation-rehearsal-results.md)

## What was tested

`test_stage11a_phase4a_credential_rotation.py::test_concurrent_refresh_and_rotation_never_corrupt_a_row` races a real token refresh (`GoogleTokenService.get_valid_access_token`, real `SELECT ... FOR UPDATE` row lock) against a real rotation batch (`rotate_batch`, `SELECT ... FOR UPDATE SKIP LOCKED`) on the same `ConnectedAccount` row, using two independent database connections via `asyncio.gather`, against real PostgreSQL — the same pattern `test_stage11a_phase2_concurrent_oauth_refresh.py` established for refresh-vs-refresh concurrency, extended to refresh-vs-rotation.

## Result

Whichever transaction acquired the row lock first completed; the other either blocked until the first committed (the refresh path, which does not use `SKIP LOCKED`) or was skipped entirely for that batch (the rotation path, which does). In every run, the final row state was internally consistent: exactly one ciphertext value, decryptable under the correct context, and the recorded `access_token_key_id` accurately reflecting the key that ciphertext was actually encrypted under (the active key, since a refresh always writes through the active key and a completed rotation also leaves the active key). No split write, no corruption, no row left referencing a key id that does not match its own ciphertext.

## Why this is safe by construction, not by luck

Refresh takes `FOR UPDATE` (blocks); rotation takes `FOR UPDATE SKIP LOCKED` (never blocks, defers). This asymmetry is deliberate: refresh is latency-sensitive and must never be starved by a background maintenance job, while rotation is a bounded batch job that can simply retry the same row on its next invocation. There is no interleaving of these two lock modes that can produce a torn write, because PostgreSQL's row-level locking guarantees only one transaction holds the lock at a time regardless of which lock variant either side requested.

## Conclusion

No P0 finding (no corruption, no cross-account exposure under concurrency). No P1 finding.
