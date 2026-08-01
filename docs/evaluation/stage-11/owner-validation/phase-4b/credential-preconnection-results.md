# Credential Preconnection Gate Results

**Status:** Verified 3/3 clean runs · **Date:** 2026-08-01

Companion: [../phase-4a/phase-4b-connection-gate.md](../phase-4a/phase-4b-connection-gate.md) (the gate's design) · [preconnection-readiness-results.md](preconnection-readiness-results.md) (the broader readiness command built this phase)

## Command

```
uv run python3 scripts/rotate_credential_keys.py --connection-gate
```

## Three runs from the current state, 2026-08-01

| Run | unversioned | legacy_known | legacy_unknown | clear_to_connect |
|---|---|---|---|---|
| 1 | 0 | 0 | 0 | true |
| 2 | 0 | 0 | 0 | true |
| 3 | 0 | 0 | 0 | true |

All three runs were taken against the same local Postgres instance after a clean `alembic upgrade head`; no code changed between runs. Zero stored credentials of any kind currently exist in this environment (confirmed separately by direct row count — see below).

## Stored credential count

```sql
SELECT count(*) FROM connected_accounts
  WHERE encrypted_access_token IS NOT NULL OR encrypted_refresh_token IS NOT NULL;
-- 0
```

## Missing-key blocked records

Zero — `legacy_unknown=0` in every run above is exactly this count (the gate's `legacy_unknown` bucket is definitionally the same set `rotate_batch` would report as `BLOCKED`).

## CI-safe regression coverage

The gate's availability and its ability to block a simulated unsafe state are already covered by 5 tests added during the Phase 4A PR #13 merge-integrity correction (`apps/api/tests/test_stage11a_phase4a_credential_rotation.py`), re-run and passing as part of this phase's automated verification:

- `test_connection_gate_clears_when_every_row_is_on_the_active_key` — the all-clear case
- `test_connection_gate_blocks_on_a_known_legacy_reference` — a migratable-but-not-yet-migrated row still blocks
- `test_connection_gate_blocks_on_an_unknown_key_id` — a retired/unconfigured key id blocks
- `test_connection_gate_flags_an_envelope_with_no_recorded_key_id` — an unversioned envelope blocks
- `test_connection_gate_ignores_rows_with_no_stored_credential` — a disconnected/never-connected row is correctly excluded from every bucket

No new test was needed to satisfy this phase's requirement (S11A-P4B-037) — these five already prove the gate remains available in CI and fails closed on every unsafe state the design accounts for.

## Non-decryption confirmation

`credential_connection_gate()` reads only `encrypted_access_token`/`encrypted_refresh_token` (existence only, via `IS NOT NULL`-equivalent Python truthiness) and the two `*_key_id` columns — it never calls `.decrypt()` or any cipher method, confirmed by direct inspection of `apps/api/src/lifeflow_api/credential_rotation.py`.
