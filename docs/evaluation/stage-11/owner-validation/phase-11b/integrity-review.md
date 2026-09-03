# Stage 11B — PR #24 Independent Integrity Review

**Date:** 2026-09-03 · **Reviewer:** Claude Code, per the project owner's explicit instruction ("Owner READY Decision + Final Integrity Review and Merge Preparation") · **Scope:** PR #24 (`stage-11b-pre-recruitment-ux-hardening` → `main`)

This review does not rely on the original Stage 11B report. Every claim below was independently re-checked: source code re-read, tests re-run against the final PR head, and every apparent "pre-existing, unrelated" failure independently re-derived rather than taken at face value.

**Note on this review's own methodology (disclosed, not hidden):** an early pass of this review reached a wrong conclusion twice — attributing local `e2e-design` and `e2e/rate-limiting.spec.ts` failures to "pre-existing, date-drift/environment flakiness reproduced identically on `main`." Both "reproductions" shared one real cause: a stray `uvicorn` process left running since 2026-08-24 (earlier in this session) was being silently reused by every local Playwright run instead of a fresh, correctly-configured server. Found and corrected mid-review (§5a, §6) — the true, corrected results are what's reported throughout this document; the flawed intermediate conclusions are not left standing anywhere below.

## 1. Deletion-clarity verification

Re-inspected `apps/web/src/app/connections/page.tsx`, `apps/web/src/app/settings/page.tsx`, `apps/web/src/components/ui/ConfirmButton.tsx` directly (not the earlier report).

- **Comparison table accuracy:** all four rows (Disconnect Google, Delete imported data, Delete learned preferences, Delete account) checked against the actual copy in each control's own descriptive block — consistent. Table wording never implies Gmail/Calendar content is deleted where it isn't: "Delete imported data" and "Delete account" rows explicitly say "(untouched)" next to Gmail/Calendar; "Delete learned preferences" lists Gmail/Calendar under "Keeps."
- **Consequences understandable before action:** each `ConfirmButton`'s `explanation` prop states the consequence and (where applicable) reversibility before the destructive call can fire.
- **Two-step confirmation, structurally verified:** `ConfirmButton.tsx`'s `armed` state defaults to `false`; the `onConfirm` callback is only reachable from the Confirm button rendered inside the `armed === true` branch. A single click can only call `setArmed(true)` — there is no code path from the first click to the destructive action. Verified by reading the component, not just by the passing tests.
- **No implied provider-content deletion:** confirmed by direct text inspection of all three `ConfirmButton` call sites (disconnect, per-item memory delete, delete-all memory) — none claim or imply Gmail/Calendar deletion.
- **No accidental single-click trigger:** same structural verification as above — this is a compile-time-shaped guarantee (the destructive prop is never invoked outside the armed branch), not just a passing-test claim.
- **Mobile layout (390px and other breakpoints):** `e2e-design/responsive.spec.ts`'s "Connections has no horizontal overflow at any breakpoint" and "Settings has no horizontal overflow at any breakpoint" tests check all 5 supported breakpoints (1440/1024/768/390/320) directly against the real rendered page, including the new table and `ConfirmButton` armed states. Both pass. See §4 below for the regression this suite caught and its fix.

**Verdict: verified, no gaps found beyond the wording fix in §2.**

## 2. Outage-guidance verification

Re-inspected the sync-degraded/error notices, Gmail/Calendar partial-read notices, and Today's brief status notices, cross-checked against backend behaviour (`apps/api/src/lifeflow_api/google_sync.py`, `connectors/google_email.py`).

- Every notice states what's unavailable, what remains safe, whether action is needed, and retry guidance — confirmed by direct text inspection.
- **Finding, corrected during this review:** the Gmail/Calendar incomplete-read notices claimed "these specific messages will not be retried automatically on a later sync." This is true for the common case (an incremental sync never re-processes a history entry it has already advanced past) but not exhaustively true — per D38 (`google_email.py`), a full resync (a real, documented mechanism triggered by cursor invalidation) re-lists the entire sync window and could, in a rare case, re-attempt a message that was previously inaccessible only transiently. The claim was corrected to make no assertion about the internal retry mechanism at all: "No action is needed — this isn't something you need to retry yourself." This is true regardless of which sync path a future run takes, and still answers the question that matters (does the owner need to do anything). See commit `1bfd1a5`.
- No other statement in the outage-guidance copy makes a claim the backend cannot prove. The "safe to retry" claim for a retryable sync error is backed by the retry-budget logic itself (a retryable error is, by construction, one where a retry is expected to have a chance of succeeding). The "reconnect if this continues" claim for a non-retryable error matches the actual non-retryable/permanent-failure classification the backend returns.

