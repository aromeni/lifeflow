# Stage 11A Phase 6B — Approval Evidence Against the Calendar Acceptance Envelope

**Date:** 2026-08-05

Every condition from the governing instruction's §7 envelope, checked against the exact approval preview shown to the owner before approval:

| Condition | Result |
|---|---|
| Action type is Calendar insertion | **Met** — "Create calendar event" |
| Linked to P6-CAL-TEST-02 | **Met** — title and description both reference it |
| Creates a new event (not an update) | **Met** — UI explicitly labelled "Real Calendar — creates an event" |
| Date is 13 August 2026 | **Met** |
| Time is 14:00–14:30 | **Met** |
| Timezone is Europe/London | **Met** |
| Account B is the only attendee | **Met** — exactly one attendee shown |
| Guest notifications disabled | **Met** — UI explicitly stated "Guest notifications: off ... never emails attendees" |
| Exact payload visible | **Met** — full "Exact approval preview" shown before approval, including canonical JSON and hash |
| Exact connected account visible | **Met** — only one real Google account existed to execute against, unambiguous |
| Proposal version visible | **Met** — version 1 |
| No existing event modified | **Met** — insertion-only action type |
| No CAL-01–CAL-11 fixture targeted | **Met** — this creates a brand-new event, never references an existing event ID |
| Content entirely fictional | **Met** — "Northstar follow-up" is the controlled fictional test title |
| No unexpected field or attendee | **Met** — exactly the fields above, one attendee |

No proposal was forced, edited, or approved outside this exact envelope. Approval was recorded with `execution_context: real (Google)` and a binding hash, confirming the approval was cryptographically tied to this exact payload.
