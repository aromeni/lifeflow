# Stage 11A Phase 4A — Migration/Rotation Service Design

**Status:** Implemented and verified · **Date:** 2026-08-01

Companion: [key-ring-design.md](key-ring-design.md) · [rotation-rehearsal-results.md](rotation-rehearsal-results.md) · [concurrent-refresh-results.md](concurrent-refresh-results.md) · [failure-injection-results.md](failure-injection-results.md)

## Schema (Alembic `0012_credential_key_versioning.py`)

Two nullable `String(40)` columns added to `connected_accounts`: `access_token_key_id`, `refresh_token_key_id` — each indexed. These record the `key_id` already embedded in the matching ciphertext envelope's own prefix, as an explicit, queryable column rather than requiring a decrypt to discover which key a row is on (per the governing instruction to prefer explicit version metadata over inferring from successful decryption).

Existing rows are backfilled by parsing (not decrypting) their already-stored envelope strings — the migration never needs, and never has, `TOKEN_KEY`. No secret material appears anywhere in the migration file. `downgrade()` drops the two columns; this is safe and reversible, since the ciphertext columns (and their embedded key ids) are never touched — a re-`upgrade()` simply re-derives the same metadata.

## Selection: `SELECT ... FOR UPDATE SKIP LOCKED`

`credential_rotation._select_candidates()` selects up to `batch_size` rows whose `access_token_key_id` or `refresh_token_key_id` differs from the ring's active key id, ordered by `id` for determinism, locked with `SKIP LOCKED`. This is the specific design choice that makes concurrent invocation safe (S11A-P4A-027): a row a concurrent `GoogleTokenService` refresh is already holding (via its own `SELECT ... FOR UPDATE`, no `SKIP LOCKED`) is simply left for the next rotation batch, never blocked on and never a source of contention.

## Per-row migration

For each locked row, `_migrate_field()` runs independently for the access and refresh fields: decrypt via the key ring (resolves active or legacy transparently), re-encrypt via the ring's active key (always producing a `v2`, context-bound envelope — closing the key-rotation and cross-account-binding gaps in the same pass), and update both the ciphertext and key-id columns together so they can never drift apart. A field already on the active key, or absent (`NULL`), is left untouched — reported `skipped_current` (though such rows are not even selected as candidates once every field is current). A field whose key id the ring does not resolve raises `TokenCipherError`, caught by `rotate_batch()` and classified `blocked` — the row is left completely untouched, never deleted, never marked migrated.

## Atomicity and resumability (S11A-P4A-024/026/028/030)

`rotate_batch()` performs one `session.flush()` per batch; the caller commits or rolls back the whole batch. An interruption before commit (process crash, or a deliberate rollback) discards the entire batch's in-memory changes — nothing is left half-migrated, and the next invocation simply re-selects the same still-legacy rows. This was proven directly, not merely asserted: `test_rotate_batch_is_resumable_after_a_simulated_interruption` migrates, rolls back, confirms every row is still on the legacy key, then re-runs to completion.

## Retirement gating (S11A-P4A-037/038)

`verify_key_retirement_safe(session, key_id)` is a plain, unlocked `SELECT ... LIMIT 1` checking whether any row still references `key_id` in either column. It is the sole condition the design treats as sufficient to retire a key from the live configuration — never a time-based heuristic, never "probably done by now."

## Not a public route (S11A-P4A-045/046)

`credential_rotation.py` exposes only plain async functions (`rotate_batch`, `dry_run_inventory`, `verify_key_retirement_safe`) — no FastAPI router, no HTTP path, no dependency-injected request context. The only callers are `scripts/rotate_credential_keys.py` (an operator CLI reading configuration from the process's own environment, never from request input) and this phase's own tests/rehearsals. `test_no_router_file_references_the_rotation_service` statically proves no router module imports it. There is structurally no way for a user-controlled identifier (a request parameter, a session, a proposal id) to direct which account gets migrated — the service processes whatever the database currently reports as stale, globally, which is the only safe shape for an operation an ordinary user must never be able to trigger or target.

## Deliberately not built

A public rotation-status API, a scheduled/automatic rotation trigger, and a "rotate on demand" UI control were all considered and rejected for this phase — the governing task explicitly requires "no public user-facing rotation endpoint," and none of the acceptance criteria call for automatic scheduling. An operator with direct database/process access runs `scripts/rotate_credential_keys.py` manually, which matches the project's existing convention for the deletion-retention sweep and the backup rehearsals (owner-operated, not automated in this phase).
