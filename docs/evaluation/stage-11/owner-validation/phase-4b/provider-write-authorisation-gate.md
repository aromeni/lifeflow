# Provider-Write Authorisation Gate

**Status:** Designed; neither decision made · **Date:** 2026-08-01

Companion: [first-connection-runbook.md](first-connection-runbook.md) · [provider-call-budget.md](provider-call-budget.md) · [first-provider-write-success-criteria.md](first-provider-write-success-criteria.md)

Two distinct future owner decisions exist. **Neither is made by this task.** Approval for Decision 1 must not be treated as implying Decision 2 — they are recorded, dated, and authorised separately.

## Decision 1 — OAuth connection authorisation

**Permits:**
- Connection of Account A (steps 1–25 of [first-connection-runbook.md](first-connection-runbook.md)).
- Storage of its encrypted OAuth credential.
- Read-only Gmail and Calendar smoke tests (`sync`).

**Does not permit:**
- Gmail draft creation.
- Calendar event insertion.
- The owner soak period.

## Decision 2 — first real provider-write authorisation

**Permits, in this exact sequence:**
1. One Gmail draft creation (using scenario GM-18 from [synthetic-gmail-dataset-plan.md](synthetic-gmail-dataset-plan.md)).
2. Verification in Gmail (the owner manually confirms the draft's exact recipient/subject/body in the Gmail UI, not merely LifeFlow's own confirmation).
3. Cleanup of that draft (manual deletion in Gmail).
4. One Calendar event insertion (using scenario CAL-12 from [synthetic-calendar-dataset-plan.md](synthetic-calendar-dataset-plan.md)).
5. Verification in Google Calendar (the owner manually confirms the event's exact title/time/attendees in the Calendar UI).
6. Cleanup of that event (manual removal, or the approved cleanup procedure in [test-account-cleanup-plan.md](test-account-cleanup-plan.md)).

**Does not permit:**
- Gmail send (structurally impossible per [oauth-scope-matrix.md](oauth-scope-matrix.md)'s proof, but stated explicitly here as a policy boundary too).
- Calendar update (structurally impossible, same proof).
- Calendar delete through LifeFlow (structurally impossible, same proof — cleanup of CAL-12 happens manually or through the approved cleanup procedure, never through a LifeFlow delete action, since none exists).
- Repeated or bulk writes — exactly one draft, exactly one event, per [provider-call-budget.md](provider-call-budget.md).
- Personal-account use.
- The owner soak period's commencement.

## Recording an authorisation

Each decision, when made, must be recorded as a dated, explicit statement in a future addendum to this file (or a successor evidence document for the task that executes it) — e.g. "Decision 1 authorised by [owner] on [date]: connect Account A, read-only smoke tests only." A future task inheriting this gate must not infer authorisation from silence, from Decision 1 having been granted, or from this planning document's existence.
