# First-Provider-Write Success Criteria

**Status:** Defined; not yet evaluated against a real write · **Date:** 2026-08-01

Companion: [provider-write-authorisation-gate.md](provider-write-authorisation-gate.md) · [provider-call-budget.md](provider-call-budget.md)

**This document does not authorise the writes it describes criteria for.** Decision 2 in [provider-write-authorisation-gate.md](provider-write-authorisation-gate.md) is a separate, future, explicit owner decision.

## Gmail

For the future separately-authorised test using scenario GM-18:

- The exact draft payload (recipient, subject, body) is visible to the owner before creation — matching LifeFlow's existing approval-preview requirement for any Gmail-draft `ActionProposal`.
- The exact account (Account A) is visible.
- Approval is bound to the exact payload, its version, and the account — a later edit invalidates a prior approval (existing policy-engine behaviour, unchanged by this phase).
- Exactly one draft is created.
- No email is sent (structurally proven absent in [oauth-scope-matrix.md](oauth-scope-matrix.md)).
- A duplicate request (e.g. a retried approval) creates no second draft — existing idempotency-key behaviour.
- An uncertain outcome (e.g. a timeout) is not automatically retried (per [provider-call-budget.md](provider-call-budget.md)).
- Audit History records the action truthfully (draft created, exact scope, no send).
- The draft is manually deleted during cleanup, and the deletion is confirmed in Gmail directly.

## Calendar

For the future separately-authorised test using scenario CAL-12:

- The exact insertion payload (title, time, attendees) is visible to the owner before creation.
- Timezone and attendees are shown explicitly, not inferred silently.
- Notification behaviour is explicit (`sendUpdates=none`, per the existing implementation) and stated to the owner before approval, not left ambiguous.
- Exactly one event is inserted.
- No existing event is edited (structurally proven absent).
- No existing event is deleted (structurally proven absent).
- A duplicate request creates no second event — existing idempotency-key behaviour.
- An uncertain outcome is not automatically retried.
- Audit History records the action truthfully.
- The event is removed manually (in Google Calendar directly) or through the approved cleanup procedure — never through a LifeFlow delete action, since none exists.

## What this document does not do

It defines the bar a future Decision-2 write test must clear. It does not perform, schedule, or pre-approve either write, and it does not itself constitute Decision 2.
