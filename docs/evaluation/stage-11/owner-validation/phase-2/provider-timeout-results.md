# Stage 11A Phase 2 — Provider Timeout Results

**Status:** Complete · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) (S11A-P2-018 to 019) · [defect-register.md](defect-register.md) (real-distinction finding)

## The real distinction (read this before the tables below)

The governing task framed "timeout before write acceptance" and "accepted-but-unconfirmed write" as two outcomes to keep separate. Reading `action_executors.py` directly showed the product's actual, deliberate design collapses any transient failure touching the write call itself into a single `uncertain` outcome — it never assumes a write "definitely didn't happen" merely because the local client didn't confirm it, since it cannot know that. The real, tested distinction is:

1. **Refused before any provider call was attempted** — a failure in token/context/authorisation checks, strictly before the network call to Gmail/Calendar is made. Classified `FinalExecutionError` → `failed`, disclosed, never retried.
2. **The write call was made and something about it could not be confirmed** — classified `uncertain`, never retried, requires a fresh human-approved proposal (not a system retry) to try again.

## Timeout before write acceptance (S11A-P2-018)

| Action type | Repetitions | Result | Evidence |
|---|---|---|---|
| Gmail draft | 5 | PASS — disclosed `failed`, "No external action was attempted," never retried, registry never invoked twice | `test_five_refused_before_call_cycles_are_disclosed_not_uncertain[create_gmail_draft]` |
| Calendar event | 5 | PASS — same | `test_five_refused_before_call_cycles_are_disclosed_not_uncertain[create_calendar_event]` |

## Accepted-but-unconfirmed write (uncertain) (S11A-P2-019)

| Action type | Repetitions | Result | Evidence |
|---|---|---|---|
| Gmail draft | 10 | PASS — uncertain, zero auto-retry, no re-offered Execute control, exact payload stays visible, restart never replays, exactly one execution record across a repeat call | `test_ten_uncertain_write_cycles_never_duplicate_or_replay[create_gmail_draft]` |
| Calendar event | 10 | PASS — same | `test_ten_uncertain_write_cycles_never_duplicate_or_replay[create_calendar_event]` |

Both also independently confirmed via the real fake-Google-server `hang_on_write` mechanism at the process level: `journey-b-uncertain-write.spec.ts` (real API restart) re-run 3× this phase, and via the manual owner walkthrough's screenshot 3 (`manual-walkthrough.md`), which shows the exact rendered "Outcome uncertain — not retried automatically" state for a real Gmail draft.

## Audit History truthfulness

Every cycle's audit trail was inspected: `proposal.executing` → `execution.started` → `execution.uncertain` (or `execution.failed` for the before-call case) appear in order, with no fabricated `execution.succeeded` event ever recorded for an outcome that was not confirmed.
