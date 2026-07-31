# F-002 Closure — Acceptance Matrix

**Status:** In progress · **Date:** 2026-07-31

Governs the closure task "Stage 11A Phase 1 — Final Determinism Fix and Merge." F-002 (see [defect-register.md](defect-register.md)) was mitigated by regenerating drifted baselines but its root cause — the demo synthetic anchor being derived from the real host clock — was left open. This matrix tracks closing it properly before PR #10 merges. Stable IDs: `S11A-P1-F002-XXX`.

| ID | Requirement | Verification method | Result |
|---|---|---|---|
| F002-001 | PR #10 boundary is exactly as left at Phase 1 completion: open, base `main`, head `stage-11a-phase-1-synthetic-validation`, 9 unrewritten commits, mergeable, `CLEAN` | `gh pr view 10`, `git log --oneline main..HEAD`, `git rev-parse main origin/main` | PASS — head `920d6c6`, `mergeable: MERGEABLE`, `mergeStateStatus: CLEAN`, 9 commits, `main`==`origin/main`==`296d59b` |
| F002-002 | Working tree and index clean; no Stage 11 tag; no test account/participant data | `git status --short`, `git tag -l "stage-11*"` | PASS — clean, no tags |
| F002-003 | Root cause of F-002 identified precisely (which mechanism, not just "flaky") | Read `connectors/synthetic.py`, `demo_mode.py` | PASS — `demo_mode.py:53-54` derives the synthetic import `anchor` from `datetime.now(ZoneInfo(user.timezone))` (the real host clock) on every `/demo/start` call; `SyntheticEmailConnector`/`SyntheticCalendarConnector` materialise every fixture's `day_offset` against that anchor, so which fictional email/event lands in-window and ranks highest drifts as real time passes — a changed fixture-selection/content outcome, not unstable visible date text, not a timezone disagreement, not snapshot-capture timing |
| F002-004 | A deterministic-clock override mechanism is added, scoped to demo/test use only, reusing an existing safe test-control pattern rather than a new bypass | Code review of `config.py`/`demo_mode.py` diff | PASS — new `demo_clock_override` setting, gated by the existing `e2e_test_controls_enabled` flag exactly like `google_api_origin_override` (Stage 9 Phase 5 §20 pattern) |
| F002-005 | Production cannot silently accept the override; no public endpoint can set server time; no user request can alter it | `test_e2e_test_controls_enabled_refuses_to_start_in_production` (extended), code review confirming no route reads `demo_clock_override` from request input | PASS |
| F002-006 | The override does not leak into OAuth, execution-expiry, or other security-relevant clocks | New regression test asserting `ActionProposal`/session timestamps still reflect the real wall clock while the demo anchor override is active | PASS |
| F002-007 | Host system date does not change generated synthetic content when the override is active | New regression test: two simulated host "now" values, override fixed, imported content/anchor identical | PASS |
| F002-008 | Host timezone does not alter expected content when the override is active | New regression test: two different `user.timezone` values, override fixed, anchor identical (override is UTC-anchored then converted, not re-derived) | PASS |
| F002-009 | Determinism holds across a midnight boundary, a month boundary, and a year boundary | New regression test parametrised across three override instants straddling each boundary | PASS |
| F002-010 | Reset-repeatability (10-cycle harness) is unaffected by the change | Re-run `test_stage11a_phase1_reset_repeatability.py` | PASS |
| F002-011 | Design Playwright config supplies the fixed demo clock to the API it launches | Code review of `playwright.design.config.ts` | PASS |
| F002-012 | Darwin baselines regenerated under the fixed clock and visually confirmed correct, non-blank, non-loading | `--update-snapshots` locally, `Read` on each changed PNG | PASS |
| F002-013 | Linux baselines regenerated under the fixed clock via real Linux/Chromium CI and visually confirmed | Temporary branch-scoped workflow (isolated, no credentials, removed after use), `Read` on downloaded artifacts | PASS |
| F002-014 | 5 consecutive local full design-suite passes with no snapshot regeneration between runs | `pnpm exec playwright test -c playwright.design.config.ts` × 5 | PASS |
| F002-015 | 3 consecutive visual-regression-only passes | `pnpm exec playwright test -c playwright.design.config.ts visual-regression.spec.ts` × 3 | PASS |
| F002-016 | One pass with a simulated different host date | API launched with `TZ`/monkeypatched-equivalent host date different from capture date, same committed baselines | PASS |
| F002-017 | One pass with a simulated different host timezone | API launched with a non-`Europe/London` `TZ`, same committed baselines | PASS |
| F002-018 | One real Linux CI pass against the final committed baselines (no regeneration) | GitHub Actions `E2E — design, accessibility, responsive, visual` check on the final pushed commit | PASS |
| F002-019 | Full Phase 1 gate list re-verified after the fix (backend, frontend, evals, lint/type/format, build, contracts, metrics, Alembic, contrast, launch-safety, pre-commit, secrets) | Re-run each command | PASS |
| F002-020 | Evidence pack updated; F-002 marked CLOSED — ROOT CAUSE FIXED with prior symptom, causal mechanism, permanent fix, safety boundary, regression proof, baseline source environment | `defect-register.md`, `phase-1-decision.md`, execution-log, this matrix | PASS |
| F002-021 | Correction committed in narrowly scoped commits without amending the 9 existing Phase 1 commits | `git log --oneline main..HEAD` after push | PASS |
| F002-022 | All required PR checks green against the final head SHA | `gh pr checks 10` | PASS |
| F002-023 | Merge via true merge commit only; no squash/rebase/force-push; no tag created | `gh pr merge 10 --merge`; post-merge `git log` | PASS |
| F002-024 | `main` after merge contains all Phase 1 + correction commits as ancestors; merged tree matches final PR head | `git merge-base --is-ancestor`, `git diff <head> <merge-commit>` | PASS |

All rows PASS. No row blocked. Full detail in the final report delivered to the user.
