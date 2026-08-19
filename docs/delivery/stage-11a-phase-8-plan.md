# Stage 11A Phase 8 — Closing Phase 7's Open Items and the Stage 11A Exit Decision

**Status:** Complete · **Date:** 2026-08-16–2026-08-19

Companion: [Phase 7 plan](stage-11a-phase-7-plan.md) · [Phase 7 decision](../evaluation/stage-11/owner-validation/phase-7/phase-7-decision.md) · [Stage 11A owner-validation plan](stage-11a-owner-validation-plan.md) · [owner-validation-exit-template.md](../evaluation/stage-11/owner-validation-exit-template.md) · [Engineering Acceptance Contract](engineering-acceptance-contract.md)

## Objective

Phase 7's soak reached `CONDITIONAL PASS` with two named open items: GM-12's stale-follow-up evaluation was never reached, and Google-side revocation could not be objectively confirmed at teardown. Neither is a defect, but both are cheap enough to close outright rather than carry forward indefinitely. Once closed (or explicitly and honestly left open with reasoning, if closing turns out not to be possible in a bounded way), this phase rolls all of Stage 11A's phases (1 through 8) up into the one overall Stage 11A exit decision that `docs/delivery/stage-11a-owner-validation-plan.md` defines but that has never actually been produced — every phase so far only issued its own phase-level verdict.

## Authorised scope

Project owner selected "Close the two open items, then exit Stage 11A" when asked how to interpret `PROCEED TO STAGE 11A NEXT-PHASE PLANNING`.

- **Revocation confirmation**: ask the owner to independently check Google's own connected-apps permissions page and confirm (or personally revoke) LifeFlow's access — this cannot be done from the product side, since the local refresh token was already cleared by Phase 7's disconnect.
- **GM-12 closure, cheapest path first**: reconnect Account A (connector-consent only, same as every prior phase) and attempt a controlled sync immediately. Real time has now passed since GM-12 was originally sent (~2026-08-01) — if either provider's sync cursor happens to have expired into a full resync by now, GM-12 may already be observable without any further wait, and can be evaluated (read-only) in this same session.
- **GM-12 fallback, only if the cheap path doesn't work**: design and rehearse (fake-provider first, exactly as every prior trigger was) a fresh stale-follow-up trigger message, have the owner send it from Account B to Account A, and schedule exactly one follow-up check-in no sooner than 5 days later to evaluate it — read-only, never approved or executed. This is a short, bounded wait, not a repeat of the 10-day soak.
- Once both items are resolved (or, for GM-12, honestly recorded as still not resolved with the reason), produce the Stage 11A exit decision using `owner-validation-exit-template.md`, synthesising all 8 phases into one overall verdict.

## Prohibited scope

`GOOGLE_PROVIDER_WRITES_ENABLED` stays `false` throughout — no proposal is approved or executed, including any GM-12-derived proposal. Account B stays disconnected (it is only ever used as a sender, never connected to LifeFlow). `GOOGLE_OIDC_SIGNIN_ENABLED` stays `false` throughout. No participant recruitment activity, no Stage 12 activity — the Stage 11A exit decision, even at its most positive, is a precondition for *considering* recruitment, never an authorisation of it (per `stage-11a-owner-validation-plan.md`'s own explicit framing, reaffirmed here). No new soak, no repeat of Phase 7.

## What happened

The owner asked, directly, whether the ~5-day wait for a fresh GM-12
trigger to age was actually necessary before Phase 8 could close — a fair
question this plan answers honestly: the wait is a genuine technical
constraint (the detector requires real elapsed time against a real Gmail
timestamp), but it does not need to block Stage 11A's exit, since the
underlying detection logic is already unit-tested independent of any live
Gmail question. The owner then explicitly authorised proceeding with
closure now, treating GM-12 as an explicit, named, deferred condition
rather than a blocker.

Revocation was closed: the owner independently checked Google's own
connected-apps page, found LifeFlow's access genuinely still active
(confirming Phase 7's uncertain result was real, not a masked success),
and removed it directly via Google's interface. GM-12's cheap-path
attempt (immediate reconnect + sync, on the chance enough real time had
already passed) did not work; a fresh trigger (`P8-FOLLOWUP-TEST-01`) was
designed against the actual `detect_follow_ups` logic and sent by the
owner, then explicitly deferred rather than waited on.

The overall Stage 11A exit decision was then produced by synthesising all
8 phases against `owner-validation-success-criteria.md`'s thresholds:
**CONDITIONAL READINESS**, with four named non-safety conditions (GM-12
re-verification, daily-brief-generation-under-real-load never measured
during the soak, no formal owner-usability self-review conducted, and
§D's low-disk-space exercise never run — the last found by directly
checking Phase 2's evidence pack rather than assumed). Zero unresolved
P0/P1 across every phase. `stage-11a-owner-validation-plan.md` (stale
since Phase 4C), `owner-validation-evidence-register.md` (never
populated), and `owner-validation-success-criteria.md` (needed a changelog
entry for two honest scope deviations) were all brought up to date. No
application code changed this phase.

## Evidence pack

See [docs/evaluation/stage-11/owner-validation/phase-8/](../evaluation/stage-11/owner-validation/phase-8/).

## Exit decision

**PASS — BOTH PHASE 7 OPEN ITEMS ADDRESSED.** See
[phase-8-decision.md](../evaluation/stage-11/owner-validation/phase-8/phase-8-decision.md)
for this phase's own decision, and
[owner-validation-exit-template.md](../evaluation/stage-11/owner-validation-exit-template.md)
for the overall Stage 11A exit decision (**CONDITIONAL READINESS**) this
phase produced.
