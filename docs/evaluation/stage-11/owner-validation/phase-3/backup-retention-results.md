# Stage 11A Phase 3 — Backup and Retention Results (S11A-P3-036)

**Status:** PASS (with an honestly-documented production limitation) · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) · [deletion-residual-analysis.md](deletion-residual-analysis.md)

`apps/api/scripts/stage11a_phase3_backup_deletion_rehearsal.py` — genuinely new tooling this phase, extending Phase 2's data-fidelity-only backup/restore rehearsal to the compliance question Phase 3's contract actually asks. 3/3 cycles PASS (~2.0–2.5s each).

## What each cycle proved

1. Seed a synthetic user with a full reference graph, including a real AES-GCM-encrypted connected account.
2. Take a "pre-deletion" backup (`pg_dump`) — scanned for secret-shaped values in the table-of-contents, none found.
3. Run a **real** full-account deletion in the *active* database, after the backup was taken.
4. Verify the active database reflects the deletion (anonymised email, zero source items, `deleted` account state).
5. Restore the pre-deletion backup into a separate, isolated database.
6. Verify the restored copy still shows the **original, pre-deletion** state — the original email, the source item, the connected account, and the exact same ciphertext envelope — proving the active database's later deletion did not (and structurally could not) reach into the already-taken backup.

## The honest limitation this documents

A conventional point-in-time database backup is a frozen snapshot. Deleting a user afterward in the live database has no effect on backups taken before that deletion — this is not a bug in LifeFlow, it is how backups work everywhere. **This means a production deployment needs an explicit backup-retention/expiry policy** aligned to the data's own retention rules (e.g., backups older than the longest retention horizon must themselves be destroyed or re-scrubbed) — LifeFlow does not claim, and this phase does not test, "immediate deletion from all backups," because that claim would be false for any conventional backup mechanism.

## Retention/expiry rehearsal

A minimal local rehearsal (`_rehearse_backup_retention_sweep`) proved the sweep mechanics directly: a backdated dummy file (aged past a fixed 7-day local policy) was destroyed by the sweep; a fresh dummy file was not touched. This says nothing about a real backup-storage provider's own lifecycle rules, which remain a documented, separately-owned future production requirement (tracked here, not silently assumed solved).

## Restored-credential safety

The restored connected account's ciphertext envelope was confirmed to retain the exact `v1:<key_id>:...` synthetic format — never decryptable outside this rehearsal's own in-memory key, and never pointing at any real provider host. Restored backups in this rehearsal never connect to anything beyond the isolated local scratch database.

## Result

The core compliance property (backup snapshot immutability with respect to later deletion) is proven directly, not merely asserted. The production backup-retention-policy requirement is recorded as a **P2, deadline-bound-by-Stage-12/13** item — not a blocking Phase 3 finding, since no production backup infrastructure exists yet to misapply this to.
