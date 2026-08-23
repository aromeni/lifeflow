# Stage 11A Phase 10 — Closing the Remaining Three Exit Conditions

**Status:** In progress · **Date:** 2026-08-24

Companion: [Phase 8 plan](stage-11a-phase-8-plan.md) · [Phase 9 plan](stage-11a-phase-9-plan.md) · [owner-validation-exit-template.md](../evaluation/stage-11/owner-validation-exit-template.md) · [Engineering Acceptance Contract](engineering-acceptance-contract.md)

## Objective

Address the three remaining non-safety conditions from Stage 11A's `CONDITIONAL READINESS` exit decision (Phase 9 already closed the fourth, GM-12). Each condition has a different shape and is handled differently, not forced into one uniform procedure:

1. **§D's low-disk-space failure/recovery exercise** — a self-contained, fully local technical exercise. No owner interaction and no real Google connection needed.
2. **Daily brief generation under real elapsed time** — requires a real, owner-attended, multi-day connection to Account A, generating a brief once a day and confirming stable, consistent output. Shorter than the 10-day soak (the exit template calls for "at least several real days," not a repeat of the full soak), but genuinely spans real calendar days — cannot be compressed into one session.
3. **Formal owner-usability self-review (§F)** — genuinely requires the project owner's own subjective judgement (onboarding clarity, Today scanability, priority relevance, evidence usefulness, approval comprehension, deletion-choice clarity, outage guidance, uncertain-outcome guidance, navigation/responsive behaviour, recurring friction). Claude cannot honestly fabricate the owner's opinions on these dimensions. What Claude *can* do is consolidate the friction already documented across phase defect registers (D-6B-02, D-6B-03, Turbopack cache contamination, the Phase 7/8/9 revoke-token intermittency) into the prescribed labelled format — clearly marked as inferred-from-defect-records, not owner-observed — and ask the owner whether they want to add genuine fresh observations for the remaining, purely subjective dimensions.

## Authorised scope

Continuation of the project owner's "continue with the remaining conditions" instruction, following the merge of Phase 9.

- Design and run a bounded, reversible low-disk-space exercise against an isolated, throwaway Docker volume — never the host machine's real disk, never the persistent dev database.
- Reconnect Account A (connector-consent only) for the brief-generation exercise; owner-triggered daily check-ins, same operating model as Phase 7 (owner-attended, best-effort uptime), for a shorter, explicitly bounded number of days.
- Consolidate existing documented friction into `owner-observation-template.md`'s format, clearly labelled by source; ask the owner directly whether they want to contribute further genuine observations before this condition is considered closed.
- Update the Stage 11A exit decision again as each condition closes, exactly as Phase 9 did — never batch silent updates.

## Prohibited scope

`GOOGLE_PROVIDER_WRITES_ENABLED` stays `false` throughout — any proposal a generated brief composes is left exactly as `proposed`, never approved or executed. Account B stays disconnected. `GOOGLE_OIDC_SIGNIN_ENABLED` stays `false`. No participant or Stage 12 activity. The low-disk-space exercise never touches the host machine's real available disk space or the persistent dev database/Redis volumes.

## What happened

_Filled in as each condition closes._

## Evidence pack

See [docs/evaluation/stage-11/owner-validation/phase-10/](../evaluation/stage-11/owner-validation/phase-10/).

## Exit decision

_Recorded per-condition as each closes; overall Stage 11A verdict revisited once all three are addressed._
