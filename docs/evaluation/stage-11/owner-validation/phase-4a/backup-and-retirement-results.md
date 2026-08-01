# Stage 11A Phase 4A — Backup and Legacy-Key-Retirement Results (S11A-P4A-037–041)

**Status:** PASS, 3/3 cycles · **Date:** 2026-08-01

Companion: [migration-design.md](migration-design.md) · [rotation-rehearsal-results.md](rotation-rehearsal-results.md) · [f-p3-03-closure.md](f-p3-03-closure.md)

## Retirement gating

`verify_key_retirement_safe(session, key_id)` — a plain, unlocked `SELECT ... LIMIT 1` across both key-id columns — is the sole gate this design treats as sufficient to retire a key. Proven both ways: `test_key_retirement_is_blocked_while_rows_still_reference_it` (returns `False` while a legacy-key row exists) and `test_key_retirement_is_permitted_once_zero_rows_reference_it` (returns `True` only after every row has migrated). The rotation rehearsal script performs the same check live against a real multi-owner dataset (step 13) before simulating a service restart with the legacy key dropped from the ring entirely (step 14), then proves every migrated credential remains readable (step 15) and that no row references the retired key (step 16).

## Backup implications — script

`apps/api/scripts/stage11a_phase4a_backup_key_ring_rehearsal.py`, 3 cycles, each:

1. Seed a synthetic credential on a legacy key.
2. Take a `pg_dump` backup of the live database (via `docker compose exec -T db pg_dump`, matching the established Phase 2/3 convention — `pg_dump`/`pg_restore` are never assumed installed on the host).
3. Scan the backup's table-of-contents text for `TOKEN_KEY`/`SESSION_SECRET`/`-----BEGIN` — none found in any cycle, confirming no key material enters the dump.
4. Migrate the **live** database to the active key (the backup was already taken and is now stale relative to the live database's key state).
5. Restore the backup into a separate, isolated database.
6. Confirm the restored copy still shows the **pre-migration** key id (`legacy-backup`) — proving migrating the live database does not retroactively alter an already-taken backup, the same class of finding F-P3-05 established for deletion.
7. Confirm a **full** key ring (both legacy and active keys supplied) can still decrypt the restored, pre-migration credential correctly.
8. Confirm an **incomplete** key ring (legacy key omitted, as it would be after a real retirement) fails safely with the documented "No key available" error — never a silent fallback, never a plaintext leak.

All 3 cycles passed all 8 steps.

## The honest limitation this establishes

Retiring a live key does not, and structurally cannot, reach into an already-taken backup — a restored backup still needs whatever key(s) were active when it was taken, regardless of what the live system's key ring looks like today. **A real deployment must therefore retain every key a still-relevant backup depends on until that backup itself expires under its own retention policy.** This is recorded here as a requirement for future production backup infrastructure, not solved by this phase — no production backup infrastructure exists yet for a real policy to apply to (per the same honest-limitation framing Phase 3's F-P3-05 already established for deletion-vs-backup).

## Conclusion

No P0. No P1. The backup/retirement interaction behaves exactly as a correctly-designed system should, and is documented rather than silently assumed.
