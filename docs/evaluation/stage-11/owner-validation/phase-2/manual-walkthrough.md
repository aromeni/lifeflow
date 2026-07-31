# Stage 11A Phase 2 — Manual Owner Walkthrough

**Status:** Complete · **Date:** 2026-07-31

Companion: [../owner-observation-template.md](../../owner-observation-template.md) · [acceptance-matrix.md](acceptance-matrix.md) (S11A-P2-034)

## Method

`apps/web/e2e-owner-validation/phase2-failure-walkthrough.spec.ts`, run via `scripts/stage11a-phase2-owner-walkthrough.sh` against the real dedicated resilience stack (API :8011 with `GOOGLE_OAUTH_ENABLED=true` redirected to the fake Google server :8098, web :3001) — the same stack the Journey specs use, never the plain demo stack. 5 screenshots were captured and **individually viewed** (not merely asserted-on) to produce the observations below. Every entry is labelled per the required convention.

## Screenshots

1. `01-temporary-outage.png` — a transient Gmail read failure (fail_count=5, exceeding the retry budget) rendered on Connections.
2. `02-reconnection-required.png` — a non-retryable ("permanent_failure") Gmail read failure rendered on Connections.
3. `03-uncertain-gmail-draft.png` — an approved, executed, `hang_on_write`-triggered Gmail draft proposal on the Approvals screen.
4. `04-deletion-preview.png` — the account-deletion preview (danger-treated, phrase-gated) on Connections.
5. `05-restored-normal.png` — Today, fully loaded, with a real generated brief and no degraded notice.

## Owner observations

**OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE**

**1. The temporary-outage and reconnection-required notices are visually and tonally distinct, not just textually.** The temporary outage (screenshot 1) renders in a muted amber `warning`-tone box with a small triangle icon and the words "It is safe to try syncing again in a moment." The reconnection-required state (screenshot 2) renders in a red `danger`-tone box with an X icon and "Retrying now will not help — reconnect Google if this continues." Seeing these side by side (not just reading the assertion that `role="alert"` differs from `role="status"` in the code) makes it obvious a user would never confuse "try again later" with "this needs my action" — the visual weight matches the actual urgency.

**2. The uncertain-execution card is the single clearest safety artefact in the whole product.** Screenshot 3 shows, on one card: a distinct amber "EXECUTION OUTCOME UNCERTAIN" pill placed directly under the action title (before you even scroll to the outcome section), the exact approved payload still fully visible and readable (recipient, subject, body — nothing hidden or collapsed once uncertainty occurs), a green "Approved exact payload" block showing the binding hash unchanged, and then a clearly separated "Outcome uncertain — not retried automatically" panel with the plain-language warning "We could not confirm this action completed. It has not been retried automatically — check directly with the provider before assuming either outcome." There is no Execute button anywhere on this card anymore. An owner reading this needs no engineering background to understand exactly what LifeFlow does and does not know.

**3. The account-deletion preview correctly treats "will be deleted" and "will be kept" as equally important information, not just a scary warning.** Screenshot 4 shows both lists with the same visual weight — "Will be deleted" (4 rows with counts) directly above "Will be kept (content-free)" (3 rows with counts) — before the destructive confirmation control appears at all. This matters specifically in a failure-recovery context: an owner who arrives at this screen worried about data loss during an outage can see precisely what's at stake before typing the confirmation phrase, not after.

**4. The "restored normal operation" screen genuinely shows no trace of the preceding failures.** Screenshot 5, captured after fixing a real screenshot-timing race (the first attempt caught "Loading your brief…" mid-fetch), shows a complete, ordinary Today dashboard — a real generated brief, one needs-attention item with full evidence and confidence detail, and critically, zero leftover degraded-notice, zero stale error banner, zero visual residue from the temporary-outage or reconnection-required states shown seconds earlier in the same session. Recovery is not just functionally correct (confirmed by the automated suite) — it is also invisible to the owner once it has happened, which is the right UX outcome for a transient failure.

**5. The walkthrough could not exercise the Calendar uncertain-write path visually within existing seed tooling, and that gap was worth noticing rather than silently working around.** Building this walkthrough surfaced that `e2e_google_support.py` (existing Stage 9 test-support code) only seeds a Gmail-sourced item, so there is currently no lightweight way to *visually* inspect the Calendar equivalent of screenshot 3 without either extending shared test infrastructure or writing new Python seeding logic. The automated proof (10 cycles, `test_stage11a_phase2_uncertain_write_repeatability.py`) is not in question — the UI rendering is provably identical code (the same `execution-result` component, same copy pattern) — but this is worth flagging as a real, if minor, gap in the *manual-inspection* tooling for a future phase, separate from the underlying safety guarantee.

## What this walkthrough does not claim

It does not claim to be a certification of accessibility, cross-browser behaviour, or production performance. It does not involve a participant, a real Google account, or any data beyond synthetic/fake-provider fixtures. It is one owner's observation of one session against one local environment, recorded for engineering judgement, never for statistical comparison against future participant feedback.
