# Stage 11A Phase 6B — Corrected Calendar-Write Trigger Attempt

**Status:** Complete · **Date:** 2026-08-05

Companion: [Phase 6B evidence pack](../evaluation/stage-11/owner-validation/phase-6b/) · [Phase 6 plan](stage-11a-phase-6-plan.md) · [Engineering Acceptance Contract](engineering-acceptance-contract.md)

## Objective

Phase 6 validated the first real Gmail draft write but never validated a real Calendar insertion — no qualifying proposal was ever generated during that phase. This phase repeats only the Calendar-write path, using a dedicated new trigger (P6-CAL-TEST-02) and the Phase 6A/6A.1 split OAuth controls, without repeating the already-passed Gmail draft path.

## Authorised scope

Project owner authorisation: `AUTHORISE A CORRECTED CALENDAR-WRITE TRIGGER ATTEMPT`.

- Owner manually sends P6-CAL-TEST-02 (Account B → Account A).
- Temporarily enable Google connector consent; keep OIDC sign-in disabled throughout.
- Reconnect Account A only; one bounded manual sync.
- Inspect Calendar proposals; approve and execute at most one qualifying insertion.
- Owner verifies the event directly in Google Calendar, then deletes it manually.
- Delete LifeFlow-imported provider data; revoke access; disconnect Account A; restore all flags to safe defaults; prove zero residue.

## Prohibited scope

Google OIDC sign-in; connecting Account B; Gmail draft creation or sending; more than one Calendar insertion; Calendar update/deletion through LifeFlow; altering the CAL-01–CAL-11 fixtures; forcing an unsuitable proposal; automatic retries; the soak period; participant activity; Stage 12; tagging or merging without separate review.

## What happened

A fake-provider rehearsal proved the exact trigger content deterministically produces a complete, insertion-only Calendar-event request before any live reconnection. The owner sent the trigger, Account A was reconnected via connector-consent only, one manual sync ran, and the resulting proposal — checked against every condition of the Calendar acceptance envelope — was approved and executed exactly once. The owner independently verified the correct event in Google Calendar, then deleted it manually. Full cleanup followed: LifeFlow's imported copy of the real sync was deleted via the product's own audited deletion flow, Google access was revoked, Account A disconnected, and every flag restored to its safe default.

Three P3 process/environmental findings surfaced and were closed within the phase (see `defect-register.md`); no P0/P1, and no application code changed.

## Evidence pack

See [docs/evaluation/stage-11/owner-validation/phase-6b/](../evaluation/stage-11/owner-validation/phase-6b/).

## Exit decision

`PASS — FIRST REAL CALENDAR INSERTION VALIDATED`. See [phase-6b-decision.md](../evaluation/stage-11/owner-validation/phase-6b/phase-6b-decision.md).
