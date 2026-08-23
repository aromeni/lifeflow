# Stage 11A Phase 9 — Decision

**Date:** 2026-08-23

## Summary

Six days after `P8-FOLLOWUP-TEST-01` was sent, Account A was reconnected,
synced, and briefed. The fresh trigger imported correctly into its
`sent` folder, and `detect_follow_ups` correctly identified it as an
unanswered follow-up (`reason_codes: ["no_reply_6d"]`, confidence 0.85) in
the generated brief's `waiting_for` section — confirming real Gmail's
`SENT`/`INBOX` labels and thread IDs propagate correctly through the real
connector into the exact shape the detector expects. Full teardown
completed and independently re-verified as zero-residue.

## Requirements met

- Trigger imports with `folder: "sent"` — **met**.
- No reply present in the trigger's own thread — **met**, confirmed by
  distinct thread IDs, not merely assumed.
- Follow-up `Signal` correctly identifies the trigger via real Gmail data
  — **met**.
- No proposal or execution touches the real connected account beyond what
  already existed from Phase 6B — **met**; the two new proposals this
  brief generated both trace to the synthetic demo dataset instead.
- `GOOGLE_PROVIDER_WRITES_ENABLED` stayed `false` throughout — **met**.
- Full teardown, zero residue — **met**: 0 source items, 0 signals, 0
  stored credentials, `revocation_confirmed: true`, readiness 19/19 PASS.

## Decision

**PASS — GM-12'S DEFERRED CONDITION CLOSED.**

This closes the one condition `phase-8/gm12-deferral.md` explicitly
carried forward from the Stage 11A exit decision. It does not, on its
own, upgrade Stage 11A's overall exit decision from `CONDITIONAL
READINESS` — the other three named conditions (daily brief generation
under real elapsed time not measured during the 10-day soak itself, no
formal owner-usability self-review, Phase 2's low-disk-space exercise
never run) remain open and are unaffected by this phase. See
[owner-validation-exit-template.md](../../owner-validation-exit-template.md)
for whether/when to revise the overall verdict once — or if — those are
also addressed.

Does not authorise recruitment or Stage 12.