**Verdict: one real overclaim found and fixed; everything else verified accurate.**

## 3. Uncertain-outcome verification

Re-inspected `apps/web/src/components/ActionProposalPanel.tsx`'s `uncertainOutcomeGuidance` function and its call site.

All five required elements are present, verified against the live source, not the original report:

1. External outcome is unknown: "the outcome is unknown, not failed."
2. Why LifeFlow won't auto-retry: "has not retried it automatically, because retrying an unconfirmed write could create a duplicate" — states the reason, not just the fact.
3. What to independently verify: action-type-specific ("your Gmail Drafts folder" / "your Google Calendar"), confirmed via `action_executors.py` inspection that `create_task` can never reach `uncertain` (it has no external provider call) — the fallback branch is defensive-only.
4. What's safe next: "do nothing else with this proposal until you've checked — approving or executing a new proposal for the same thing before then could create a duplicate."
5. How reconciliation/retry would require a deliberate future action: states honestly that no in-product mechanism exists today, and describes the only current safe manual path (reject; a future brief may surface a fresh proposal if the underlying need still stands, itself a directly-observed behaviour from Phase 10's brief-generation exercise, not a speculative claim).

**No automatic retry, reconciliation, or provider-write behaviour was introduced.** Confirmed by `git diff --stat main..HEAD -- apps/api/src` returning empty at every checkpoint in this review, including after the §2 copy fix. No new backend endpoint, no new `ActionExecution`/`ActionProposal` status value, no change to `action_proposal_service.py`, `retry.py`, or `action_executors.py`.

**The no-auto-retry safety invariant remains unchanged.** `apps/api/tests/test_action_proposals.py`, `test_retry.py`, and `test_stage11a_phase2_uncertain_write_repeatability.py` (51 tests) re-run against the final PR head — all pass. Full backend suite (1058 tests) also re-run — all pass.

**Verdict: verified, no gaps found.**

## 4. Mobile-layout defect review

- **Cause confirmed:** the new deletion-options table's `min-w-lg` (512px minimum width) forced the table wider than the viewport at narrow breakpoints, and the `overflow-x-auto` wrapper's own box was not itself constrained to the viewport, so the overflow leaked to the page level.
- **Reproduction confirmed:** `stage10-outage-notice-fixture.spec.ts`'s responsive breakpoint loop failed with `horizontal overflow at 390px: 182` before the fix (first attempt), `81` after a partial fix (removing `min-w-lg` alone), `0` after the final fix.
- **Root-cause correction confirmed:** `table-fixed` (equal column widths, no content-driven minimum) plus `wrap-break-word` on every cell (forces text to wrap within its fixed column width) — not a superficial suppression of the symptom.
- **Regression coverage confirmed:** `e2e-design/responsive.spec.ts`'s "Connections has no horizontal overflow at any breakpoint" test exercises exactly this table at all 5 breakpoints on every design-suite run; `stage10-outage-notice-fixture.spec.ts`'s breakpoint loop provides a second, independent check via the resilience suite.
- **No horizontal overflow remains:** confirmed by both suites passing at the final PR head, re-run during this review (not merely cited from the original report).
- **No desktop/tablet regression:** the same breakpoint loops cover 1440/1024/768, not just 390/320 — all pass. The `connections.png` visual baseline (full-page screenshot at 1440px) was regenerated and visually inspected during original implementation; re-confirmed passing in this review's design-suite re-run.

**Verdict: genuine defect, correctly root-caused, correctly fixed, regression-covered. Recorded as a real defect found and closed during Stage 11B, not glossed over.**

## 5. Owner walkthrough evidence review

See [owner-walkthrough.md](owner-walkthrough.md), extended during this review with an explicit per-condition breakdown (prior problem / changed experience / owner's actual reaction / whether confusion remains / final status) for full traceability. All three conditions: **CLOSED**, on the owner's own words, not a paraphrase.

One honest methodological limitation, recorded rather than hidden: the disconnect confirm-armed state could not be shown live in the owner's own browser, because the real Account A was already disconnected from Phase 10's teardown and reconnecting it live is explicitly prohibited in this phase's scope. It was instead shown via a screenshot captured through the isolated fake-Google test fixture (the same mechanism `e2e-resilience` already uses) — never a real Google account, and the owner was told this explicitly at the time (see the conversation transcript). This is disclosed, not glossed over.

## 5a. Required-CI-check failures found and fixed during this review

Two genuine, required-CI-check failures were found after pushing this review's own commits — investigated and fixed, not routed around, per the owner's explicit "do not merge with a required check red" instruction:

1. **`Web — lint, types, tests, build` failed at `pnpm web:format:check`.** A gap in this review's own local verification loop, which had run lint/typecheck/test/build but never Prettier's `format:check` specifically. Two files (this review's own incomplete-notice fix, and one already-committed assertion) had manual line-wrapping that didn't match Prettier's canonical wrapping. Fixed with `pnpm --filter @lifeflow/web format`; whitespace-only, confirmed via diff. See commit `1ba6119`.

2. **`E2E — design, accessibility, responsive, visual` failed on `connections.png`, specifically the Linux-platform baseline (`connections-linux.png`).** Root cause: this repository keeps OS-specific visual baselines (`-darwin.png` / `-linux.png`); the original Stage 11B work correctly regenerated and visually verified only the `-darwin.png` variant (the only platform available locally), leaving `-linux.png` stale — still showing the pre-Stage-11B page height (2134px vs. the new 2596px). This is the CI-actual failure; it is **not** the two demo-content date-drift tests reported in §6 below, which CI's real, fresh run does not fail on at all (a correction to this review's own earlier, methodologically-flawed local reproduction — see the note in §6).

   Fixed by generating the true Linux baseline: brought up an isolated, throwaway Postgres/Redis pair and a `mcr.microsoft.com/playwright:v1.61.1-noble` container (matching the pinned `@playwright/test` version and GitHub's `ubuntu-latest` runner family), ran the API and web dev servers inside that container with the same deterministic-clock fixture the CI config already uses (`E2E_TEST_CONTROLS_ENABLED=true`, `DEMO_CLOCK_OVERRIDE=2026-03-15T09:00:00+00:00`), and regenerated only `connections-linux.png` with `--update-snapshots`, scoped to that one test. The resulting image was copied out and visually inspected before accepting (rendered correctly — comparison table, confirm-button copy, no garbled content). The throwaway environment was fully torn down afterward (`docker compose down -v`) — zero residue in the real dev database.

   Two real mistakes were made and corrected during this fix, disclosed rather than hidden: (a) the container's `pnpm install --no-frozen-lockfile` and a Turbopack dev-cache both initially produced misleading results (a stale `NEXT_PUBLIC_API_URL` value baked into the dev cache caused a same-site-cookie/cross-host 401 that had nothing to do with the actual snapshot); resolved by clearing `.next-dev`/`.next` inside the container and confirming the corrected env var via `/proc/<pid>/environ` before retrying. (b) Because the throwaway container bind-mounted the real repository directory, its Linux-native `pnpm install` briefly overwrote host (macOS) native binaries in the shared `node_modules`, breaking the host's own `pnpm --filter web test`. Caught immediately by re-running the host test suite after the container work; fixed with `CI=true pnpm install --frozen-lockfile` plus `pnpm rebuild esbuild unrs-resolver` on the host, and the container's incidental `pnpm-lock.yaml`/`pnpm-workspace.yaml` writes and `.pnpm-store/` were discarded (`git checkout --`, `rm -rf`), never committed. Full host re-verification (lint, typecheck, format:check, build, 109/109 unit tests) confirmed clean afterward.

   A full design-suite run *inside* the same throwaway container additionally showed 6 further "failures" (landing, onboarding ×2, Today, Approvals, Audit history, Settings) — investigated, not assumed meaningful: CI's own real run of the same commit shows these 6 passing (only `connections.png` failed there), so they are artifacts of that container's own accumulated debugging state (multiple manual test runs against the same throwaway database during diagnosis), not real Linux-platform mismatches. Not acted on, to avoid overwriting baselines that are already correct on the real CI platform based on a locally-contaminated environment.

## 6. 24/26 design-suite investigation — corrected during this review

The original Stage 11B report, and this review's own first pass, attributed a locally-observed 24/26 design-suite result to two "pre-existing, date-drift" failures (`Today with a generated brief visual baseline`, `Approvals: a single proposal card visual baseline`), reproduced identically on unmodified `main` and treated as unrelated. **That reproduction was methodologically flawed, and the true root cause is different — corrected here rather than left standing.**

- **What was actually happening:** `playwright.design.config.ts`'s `webServer` entries set `reuseExistingServer: !process.env.CI` — locally (non-CI), if a server is already listening on the target port, Playwright reuses it instead of spawning its own with the suite's deterministic-clock fixture (`E2E_TEST_CONTROLS_ENABLED=true`, `DEMO_CLOCK_OVERRIDE=2026-03-15T09:00:00+00:00`). This session had a `uvicorn` process running continuously **since 2026-08-24** (10 days), left over from earlier Stage 11A/11B work, still listening on port 8010. Every local design-suite run in this session — including both the "main" and "PR head" comparison runs — silently reused that ancient, non-clock-pinned server, so brief/proposal content genuinely drifted by the real host date each time, producing exactly the kind of "date-relative content" pixel diffs both runs showed.
- **Corrected reproduction:** killed every stray `uvicorn`/`next dev` process (`lsof -ti tcp:8010,3000 -sTCP:LISTEN | xargs kill -9`), then re-ran `./scripts/e2e-design.sh` fresh — with no reusable server, Playwright started its own, clock-pinned instance. Result: **25/26 passed**, with `Today` and `Approvals` now passing reliably. The one remaining local failure (`onboarding step 2`, a `/demo/start` timeout) was re-run in isolation and passed — a one-off local flake from this session's extremely heavy back-to-back container/test-suite load, not a real issue.
- **This matches GitHub's actual CI result exactly**: CI's real run of the same commit (a genuinely fresh environment every time, so this reuse bug never manifests there) showed 25 passed, 1 failed — `Today` and `Approvals` were never actually failing on CI at all. The one true, required-check failure was `connections.png`'s stale Linux baseline (§5a above), which the flawed "date-drift" framing had nothing to do with.
- **Why the flawed conclusion didn't cause harm:** no snapshot was changed to paper over `Today`/`Approvals` (they were left alone, correctly, since they were never actually broken); the only baseline touched was `connections-linux.png`, fixed at its real, verified root cause (§5a). The error was in this review's own *diagnosis* — attributing a locally-observed symptom to the wrong cause — not in any action taken as a result of it. Recorded here so the record is accurate, not merely so it reads well.

**Corrected final design-suite result: 25/26 locally (one isolated-flake retry aside), matching CI's real 25/26 result exactly for the tests that were actually failing there; the `connections-linux.png` fix (§5a) is pushed and awaiting CI confirmation as the final required-check result — 0 unexplained failures.**

## 7. Complete verification gate (re-run against the final PR head)

| Gate | Result |
|---|---|
| Frontend unit tests | 109/109 pass |
| Deletion UX tests (`connections/page.test.tsx`, `settings/page.test.tsx`) | Included in the 109; specifically re-inspected — pass |
| Outage/degraded-state tests | Included in the 109; specifically re-inspected — pass |
| Uncertain-outcome tests (`ActionProposalPanel.test.tsx`) | Included in the 109; specifically re-inspected — pass |
| Responsive 390px regression | `e2e-design/responsive.spec.ts` — pass (0 overflow at all 5 breakpoints) |
| Lint (`pnpm web:lint`) | Clean |
| TypeScript (`pnpm web:typecheck`) | Clean |
| Production build (`pnpm web:build`) | Clean |
| Contract checks (`./scripts/generate-contracts.sh`) | No drift — `packages/contracts` unchanged (expected: zero backend changes) |
| Backend suite (`uv run pytest`) | 1058/1058 pass |
| Ruff format/check | Clean |
| mypy | Clean, 94 source files |
| Functional E2E (`./scripts/e2e.sh`) | **10/10 pass** (corrected — see the note below the table) |
| Resilience E2E (`./scripts/e2e-resilience.sh`) | 6/6 pass (all four journeys plus both Stage 10 fixtures) |
| Design/accessibility/responsive/visual E2E (`./scripts/e2e-design.sh`) | 25/26 locally (Today/Approvals confirmed never actually broken); the `connections-linux.png` fix (§5a) is pushed and awaiting CI's next run for final required-check confirmation — see §6 (corrected) |
| pre-commit (`uvx pre-commit run --all-files`) | All hooks pass |
| detect-secrets | Clean (timestamp-only baseline diff discarded each time, per standing practice) |
| Staged Gitleaks (`gitleaks git --log-opts="main..HEAD"`) | No leaks, 4 commits scanned |
| Full-history Gitleaks (`gitleaks git`) | No leaks, 173 commits scanned |
| Private-key detection | Clean (pre-commit hook) |
| Real-email/domain scan | 0 matches in the PR diff |
| Credential/client/project identifier scan | 0 matches (`client_id`, `client_secret`, `project_id`, Google API key/OAuth token shapes) |
| `git diff --check` (main..HEAD) | Clean |
| Google/provider activity | `GOOGLE_OIDC_SIGNIN_ENABLED`/`GOOGLE_CONNECTOR_OAUTH_ENABLED`/`GOOGLE_PROVIDER_WRITES_ENABLED` all `false` at every checkpoint; zero real Google API calls at any point in Stage 11B or this review (the only Google-shaped traffic anywhere in this work was against the isolated fake-Google test server on port 8098, per the existing `e2e-resilience` mechanism) |

### rate-limiting.spec.ts — false alarm, corrected during this review

An earlier pass of this review reported 3 `e2e/rate-limiting.spec.ts` failures as "pre-existing, reproduced identically on unmodified `main`." **That reproduction shared the same root cause identified in §6: a stray `uvicorn` process from earlier in this session (running continuously since 2026-08-24) was being silently reused by every local Playwright run** (`playwright.config.ts`'s `reuseExistingServer: !process.env.CI`), instead of Playwright spawning its own server with the env vars this specific suite requires (`RATE_LIMITING_ENABLED=true`, `RATE_LIMIT_KEY_SECRET`, `RATE_LIMIT_POLICY_OVERRIDES_JSON` — all only set in `playwright.config.ts`'s own `webServer` block). Against that stray, non-rate-limited server, the tests correctly never saw a rate-limit response, and correctly failed waiting for it — a real bug in this review's test hygiene, not in the product.

Re-run properly (stray server killed first, `lsof -ti tcp:8010,3000 -sTCP:LISTEN | xargs kill -9`, confirmed free before invoking the script): **`e2e/rate-limiting.spec.ts` — 3/3 pass. Full `./scripts/e2e.sh` (all 10 functional journeys) — 10/10 pass.** There was never a real failure here, on `main` or on the PR head — both "reproductions" were artifacts of the same contaminated local process, not independent evidence of anything. Recorded honestly rather than left as a false "pre-existing and unrelated" claim.

## 8. Final READY checklist

Every criterion in `owner-validation-exit-template.md`'s READY section, checked against evidence assembled in this review (not re-asserted from the original report):

- All seven named owner-validation exit conditions CLOSED — confirmed: conditions 1–4 (Stage 11A, closed Phase 9/10), conditions 5–7 (Stage 11B, closed and owner-re-verified today, §5 above).
- Zero unresolved P0 — confirmed, unchanged across every phase; nothing in Stage 11B introduced one (§1–4 above).
- Zero unresolved P1 — confirmed, same basis.
- No open P2 remains that meets the template's `CONDITIONAL READINESS` rule — the three P2s that did (deletion clarity, outage guidance, uncertain-outcome guidance) are now closed; the one accuracy issue found in §2 was fixed within this same review, not left open.
- Safety/privacy boundaries remain passed — full backend suite (1058 tests) confirms; zero backend diff; gitleaks/detect-secrets clean.
- Owner core tasks remain completed — no core workflow (brief generation, approval, execution) touched by this PR.
- Uncertain outcomes remain fail-safe — §3 above: no-auto-retry invariant unchanged, backend tests re-confirmed.
- Deletion choices are understandable — §1 above.
- Outage guidance is actionable — §2 above.
- Owner re-verification passed — §5 above, all three conditions, in the owner's own words.
- Recruitment remains NOT AUTHORISED — `recruitment-authorisation-checklist.md` inspected, unchanged; no item marked satisfied.

**This review's independent conclusion matches the recorded decision: READY FOR INDEPENDENT ETHICS AND RECRUITMENT PREPARATION is supported by the evidence**, and the project owner has explicitly accepted it (`owner-validation-exit-template.md`, "Owner decision" section).
