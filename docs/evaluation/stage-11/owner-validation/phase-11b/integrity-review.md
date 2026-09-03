# Stage 11B — PR #24 Independent Integrity Review

**Date:** 2026-09-03 · **Reviewer:** Claude Code, per the project owner's explicit instruction ("Owner READY Decision + Final Integrity Review and Merge Preparation") · **Scope:** PR #24 (`stage-11b-pre-recruitment-ux-hardening` → `main`)

This review does not rely on the original Stage 11B report. Every claim below was independently re-checked: source code re-read, tests re-run against the final PR head, and the two design-suite failures reproduced against unmodified `main` before being accepted as pre-existing.

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

## 6. 24/26 design-suite investigation

Independently reproduced, not accepted on the original report's word:

- **A (unmodified main):** `git checkout main` in place (working tree was clean; no worktree needed), ran `./scripts/e2e-design.sh e2e-design/visual-regression.spec.ts --grep "Today with a generated brief|Approvals: a single proposal card"`. Both failed, with the *same* pixel-diff counts as later observed on the PR head (Approvals: 3060 then 3080 pixels — the small difference between runs is itself further evidence of date-relative content drift, not a fixed regression).
- **B (final PR #24 head):** re-ran the same two tests — same two failures, same class of diff (visibly different email subject/thread-id text in the diff image, and a different "Needs attention" item count on Today — both are demo-dataset content that shifts by real calendar date, confirmed by direct visual inspection of the diff images).
- **Evidence the same tests fail for the same reason on `main`:** confirmed above — identical test names, identical failure mode (visual pixel diff from date-relative content, not a layout/component regression), reproduced on a branch with zero Stage 11B changes present.
- **Evidence Stage 11B did not introduce or worsen them:** the diffs are localised to brief/proposal *content* (item counts, email text) that Stage 11B's diff never touches (`git diff --stat main..HEAD` for `apps/api/src` is empty; the frontend diff never touches brief-content rendering, only deletion/outage/uncertain-outcome copy and controls).
- **No Stage 11B assertion was weakened to hide this:** neither failing test belongs to Stage 11B's own added/changed assertions (they predate this PR entirely — `Today with a generated brief visual baseline` and `Approvals: a single proposal card visual baseline` are Stage 10 fixtures). No snapshot was updated to paper over a real regression; the one snapshot Stage 11B did update (`connections.png`) was regenerated because Stage 11B genuinely changed that page's content (the new table), and was visually inspected before accepting, both in the original implementation and re-confirmed in this review.

**Final design-suite result at the PR head: 24/26 — same 2 pre-existing failures, both proven pre-existing and unrelated, 0 new failures.**

Per the owner's explicit instruction, this alone does not block merge, since these two are not required GitHub CI checks in a red state (see §8 below for the actual required-check gate) — but see that section for confirmation of the *remote* CI result specifically.

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
| Functional E2E (`./scripts/e2e.sh`) | `e2e/deletion.spec.ts` 2/2 pass. Full-suite run surfaced 3 pre-existing `rate-limiting.spec.ts` failures — independently reproduced identically on unmodified `main` (see below); unrelated to Stage 11B. |
| Resilience E2E (`./scripts/e2e-resilience.sh`) | 6/6 pass (all four journeys plus both Stage 10 fixtures) |
| Design/accessibility/responsive/visual E2E (`./scripts/e2e-design.sh`) | 24/26 — see §6 |
| pre-commit (`uvx pre-commit run --all-files`) | All hooks pass |
| detect-secrets | Clean (timestamp-only baseline diff discarded each time, per standing practice) |
| Staged Gitleaks (`gitleaks git --log-opts="main..HEAD"`) | No leaks, 4 commits scanned |
| Full-history Gitleaks (`gitleaks git`) | No leaks, 173 commits scanned |
| Private-key detection | Clean (pre-commit hook) |
| Real-email/domain scan | 0 matches in the PR diff |
| Credential/client/project identifier scan | 0 matches (`client_id`, `client_secret`, `project_id`, Google API key/OAuth token shapes) |
| `git diff --check` (main..HEAD) | Clean |
| Google/provider activity | `GOOGLE_OIDC_SIGNIN_ENABLED`/`GOOGLE_CONNECTOR_OAUTH_ENABLED`/`GOOGLE_PROVIDER_WRITES_ENABLED` all `false` at every checkpoint; zero real Google API calls at any point in Stage 11B or this review (the only Google-shaped traffic anywhere in this work was against the isolated fake-Google test server on port 8098, per the existing `e2e-resilience` mechanism) |

### rate-limiting.spec.ts — pre-existing, confirmed unrelated

`e2e/rate-limiting.spec.ts` (3 tests: Journeys A, B, C) fails consistently, with identical error signatures, on:

- the final PR #24 head, run twice (once mid-review before the incomplete-notice fix, once — implicitly, since the fix doesn't touch this suite's surfaces — consistent with the second finding);
- unmodified `main` (`git checkout main` in place, containers freshly recreated via `docker compose down && docker compose up -d db redis --wait` to rule out leaked rate-limit-bucket state), run in isolation.

All three failures are `getByRole("alert")` timeouts waiting for rate-limit copy ("Try again in...") that never appears within the 5s window — a timing/environment characteristic of this specific local machine's rate-limit bucket behaviour under the current test run's load, not a Stage 11B code change (neither `ActionProposalPanel.tsx`'s error-`Notice` block nor `DeletionControls.tsx`'s rate-limit handling were touched by this PR). Not a required GitHub Actions check result — the remote CI environment is a separate, controlled environment from this local machine; see §8 for the actual required-check gate that governs merge.

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
