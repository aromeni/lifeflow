# Stage 11A Phase 9 — GM-12 Fresh-Trigger Follow-Up

**Status:** Complete · **Date:** 2026-08-23

Companion: [Phase 8 plan](stage-11a-phase-8-plan.md) · [GM-12 deferral](../evaluation/stage-11/owner-validation/phase-8/gm12-deferral.md) · [Fresh-trigger design](../evaluation/stage-11/owner-validation/phase-8/gm12-fresh-trigger-design.md) · [Engineering Acceptance Contract](engineering-acceptance-contract.md)

## Objective

Close the one condition Phase 8 explicitly deferred rather than forced: whether real Gmail's `SENT`/`INBOX` labels and thread IDs propagate correctly through the real connector into the shape `detect_follow_ups` (`detectors.py:405-440`) expects. The fresh trigger (`P8-FOLLOWUP-TEST-01`) was sent 2026-08-17; today (2026-08-23) it is 6 days old, past the detector's 5-day threshold.

## Authorised scope

Continuation of the condition named in `gm12-deferral.md` — the owner asked to check it now that the date has arrived.

- Reconnect Account A (connector-consent only, same four scopes).
- One controlled sync — confirm the trigger imports as a `SourceItem` with `metadata_json.folder == "sent"`.
- Generate one brief (read-only composition) — the step that actually runs `detect_follow_ups`.
- Confirm (or honestly record the absence of) a follow-up `Signal` referencing the trigger item.
- Full teardown: imported-data deletion, disconnect, revoke, zero-residue verification.

## Prohibited scope

`GOOGLE_PROVIDER_WRITES_ENABLED` stays `false` throughout — any proposal the brief composes (e.g. a `create_gmail_draft` suggestion) is left exactly as `proposed`, never approved or executed. Account B stays disconnected. `GOOGLE_OIDC_SIGNIN_ENABLED` stays `false`. No participant or Stage 12 activity.

## What happened

Account A was reconnected (`authorisation_revision` 5→6), synced (the
trigger imported correctly with `folder: "sent"`), and briefed. The
trigger appeared in the generated brief's `waiting_for` section as a
`follow_up` signal with `reason_codes: ["no_reply_6d"]` — an exact match
for the real six days elapsed — confirming real Gmail's `SENT`/`INBOX`
labels and thread IDs propagate correctly through the real connector into
the shape `detect_follow_ups` expects. A second, unrelated real message
also arrived during the wait; its distinct thread ID confirmed it was not
a reply, so the trigger's "no reply" condition was never at risk. Two new
proposals appeared in the same brief, both tracing to the synthetic demo
dataset rather than the real trigger — nothing needed to be left
deliberately untouched on the real account beyond what already existed.
Full teardown (imported-data deletion, disconnect, revoke) completed and
was independently re-verified as zero-residue; `GOOGLE_PROVIDER_WRITES_ENABLED`
was never touched.

## Evidence pack

See [docs/evaluation/stage-11/owner-validation/phase-9/](../evaluation/stage-11/owner-validation/phase-9/).

## Exit decision

**PASS — GM-12'S DEFERRED CONDITION CLOSED.** See
[phase-9-decision.md](../evaluation/stage-11/owner-validation/phase-9/phase-9-decision.md).
This closes one of the four conditions named in Stage 11A's
`CONDITIONAL READINESS` exit decision; the other three remain open and
unaffected.
