# Stage 10 Completion Report — Product Design System and UX Completion

**Branch:** `stage-10-product-design` (branched from `main` @ `e347b75e27399eb353a6d57aa87fe4c2282a803a`, tag `stage-9-complete`).
**Date:** 2026-07-30.
**Status:** implemented and verified in the working tree, closed after a final acceptance review found and corrected several verification gaps in the first pass (see "Final closure findings" below). **Not committed, not pushed, not tagged.**

## Executive verdict

**APPROVE STAGE 10 FOR REVIEW**

## Delivered capabilities

A token-based design system (`apps/web/src/app/globals.css`, light and dark palettes, re-exported to Tailwind v4 via `@theme inline`) and a five-component shared library (`Badge`/`PriorityBadge`/`RiskBadge`, `Notice`, `Button`, `AppShell`/`PageHeader`, `Form` primitives) replace the previous ad hoc, unstyled Next.js boilerplate across every screen: landing, onboarding (rebuilt as a two-step guided wizard), Today, Approvals, Connections (including the destructive deletion flows), Audit history, and Settings. See [ADR 0006](../../architecture/adr/0006-stage10-product-design-system.md) for the decisions and [docs/product/design-system.md](../../product/design-system.md) for the reference.

## Final closure findings (this review round)

A first version of this report was returned with `APPROVE STAGE 10 FOR REVIEW` before several verification gaps were actually closed. Each is now fixed; see ADR 0006 D104–D108 for full detail:

1. **Degraded-provider and uncertain-execution states now have direct, real fixtures**, not just proxy coverage through another screen's `Notice` instance. Two new specs (`apps/web/e2e-resilience/stage10-outage-notice-fixture.spec.ts`, `stage10-uncertain-execution-fixture.spec.ts`) reuse the existing Stage 9 fake-Google-server infrastructure to reach the real backend-classified states — a real `GoogleTransientError` → degraded-sync notice, and a real `hang_on_write` → uncertain-execution warning — and assert correct tone/role, absence of raw provider detail, absence of an unsafe retry control, and zero horizontal overflow at all 5 required breakpoints.
2. **The three new Stage 10 test suites were moved out of the original `apps/web/e2e` boundary** into a new, independent `apps/web/e2e-design/` (`scripts/e2e-design.sh`, `playwright.design.config.ts`), restoring `apps/web/e2e` to exactly its original 10 functional journeys. `scripts/check_ci_e2e_coverage.py` and `.github/workflows/ci.yml` were both extended to require all three suites (`e2e.sh`, `e2e-resilience.sh`, `e2e-design.sh`) as real CI steps.
3. **The full golden-dataset eval matrix was actually run** (`det`, `det+mock`, `brief`, `brief+mock`, `actions`) rather than inferred as unaffected — all pass with figures identical to the Stage 9 baseline (`det`: 1.00 precision / 0.94 recall), confirming no backend regression, not merely assuming one couldn't exist. `det+anthropic` was not run (no `ANTHROPIC_API_KEY` configured — CI/demo mode never call real providers, per repository convention).
4. **The complete 12-item screenshot inventory was captured and visually reviewed** (see the manual checklist for the full table), not just the subset that happened to already exist.
5. **Two genuine, intermittent screenshot-timing races were found and fixed at the root cause** by stress-running the new design suite 5+ consecutive times rather than accepting one green run: the landing page's async Google-config fetch and the Connections page's async privacy-summary fetch could each be screenshotted mid-load. Both are now awaited explicitly before capture.
6. **An apparent cross-user data leak was investigated and disproven** via a direct, unmediated backend API call (bypassing the browser and UI) rather than dismissed or silently worked around — demo mode's own synthetic `ConnectedAccount` was confirmed correctly user-scoped (see ADR 0006 D108).
7. **A real repository-hygiene defect was caught and fixed**: the original full-page Today baseline was a 719KB PNG, over the repo's 500KB pre-commit limit — caught by actually staging the change and running `pre-commit run --all-files` against the exact staged boundary, not by inspection alone.
8. **An exact-boundary security proof was run against the literal staged changeset** (`git add -A`, full hook/secret-scan matrix, `git reset`), not against the working tree by assumption.

## Safety and behavior preservation

