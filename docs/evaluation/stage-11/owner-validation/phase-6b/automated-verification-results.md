# Stage 11A Phase 6B — Automated Verification Results

**Date:** 2026-08-05

| Check | Result |
|---|---|
| Fake-provider rehearsal (`test_stage11a_phase6b_calendar_trigger_rehearsal.py`) | 9/9 passed |
| Full backend suite | **1058 passed**, 0 failed (1049 at Phase 6A.1's merge + 9 new rehearsal tests) |
| Ruff format/check | Clean (217 files) |
| mypy | Success — 94 source files |
| Frontend unit tests | **101 passed**, 0 failed — unchanged from Phase 6A.1 (no frontend code touched this phase) |
| Frontend lint/typecheck | Clean |
| Contracts regeneration | No diff — no API schema changed this phase |
| Evaluations — det | Precision 1.00, recall 0.94, 0 duplicates among expected, 0 unsafe outputs |
| Evaluations — det+mock | Clean, 0 confidence-calibration violations |
| Evaluations — brief | Deterministic, section counts match golden, low-confidence containment holds |
| Evaluations — brief+mock | Clean, fabricated-prose correctly rejected |
| Evaluations — actions | 0 grounding violations, 0 schema violations, 0 injection leakage |
| Alembic | Single head (`0012`), unchanged |
| `detect-secrets` | No new findings (only the tool's own baseline timestamp, discarded) |
| `git diff --check` | Clean |
| Prohibited-content scan of the evidence pack | Clean — no account address, token, event ID, or absolute local path |

| Functional E2E (`scripts/e2e.sh`) | 10/10 passed (first attempt hit a 120s cold-start timeout after the Turbopack cache was cleared per `pre-live-gate-results.md`; the immediate retry passed cleanly, confirming an environmental cold-start cost, not a regression) |
| Resilience E2E (`scripts/e2e-resilience.sh`) | 6/6 passed |
| Design/accessibility/responsive/visual E2E (`scripts/e2e-design.sh`) | 26/26 passed, including the visual-regression suite against the exact baselines Phase 6A.1 committed |

No test was skipped, weakened, or disabled to obtain a green result.
