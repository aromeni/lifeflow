# Stage 11A Phase 2 — Backup and Restore Results

**Status:** Complete · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) (S11A-P2-026) · [recovery-timing-summary.md](recovery-timing-summary.md)

No backup or restore tooling existed anywhere in this repository before this phase — confirmed absent during the Phase 2 codebase audit, and explicitly flagged as unbuilt in `stage-11a-owner-validation-plan.md` §D ("backup creation and restore, in a local/test environment only... Planning only. No exercise is run by this document."). This phase builds and runs it for the first time.

## Method

`apps/api/scripts/stage11a_phase2_backup_restore_rehearsal.py`. Each of 3 cycles: creates an isolated scratch source database (`lifeflow_phase2_backup_src_N`), seeds one full synthetic reference graph (user, connected account, source item, brief, an approved+executed action proposal, an audit event, and a real completed imported-data-deletion operation run through the actual `create_imported_data_preview`→`confirm_operation`→`run_operation` code path against a second, empty account), records the resulting figures, `pg_dump`s it via `docker compose exec db pg_dump -Fc` (no host `pg_dump` install required), restores into a *separate* freshly created destination database via `pg_restore`, re-verifies every figure and the exact stored approval-binding-hash string, scans the dump's table-of-contents for any secret-shaped value, then drops both scratch databases.

## Results

| Cycle | Seed | Dump | Restore | Verify | Total |
|---|---|---|---|---|---|
| 0 | 0.55s | 0.51s | 0.78s | 0.08s | 1.92s |
| 1 | 0.49s | 0.33s | 0.88s | 0.07s | 1.78s |
| 2 | 0.67s | 0.35s | 0.80s | 0.08s | 1.89s |

All 3 cycles: PASS. Every restored figure (source item count, brief count, proposal count, execution count, audit event count, deletion operation count, and the exact approval-binding-hash string) matched the source database exactly. No secret-shaped value (`SESSION_SECRET`, `TOKEN_KEY`, a PEM header) appeared in the dump's table-of-contents. Both scratch databases were confirmed dropped after each cycle (`SELECT datname FROM pg_database WHERE datname LIKE 'lifeflow_phase2%'` → 0 rows). No dump file was committed — each lived in a `tempfile.TemporaryDirectory()` removed at the end of the run.

## Safety guards

Two independent checks (`_assert_safe_target`) restrict every database-admin operation in this script to `localhost`/`127.0.0.1` and a `lifeflow_phase2_backup_`-prefixed database name — mirroring the existing `e2e_deletion_support.py`'s own safe-target pattern. This script can never touch a real deployment's database.
