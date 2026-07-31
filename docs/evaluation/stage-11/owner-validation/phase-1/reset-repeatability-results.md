# Stage 11A Phase 1 — Reset Repeatability Results

**Status:** Complete · **Date:** 2026-07-31

Companion: [execution-log.md](execution-log.md) · `apps/api/tests/test_stage11a_phase1_reset_repeatability.py`

## Why this harness exists

No production "wipe and reseed" endpoint exists in this repository. The only reset route (`POST /__control__/reset` in `apps/api/src/lifeflow_api/testing/fake_google_server.py`) is scoped to the Stage 9 resilience E2E harness, not general demo state. This harness is Stage 11A's equivalent: each cycle uses a fresh synthetic user and ends by deleting it through the already-tested full-account-deletion path, so no cycle can contaminate the next — this reuses tested production code (`lifeflow_api.deletion.run_operation`, the real worker body) rather than raw SQL truncation.

## Method

10 independent cycles, each: fresh dev-login → `/demo/start` → `/briefs/generate` → approve + execute one proposal (called twice, to prove no duplicate) → account-deletion preview + confirm → complete via `run_operation` (the real worker body, invoked directly since no live arq worker runs in this harness) → verify residual state.

## Results

| Cycle | Imported | Proposals | Executions after double-execute | Account state | Residual content-bearing rows | Result |
|---|---|---|---|---|---|---|
| 1–10 | identical across all 10 (asserted via set-uniqueness, not hand-copied per cycle) | identical across all 10 | 1 (never 2) | `deleted`, email → `@deleted.invalid` | 0 (`SourceItem`, `Signal`, `ConnectedAccount`, `Preference`, `MemoryItem`) | PASS |

The test asserts set-based uniqueness (`len({...}) == 1`) across all 10 cycles for import count and proposal count, and `{1}` for execution count, rather than printing 10 near-identical rows — the assertion itself is the evidence, and it is reproducible by re-running `uv run pytest tests/test_stage11a_phase1_reset_repeatability.py -v`.

## Reset-requirement checklist (§14)

- [x] Removes prior synthetic state safely — via the tested account-deletion path, not raw SQL.
- [x] Recreates the expected fixtures identically each cycle — the demo dataset's fixture IDs (`em-001`, `ev-001`, etc.) are static.
- [x] Preserves no previous cycle's user-specific state — each cycle uses a fresh, distinct synthetic user, deleted at cycle end.
- [x] Avoids real credentials and provider calls — uses `SyntheticEmailConnector`/`SyntheticCalendarConnector` throughout; `ActionProposalService` defaults to `SimulatedExecutorRegistry` (no `google_executors` wired).
- [x] Is idempotent — delete-then-recreate is safe to repeat; proven by 10 consecutive successful cycles.
- [x] Fails loudly on partial completion — a pytest assertion failure, not a silent skip; no `try`/`except` swallows a failure anywhere in the harness.

## 100% success rate

10/10 cycles succeeded with zero residual content-bearing data and zero duplicate executions.
