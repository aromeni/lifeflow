# Stage 11A Phase 2 — Execution Log

**Status:** Complete · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) · [../../../../delivery/stage-11a-phase-2-plan.md](../../../../delivery/stage-11a-phase-2-plan.md)

All commands run sequentially, on branch `stage-11a-phase-2-failure-recovery`, against the local Docker Postgres/Redis stack. Outage-injection suites (resilience, rollback rehearsal) were never run concurrently with anything else sharing PostgreSQL or Redis. No real Anthropic API key was configured — `det+anthropic` was not run and is not claimed.

| # | Suite | Command | Result |
|---|---|---|---|
| 1 | Backend tests + coverage | `uv run pytest --cov=lifeflow_api --cov-report=term-missing -q` | **835 passed** (817 + 18 new Phase 2 tests), 90% coverage |
| 2 | New: uncertain-write repeatability | `uv run pytest tests/test_stage11a_phase2_uncertain_write_repeatability.py -v` | **4 passed** (10+10 uncertain cycles, 5+5 refused-before-call cycles) |
| 3 | New: concurrent OAuth refresh | `uv run pytest tests/test_stage11a_phase2_concurrent_oauth_refresh.py -v` | **1 passed** (10 rounds × 5 concurrent callers) |
| 4 | New: cross-user isolation under failure | `uv run pytest tests/test_stage11a_phase2_cross_user_isolation.py -v` | **12 passed** (4 scenarios × 3 repetitions) |
| 5 | New: storage-pressure classification | `uv run pytest tests/test_stage11a_phase2_storage_pressure.py -v` | **1 passed** |
| 6 | Reset-repeatability harness (Phase 1, re-run) | `uv run pytest tests/test_stage11a_phase1_reset_repeatability.py -v` | **1 passed** (10 internal cycles) |
| 7 | Demo-clock determinism tests (Phase 1 closure, re-run) | `uv run pytest tests/test_stage11a_demo_clock_determinism.py -v` | **7 passed** |
| 8 | Frontend unit tests | `pnpm web:test` | **90 passed** across 10 files |
| 9 | ESLint / TypeScript / Prettier | `pnpm web:lint && pnpm web:typecheck && prettier --check .` | Clean |
| 10 | Production build | `pnpm web:build` | Compiled successfully; 12/12 pages generated |
| 11 | Ruff format / lint / mypy | `uv run ruff format --check . && uv run ruff check . && uv run mypy` | Clean; 90 source files |
| 12 | Functional E2E | `./scripts/e2e.sh` | **10 passed**, 2.2m (see defect-register.md's environmental-artefact note — first attempt hit stale shared-Redis rate-limit state from this session's own extensive prior testing; a `FLUSHDB` and clean re-run passed 10/10) |
| 13 | Resilience E2E | `./scripts/e2e-resilience.sh` | **6 passed** per run, **5 consecutive runs** (satisfies both the 3× and 5× repetition requirements); run 1 of the very first attempt hit a leftover local process (see defect-register.md T-P2-1), resolved, then 5/5 clean runs, ~47–53s each |
| 14 | Design/a11y/responsive/visual E2E | `./scripts/e2e-design.sh` | **26 passed**, 39.7s |
| 15 | Owner-operated failure walkthrough (new) | `./scripts/stage11a-phase2-owner-walkthrough.sh` | **1 passed**, 5 screenshots captured and individually viewed |
| 16 | Backup/restore rehearsal (new) | `uv run --project apps/api python3 apps/api/scripts/stage11a_phase2_backup_restore_rehearsal.py 3` | **3/3 cycles PASS** |
| 17 | Rollback rehearsal (new) | `./scripts/stage11a-phase2-rollback-rehearsal.sh 3` | **3/3 cycles PASS** |
| 18 | Deterministic signal eval | `./scripts/run-evals.sh det` | Precision 1.00, recall 0.94, 0 unsafe outputs |
| 19 | Deterministic + mock eval | `./scripts/run-evals.sh det+mock` | Precision 1.00, recall 1.00, 0 unsafe outputs |
| 20 | Brief eval | `./scripts/run-evals.sh brief` | 0 grounding/ordering violations, deterministic = True |
| 21 | Brief + mock eval | `./scripts/run-evals.sh brief+mock` | 0 grounding/ordering violations, deterministic = True |
| 22 | Action-proposal eval | `./scripts/run-evals.sh actions` | 0 grounding/schema/injection violations |
| 23 | Contract regeneration | `./scripts/generate-contracts.sh` | Regenerated; no diff (this phase adds no new routes/schemas) |
| 24 | Metrics regeneration (run twice, byte-stability check) | `python3 scripts/metrics.py` ×2 | Regenerated both times; second run byte-identical to the first (`diff` empty); real count changes recorded below |
| 25 | Alembic single-head check | `uv run alembic heads` | `0011 (head)` — unchanged, re-confirmed after every PostgreSQL outage cycle |
| 26 | Contrast-token validation | `python3 scripts/check_design_token_contrast.py` | All 28 token pairs meet their WCAG threshold |
| 27 | CI E2E-suite-coverage validator | `python3 scripts/check_ci_e2e_coverage.py` | All three required suites wired into `ci.yml` |
| 28 | Uvicorn launch-safety validator | `python3 scripts/check_uvicorn_launch_safety.py` | All 13 known launch sites set a safe proxy posture (2 new sites added this phase, both compliant) |
| 29 | `.env.example` secret-shape validator | `python3 scripts/check_env_example_secrets.py` | Clean |
| 30 | Full pre-commit | `uvx pre-commit run --all-files` | 12/12 hooks passed (one round of `detect-secrets` findings on two new test files' `client_secret="secret"` literals fixed with the same `# pragma: allowlist secret` convention already used elsewhere in the same test module) |
| 31 | `detect-secrets` full scan | `uvx detect-secrets scan --baseline .secrets.baseline` | Clean, exit 0 |
| 32 | Gitleaks (staged) | `gitleaks protect --staged --no-banner` | 0 leaks |
| 33 | Gitleaks (full history) | `gitleaks detect --no-banner` | 92 commits scanned, 0 leaks |
| 34 | `git diff --check` | `git diff --check && git diff --cached --check` | Clean |

## Metrics change (real, expected)

| Metric | Before this phase | After |
|---|---|---|
| Python files | 188 | 193 |
| Backend tests | 817 passing | 835 passing |

The +5 Python files are the 4 new test files (`test_stage11a_phase2_uncertain_write_repeatability.py`, `test_stage11a_phase2_concurrent_oauth_refresh.py`, `test_stage11a_phase2_cross_user_isolation.py`, `test_stage11a_phase2_storage_pressure.py`) plus the new backup/restore rehearsal script (`apps/api/scripts/stage11a_phase2_backup_restore_rehearsal.py`). The +18 backend tests are exactly: 4 (uncertain-write repeatability, parametrised ×2 action types ×2 test functions) + 1 (concurrent refresh) + 12 (cross-user isolation, 4 scenarios × 3 repetitions) + 1 (storage pressure) = 18. Backend coverage stayed 90%. No other value changed.

## Environmental notes (not defects — see defect-register.md)

Two runs in this section hit transient environmental state left over from this session's own unusually long sequence of back-to-back local suite executions (a leftover local process, and accumulated shared-Redis rate-limit bucket state) — both are documented in full in `defect-register.md` and were resolved without any code change, then reproduced clean.
