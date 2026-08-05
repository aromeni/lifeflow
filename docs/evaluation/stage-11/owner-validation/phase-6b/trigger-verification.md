# Stage 11A Phase 6B — Trigger Verification

**Date:** 2026-08-05

## Trigger sent

Owner confirmed: `P6-CAL-TEST-02 SENT` (Account B → Account A).

## Actual wording vs. suggested wording

The owner's actual subject/body differed in minor wording from the exact text suggested (an extended subject line, no `called "..."` title phrase), but retained every deterministically-required element: the scheduling intent cue, the full date with matching weekday, an explicit start/end time, an explicit `Europe/London` timezone string, and the "invite me" self-attendee cue. Re-running the same parser (`scheduling_phrases.parse_scheduling_request`) against the actual stored subject and body confirmed:

- `has_intent`: true
- extracted date/time: 13 August 2026, 14:00–14:30
- `timezone`: Europe/London
- `missing`: none
- exactly one attendee, added via the `sender_as_attendee` reason code (never a literal address typed into the body)
- executable against the real reference clock: true

No repository evidence contains the raw subject, body, or sender address — only the structural pass/fail facts above.

## Traceability

The resulting Calendar proposal's title and description both reference "P6-CAL-TEST-02", confirmed traceable from source item → signal → proposal.
