# Real-Provider Data Boundary

**Status:** Defined · **Date:** 2026-08-01

Companion: [synthetic-gmail-dataset-plan.md](synthetic-gmail-dataset-plan.md) · [synthetic-calendar-dataset-plan.md](synthetic-calendar-dataset-plan.md) · [test-account-specification.md](test-account-specification.md)

## Permitted

- Account A identity (email, subject) as the connected owner-test account.
- Account B identity as a synthetic correspondent/attendee.
- Fictional email messages matching [synthetic-gmail-dataset-plan.md](synthetic-gmail-dataset-plan.md).
- Fictional calendar events matching [synthetic-calendar-dataset-plan.md](synthetic-calendar-dataset-plan.md).
- Synthetic attendee details (Account B's identity only, never a real third party).
- Exactly one controlled Gmail draft (scenario GM-18, under Decision 2 only).
- Exactly one controlled Calendar insertion (scenario CAL-12, under Decision 2 only).
- Synthetic OAuth tokens belonging only to Account A, encrypted under Phase 4A's `v2` envelope.

## Prohibited

- Personal correspondence (the owner's own real email, from any account).
- Personal calendar events.
- Contacts from a real address book.
- Client information.
- Student information.
- Health information.
- Financial information.
- Employment records.
- Real third-party confidential information.
- Participant information (recruitment remains unauthorised regardless).
- Production secrets.
- Reused passwords (Account A/B credentials must be freshly generated, per [test-account-specification.md](test-account-specification.md)).
- Personal recovery codes.
- Private attachments.

## If prohibited information is introduced accidentally

1. **Stop** whatever action is in progress (per [emergency-stop-plan.md](emergency-stop-plan.md), condition 15).
2. **Remove** the content immediately from the Google account (delete the message/event/attachment at the source, not merely locally).
3. **Check LifeFlow's own ingestion**: if a sync already imported it, run the imported-data deletion operation for the affected `SourceItem`(s) — do not wait for the next scheduled cleanup.
4. **Check evidence documents and screenshots** created since the introduction for any trace of the real content; redact or delete any evidence file that captured it.
5. **Record** the incident in [defect-register.md](defect-register.md) as a P0 (matching "real or confidential information entering the account" in [emergency-stop-plan.md](emergency-stop-plan.md)) — this is a process failure regardless of whether any downstream harm occurred, and must be understood before testing resumes.
6. **Do not** continue with Decision 2 (write) testing until root-caused, even if the immediate content has been removed.

This boundary applies for the lifetime of the two disposable accounts, not only during Phase 4B — it is the standing rule for the entire testing programme through the eventual soak period.
