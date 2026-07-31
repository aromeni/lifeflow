# Stage 11A Phase 2 — Rollback Rehearsal Results

**Status:** Complete · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) (S11A-P2-027) · [recovery-timing-summary.md](recovery-timing-summary.md)

No production deployment or image-versioning infrastructure exists yet for this project (confirmed during the Phase 2 audit) — this is explicitly a **local packaging rehearsal**, proving the *shape* of a safe rollback (an explicit, truthfully-observed failure, then an explicit, verified recovery), not a real blue/green or container-image rollback. No production infrastructure is provisioned by this rehearsal.

## Method

`scripts/stage11a-phase2-rollback-rehearsal.sh`. Each of 3 cycles: (1) starts the current known-good configuration and confirms `/health`; (2) applies a **deliberately failing candidate configuration** — not a contrived failure, but a genuine existing startup guard already in the product (`main.py::_session_secret`: a production-mode boot with an empty `SESSION_SECRET` refuses to start) — and confirms it exits non-zero with the exact expected guard message, never a false success; (3) explicitly rolls back by restarting the known-good configuration and confirms `/health` and `/ready` both respond truthfully; (4) confirms the git SHA under rehearsal never changed.

## Results

| Cycle | Known-good up | Failure confirmed | Rollback total |
|---|---|---|---|
| 0 | 2.26s | 2.23s | 2.31s |
| 1 | 1.39s | 2.13s | 2.02s |
| 2 | 1.67s | 2.17s | 2.02s |

All 3 cycles: PASS. Version under rehearsal throughout: `91b6ec5c56cf136bad2e68c7953b0c1419080e51` (unchanged before/after every cycle — confirmed by `git rev-parse HEAD` comparison). Alembic schema compatibility unaffected: `uv run alembic heads` → `0011 (head)` before and after the full rehearsal. No user-visible false success occurred at any step — the broken configuration's own exit code and log message were asserted directly, not inferred.

## Cleanup

The wrapper script's `trap cleanup EXIT` pattern (`pkill -f` matched against the exact launch command, not a tracked PID — `uv run` does not always exec-replace itself, so a PID-based kill can miss the actual uvicorn child) was hardened during this phase after an initial run left one process orphaned on port 8026; confirmed no lingering process on any subsequent run.
