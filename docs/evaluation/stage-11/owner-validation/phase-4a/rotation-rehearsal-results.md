# Stage 11A Phase 4A — Rotation Rehearsal Results (S11A-P4A-044)

**Status:** PASS, 3/3 cycles · **Date:** 2026-08-01

Companion: [migration-design.md](migration-design.md) · [failure-injection-results.md](failure-injection-results.md) · [backup-and-retirement-results.md](backup-and-retirement-results.md)

## Script

`apps/api/scripts/stage11a_phase4a_key_rotation_rehearsal.py`, run against a dedicated, isolated local PostgreSQL database created and dropped every cycle (never the shared dev/test database, verified by an exact-prefix + localhost-only guard identical in spirit to the Phase 2/3 rehearsal scripts). Never calls a real Google endpoint. Never commits a database file.

## The 18-step lifecycle, per cycle

1. Create 3 synthetic owners.
2. Create 2 connected accounts per owner (6 total), covering two different provider values.
3. Store synthetic credentials under a legacy key (`legacy-v1`).
4. Confirm correct owner-scoped decrypt of a legacy-key row.
5. Introduce an active key (`active-v2`) while retaining the legacy key.
6. Run a dry-run inventory — confirmed exact expected count (12 field-references: 6 accounts × 2 fields, all still legacy).
7. Migrate in bounded batches (`batch_size=2`).
8. Interrupt migration part-way (a batch run inside a session that is rolled back rather than committed).
9. Resume migration to completion.
10. Execute a concurrent credential write (simulating a refresh) during a second migration pass.
11. Verify every surviving credential is on the active key.
12. Verify plaintext sentinels appear nowhere outside the controlled decryption boundary (direct ciphertext-column scan).
13. Remove the legacy key from the live test key ring (`verify_key_retirement_safe` check).
14. Restart services (simulated: construct a fresh `TokenKeyRing` holding only the active key).
15. Prove all migrated credentials remain readable under the restarted, legacy-key-free ring.
16. Prove no database record references the retired legacy key.
17. Disconnect and delete the synthetic accounts.
18. Prove no credential residue remains (ciphertext and key-id columns both `NULL`).

## Results

| Cycle | Seed | Dry-run | Migrate | Total | Outcome |
|---|---|---|---|---|---|
| 1 | 1.37–1.61s | 0.01–0.02s | 0.10–0.13s | 1.73–2.03s | PASS |
| 2 | 1.37–1.61s | 0.01–0.02s | 0.10–0.13s | 1.73–2.03s | PASS |
| 3 | 1.37–1.61s | 0.01–0.02s | 0.10–0.13s | 1.73–2.03s | PASS |

(Timings vary slightly run to run; the ranges above cover two consecutive full 3-cycle runs performed during this phase. These are local descriptive measurements, not production SLAs.)

All three cycles passed every one of the 18 steps with no manual intervention. No orphaned rehearsal database was left behind after any run (`docker compose exec -T db psql ... SELECT datname ... LIKE 'lifeflow_phase4a%'` returned zero rows after both full runs).

## Conclusion

The complete Path A lifecycle — dual-key coexistence, dry-run, bounded interrupted-and-resumed migration, concurrent-write safety, retirement gating, simulated restart, and full residue-free teardown — was proven directly, three times, not merely asserted. No P0. No P1.
