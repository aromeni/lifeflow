# Stage 11A Phase 7 — 10-Day Owner-Only Soak

**Status:** Complete · **Started:** 2026-08-05T22:46:02Z (T0) · **Completed:** 2026-08-16 (257.9 hours elapsed)

Companion: [daily-checklist.md](../evaluation/stage-11/owner-validation/phase-7/daily-checklist.md) · [soak-daily-log.md](../evaluation/stage-11/owner-validation/phase-7/soak-daily-log.md) · [soak-period-decision.md](../evaluation/stage-11/owner-validation/phase-4b/soak-period-decision.md) · [Engineering Acceptance Contract](engineering-acceptance-contract.md)

## Objective

Every prior Stage 11A phase (1 through 6B) validated LifeFlow's behaviour in short, single-session windows. None has run the product against a real, live Google connection for an extended, unattended period. This phase does that: a single real Google account (Account A only) stays connected for at least 240 continuous wall-clock hours, under daily read-only observation, to validate resource/queue/database/Redis stability over time, duplicate-free repeated syncing, the previously-undecided 7-day Testing-status token-expiry boundary (see [soak-period-decision.md](../evaluation/stage-11/owner-validation/phase-4b/soak-period-decision.md)), and GM-12's stale-follow-up evaluation once it is genuinely old enough to qualify.

## Authorised scope

Project owner authorisation: `AUTHORISE A 10-DAY STAGE 11A OWNER-ONLY SOAK`.

- Soak duration: at least 240 hours from the recorded Google consent timestamp (T0).
- One controlled, owner-triggered, read-only sync per day (never automatic — see "Operating model" below).
- Resource, queue, database and Redis stability measurements each day.
- Duplicate SourceItem, Signal and proposal checks each day.
- GM-12 stale-follow-up evaluation once it is genuinely 5+ days old (read-only observation only — never approval or execution).
- Deliberate observation of the Google Testing-status 7-day token boundary, and a controlled reconnection and recovery when it occurs — this phase exercises **Option A** from [soak-period-decision.md](../evaluation/stage-11/owner-validation/phase-4b/soak-period-decision.md) (Testing-status re-authorisation cadence), not Option B (production publishing/verification), which remains unselected and out of scope.
- Bounded authentication-failure and retry-behaviour verification.
- Final data deletion, revocation, disconnection and zero-residue verification at soak end.

## Prohibited scope

`GOOGLE_PROVIDER_WRITES_ENABLED` stays `false` for the entire phase — no proposal is approved or executed at any point, including for GM-12. Account B stays disconnected throughout. `GOOGLE_OIDC_SIGNIN_ENABLED` stays `false` throughout. No participant or Stage 12 activity. No unattended script or cron job touches the live credential — see "Operating model" below for why, and for the explicit trade-off this phase accepts.

## Operating model

Two operational questions were put to the project owner before this phase began, because neither has a safe default:

1. **Daily trigger.** This phase's own scheduling tooling (in-session cron/wakeups) cannot reliably run unattended for 240 hours — jobs are session-bound and auto-expire well before 10 days are up. The owner chose **owner-triggered daily check-ins**: roughly once every 24–36 hours, the owner resumes the conversation and the day's sync, stability checks, and duplicate checks are run live, inside an attended, audited turn — deliberately not automated onto an unattended local script, to keep every touch of the live credential inside the human-in-the-loop model this project is built around. Gaps longer than a day between check-ins are tolerated; they are logged as observed gaps, not failures, and do not restart the soak clock (T0 is anchored to the Google consent timestamp, not to check-in cadence).
2. **Uptime model.** The owner chose **best-effort local uptime, gaps documented**. The local Docker/API stack is not expected to run continuously for 10 unattended days on a laptop; any gap in local availability is logged as such, distinct from the Google-side 7-day token clock (which runs regardless of local uptime).

## What happened

The soak ran 257.9 hours (10.75 days) from T0, with an owner-triggered
check-in roughly once a day. Every check-in ran the same daily protocol:
flag/process verification, a stability snapshot, one controlled read-only
sync, and duplicate/write checks — all zero duplicates and zero new writes,
every single day. Several genuine local-environment gaps occurred (Docker/
DB/Redis outages, most likely the host sleeping or rebooting) and
self-recovered cleanly every time with no flag drift and no data loss. The
headline event was the Google Testing-status 7-day refresh-token boundary
(Day 7): the token expired, the app correctly returned a single non-retried
`409` rather than looping, and Account A was reconnected under a
controlled, independently-verified procedure without resetting the soak
clock. GM-12's stale-follow-up evaluation was never reached — the fixture
mail's local copy had already been deleted before this soak began, and
neither provider's incremental-sync cursor happened to expire into a full
resync during the window, so it was never re-imported; forcing this was
considered and deliberately rejected (see `phase-7-decision.md`). Full
teardown (imported-data deletion, disconnect, flag restoration) completed
cleanly at soak end; Google-side revocation could not be objectively
confirmed this time (network/non-200, indistinguishable), though local
credentials are verifiably fully cleared regardless. Decision:
**CONDITIONAL PASS — 10-DAY SOAK COMPLETE, TWO NAMED OPEN ITEMS, NO
BLOCKING DEFECTS.** Does not authorise Stage 12 or participant recruitment.
See [stage-11a-phase-6b-plan.md](stage-11a-phase-6b-plan.md) for the prior
phase and [docs/evaluation/stage-11/owner-validation/phase-7/](../evaluation/stage-11/owner-validation/phase-7/)
for the full evidence pack.

## Evidence pack

See [docs/evaluation/stage-11/owner-validation/phase-7/](../evaluation/stage-11/owner-validation/phase-7/).

## Exit decision

`CONDITIONAL PASS — 10-DAY SOAK COMPLETE, TWO NAMED OPEN ITEMS, NO BLOCKING
DEFECTS`. See [phase-7-decision.md](../evaluation/stage-11/owner-validation/phase-7/phase-7-decision.md).