No safety-relevant behavior changed. Verified by direct inspection and by the full backend/frontend/e2e/resilience/design suites all passing:

- Gmail remains draft-only, Calendar remains insert-only — no executor, connector, or policy file was touched (confirmed again this round via `git diff --stat` against the Stage 9 boundary: zero changes under `apps/api/` or `prompts/`).
- Every `ActionProposal`'s exact-payload preview, risk level, confidence, and evidence are still shown before approval; Approve (`primary`/accent) and Reject/Edit (`secondary`) are never visually confusable, and `danger` (red, disabled until an exact typed phrase is entered) is reserved exclusively for permanent deletion.
- Deletion confirmation, uncertainty warnings, rate-limit messaging, and outage/degraded-provider notices all still render — restyled via the shared `Notice` component, not removed or reworded in meaning, and now proven via direct fixture rather than by proxy (see finding 1 above).
- `aria-live` status regions were audited for correct announcement semantics during the rework (see ADR 0006 D100) — a strictly stronger accessibility guarantee than before, not a regression.

## Design-system architecture

Neutral cool-grey surface/text scale, one restrained indigo accent, four semantic tone families (success/warning/danger/info) each with verified-contrast bg/border/text/icon sub-tokens. Priority and risk badges deliberately reuse the semantic scale rather than a separate palette (ADR 0006 D97). All 28 token colour pairs verified against WCAG 2.2 thresholds via `scripts/check_design_token_contrast.py` (4.5:1 text, 3:1 non-text UI boundaries) — all 28 pass.

## Navigation, landing, and onboarding

`AppShell` provides one persistent, slim top-nav bar (not a permanent sidebar — ADR 0006 D99) across all authenticated screens; landing and onboarding keep their own focused, nav-free flow. The landing page is a two-column layout: hero copy plus one primary CTA on the left, a seven-step pipeline diagram (Gmail+Calendar → evidence → priorities → proposed action → approval → execution → audit) on the right — no robot/AI-art imagery anywhere in the product. Onboarding is a two-step wizard with a visible step indicator and progressive disclosure (schedule, then brief-section choices plus an explicit Gmail-draft/Calendar-insert-only/disconnect statement).

## Verification evidence (final, 2026-07-30)

