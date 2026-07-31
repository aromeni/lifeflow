# Stage 11A Phase 2 — Cross-User Isolation During Failure Results

**Status:** Complete · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) (S11A-P2-028 to 031) · [../../../../architecture/threat-model.md](../../../../security/threat-model.md) (T2)

Extends the existing structural isolation proof (`test_ownership.py`) with behavioural proof specifically for the four failure-adjacent mechanisms this phase covers — new test file `apps/api/tests/test_stage11a_phase2_cross_user_isolation.py`, 3 repetitions each (12 test runs total, all passing).

| Scenario | Result | Evidence |
|---|---|---|
| Rate-limiter bucket exhaustion for one user never blocks another | PASS — Alice's bucket (capacity 2) exhausted completely; Bob, an independent hashed subject, remains fully allowed | `test_rate_limit_exhaustion_for_one_user_never_blocks_another` ×3 |
| An uncertain execution for one user never appears in, or affects, another user's data | PASS — Bob's `ActionExecutionRepository` lookup for Alice's proposal returns `None`; Bob's audit trail never mentions Alice's execution id; Alice's own lookup correctly resolves it | `test_uncertain_execution_for_one_user_never_appears_in_another_users_data` ×3 |
| One user's OAuth refresh/token row lock never blocks or leaks into another's | PASS — two different users' simultaneous expired-token refreshes each complete with exactly 1 real OAuth call (proceeding fully independently), contrasting with the same-account case which serialises two concurrent callers to 1 total call | `test_concurrent_refresh_for_different_users_proceeds_independently` ×3 |
| One user's deletion-recovery sweep never touches another's rows; recovery sweeps remain owner-scoped | PASS — two users' stale `running` deletion operations recovered by the same sweep call, each independently reset to `pending` and still correctly tied to its own `user_id` | `test_stale_deletion_recovery_sweep_is_owner_scoped` ×3 |

## On the deletion-recovery sweep's own cross-user query

`deletion.py::recover_stale_operations`'s docstring states it is "Cross-user by necessity" — it queries across all users to find stale rows, by design (a single sweep, not one per user, is how the worker recovers backlog efficiently). This is not a violation of isolation: what this phase's test proves is that the sweep's *effects* stay owner-scoped — each recovered row is reset based only on its own persisted state and remains attributed to its own `user_id`, never merged, aggregated, or cross-attributed. Any cross-user *exposure* (one user's data becoming visible or mutable by another) would be a P0 finding; none was found.

## Result

All 12 test runs (4 scenarios × 3 repetitions) pass. No cross-user exposure found under any failure condition exercised this phase.
