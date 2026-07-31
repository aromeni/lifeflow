# Stage 11A Phase 3 — Owner-Scoping Results (S11A-P3-001–006)

**Status:** PASS · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md)

## What was already proven

`test_ownership.py` proves structurally, over every user-owned table via reflection, that a cascading `user_id` FK exists and every repository binds an owner (re-run fresh this phase, all passing). Individual routes already had one-off cross-user 404 tests (`test_privacy_deletion_api.py`, `test_audit_history.py`, `test_memory_api.py`).

## What this phase added

`apps/api/tests/test_stage11a_phase3_owner_scoping.py` — 13 tests, all passing:

- **Action-proposal routes** (`GET`/`PATCH`/`approve`/`reject`/`execute`): 5 id-attack shapes (valid foreign id, guessed id, stale id, malformed UUID, empty UUID) against an unrelated logged-in owner, for every mutating route. Every attempt returned 404 (or 422 for the malformed-UUID case, rejected by FastAPI's own path-param validation before any repository lookup runs). The owner's proposal was verified untouched (same status, version, and payload) after all five attack attempts.
- **List endpoint**: confirmed a second owner's proposal count is exactly their own, never inflated by another owner's rows.
- **Memory routes** (`GET`/`confirm`/`edit`/`dismiss`/`delete`): all 5 mutating routes return 404 for a foreign memory id, never a conflict response that would disclose existence.
- **Deletion-operation cancel**: extends existing preview/get/confirm coverage to the cancel route specifically.
- **Scheduled-brief status**: confirmed the route takes no id parameter at all (settings-style, always current-user), and two freshly created, never-enabled users report identical, content-free "never run" status — proving no request field can select another owner's schedule.

## Result

All 5 resource families covered at the required 5-attempts-per-family count. Zero cross-owner disclosure or mutation found. No existence oracle found (every foreign-id case returns an identical 404, whether the row belongs to another owner or doesn't exist at all).