| Gate | Result |
|---|---|
| Backend tests (`uv run pytest`) | **800 passed** |
| Backend coverage | **90%** |
| `ruff format --check` / `ruff check` / `mypy` | clean |
| Frontend tests (`pnpm web:test`) | **90 passed** (10 files) |
| `pnpm web:lint` / `pnpm web:typecheck` / `prettier --check` | clean |
| `pnpm web:build` (production) | succeeds — 10 routes built |
| Original functional suite (`scripts/e2e.sh`, `apps/web/e2e`) | **10 passed** — exactly the original boundary, restored |
| Resilience suite (`scripts/e2e-resilience.sh`, `apps/web/e2e-resilience`, run in isolation) | **6 passed** — 4 original journeys + 2 new Stage 10 direct-state fixtures |
| Design/a11y/responsive/visual suite (`scripts/e2e-design.sh`, `apps/web/e2e-design`) | **26 passed** — stable across 5+ consecutive full-suite reruns |
| Deterministic eval (`det`) | 1.00 precision / 0.94 recall — unchanged from Stage 9 baseline |
| `det+mock` / `brief` / `brief+mock` / `actions` | all pass, 0 safety/grounding/injection violations |
| Alembic | single head `0011` (unchanged) |
| Contract regeneration | zero drift |
| Metrics regeneration | byte-stable across 2 consecutive runs |
| `pre-commit run --all-files` (12 hooks, against the exact staged boundary) | all pass |
| `detect-secrets` | clean, no new findings (allowlist inspected — all entries pre-existing Stage 7 test fixtures) |
| `gitleaks protect --staged` | 0 leaks |
| `gitleaks detect` (full history) | 0 leaks (gitleaks's own progress counter reported 59 commits scanned at this point in the review; see the note below on why that figure undercounts the true git-verified total and should not be read as an authoritative commit count) |
| Private-key detection | none found |
| `.env.example` / Uvicorn launch-safety checks | pass (all launch sites classified, including the two new suite configs) |
| CI suite-coverage validation | pass — all 3 suites wired as real `run:` steps |
| `git diff --check` | clean |

## Exact-boundary security proof

`git add -A` staged the final boundary of 55 changed paths (26 new, 29 modified; `git diff --cached --stat`: 3552 insertions, 1151 deletions). Confirmed staged: all screenshot/snapshot files (8 PNGs under `e2e-design/visual-regression.spec.ts-snapshots/`), all new test fixtures, all configuration changes (`ci.yml`, `playwright.design.config.ts`, `package.json`, `pnpm-lock.yaml`, `scripts/e2e-design.sh`). Confirmed absent from the staged set: any `.env` file, credential, database/Redis dump, runtime log, Playwright report/trace/`test-results/` directory, cache, absolute local path, or throwaway script. The full hook/secret-scan matrix above was run against this exact staged tree. `.secrets.baseline`'s only observed diff across scans was its own `generated_at` timestamp, which was discarded (`git checkout --`) rather than treated as a real change. `git reset` afterward returned the index to empty with all 55 changed paths verified still present, unstaged, in the working tree — nothing was discarded. (An earlier intermediate run of this proof, before the documentation and metrics fixes below were made, staged 54/28 paths; this section reports only the final, authoritative count.)

**Note on gitleaks's "N commits scanned" figure:** this is gitleaks's own internal progress counter, not equivalent to `git rev-list --count`/`git log --oneline | wc -l`. By default `git log -p` prints no diff for a merge commit (a combined/`-m` diff is needed to see one), and gitleaks's commit-boundary parser does not count a commit it shows no diff for — so its reported total is systematically lower than the repository's actual commit count by roughly the number of merge commits in the scanned range. It is a valid indicator that gitleaks is not scanning a suspiciously truncated slice of history, but it is not a substitute for `git rev-list --count` when an authoritative commit total is needed — see the Stage 10 merge report's "Commit-count reconciliation" section for the verified figures.

## Accessibility posture (honest, not certified)

Automated coverage (axe-core, `wcag2a`/`wcag2aa`/`wcag21a`/`wcag21aa` tags, filtered to serious/critical) plus a manual keyboard-only completion pass, a 200% zoom check, and a `prefers-reduced-motion`/dark-mode check all passed — see [docs/delivery/stage-10-manual-checklist.md](../stage-10-manual-checklist.md). **A real screen-reader (VoiceOver/NVDA/JAWS) pass was not performed** — no such tool is available in this environment — and is disclosed as an open gap rather than silently certified around. No claim of WCAG conformance certification is made anywhere in this stage's documentation.

## Visual review

Three full passes were performed, all with real screenshots (not descriptions), none reusing a prior pass's images: pass 1 mid-implementation (found and fixed leftover default-browser styling and inconsistent buttons); pass 2 against the converged design (light + dark mode, all breakpoints, the account-deletion confirmation state); pass 3, this closure round, after adding the direct outage/uncertain-execution fixtures and splitting the suite boundaries — the complete required 12-item inventory (see the manual checklist's table for exactly which are pixel baselines vs. manual-only evidence). No design defects were found in pass 3; the two code changes it produced (D106's async-load race fixes, D107's Today baseline scope change) were test-infrastructure corrections, not product changes.

## Known limitations

1. **Screen-reader manual testing gap**, disclosed above.
2. **Frontend coverage is not yet measured** (accepted historical limitation, unchanged since Stage 1).
3. Two small, low-risk test-only `data-testid` additions were made to production components (`brief-item-due` on `BriefSectionView`, `proposal-expires` on `ActionProposalPanel`) solely to enable precise masking in the pixel-baseline suite — no visual or behavioral change.
4. `det+anthropic` was not run (no API key configured in this environment — consistent with the repository's standing convention that CI and demo mode never call a real provider).

## Explicit exclusions

No backend, prompt, connector, or policy-engine change of any kind. No new database migration. No change to any approval/execution/audit semantics. No Stage 11 (packaging/commercial base) functionality. Not committed, not pushed, not tagged, per instruction.

## Git state

Working tree on `stage-10-product-design` (branched from `main` @ `e347b75e27399eb353a6d57aa87fe4c2282a803a` / tag `stage-9-complete`) contains all Stage 10 changes, uncommitted. No commit, push, or tag has been made. The index is empty (verified via the exact-boundary security proof above).
