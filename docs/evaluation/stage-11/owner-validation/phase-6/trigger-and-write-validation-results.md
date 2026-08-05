# Stage 11A Phase 6 — Trigger and Write Validation Results

**Date:** 2026-08-05

## Gmail draft (P6-GM-TEST-01)

### Attempt 1 — ranking artifact, then a real defect found

After sync, exactly one `create_gmail_draft` proposal existed (LifeFlow's "one active proposal per action type" policy), but it was linked to a different, organic dataset message, not P6-GM-TEST-01 — verified directly by comparing the proposal's `source_refs` against P6-GM-TEST-01's actual `SourceItem` external ID, not assumed from the UI. Root cause: P6-GM-TEST-01's signal was exactly tied on both real ranking criteria (priority score, due timestamp) with the active one, losing only an arbitrary string tiebreak.

**Corrective action taken (explicitly permitted — rejecting is not approving):** the owner rejected the wrong-trigger proposal and regenerated the brief. The next-ranked candidate — confirmed via direct query to be P6-GM-TEST-01's own signal — became the new active proposal. The owner approved and executed it.

**Execution result: `uncertain`, not `succeeded`.** The Gmail API write itself succeeded (confirmed via the `create_draft` provider-call metric), but LifeFlow's own independent re-verification (re-fetching the draft and comparing byte-for-byte against the approved payload) found the stored subject was missing the "Re: " prefix the approved payload specified. Per the project's core safety rule, this execution was **never retried** — it remains a permanent, immutable `uncertain` record. The owner independently verified in Gmail's own UI: recipient and body matched exactly; only the subject prefix differed.

**Root cause, confirmed via code inspection:** creating a Gmail draft with a `thread_id` can make Gmail canonicalise the stored subject to the thread's own subject line, dropping the added "Re: " — the same class of Gmail-controlled threading decision the code already exempts for `thread_id` itself, just not extended to the coupled subject field. See `defect-register.md`'s D-6-01 for the fix.

### Attempt 2 — clean success, confirming the fix

After the fix (PR #17, merged to `main` at `0eb94c4`) was deployed and the server restarted, a fresh dedicated trigger message was sent and the cycle repeated: sync → new `create_gmail_draft` proposal (verified linked to the new message, not a stale one) → approved → executed.

**Result: `succeeded`.** `result_json`: `{"status": "created", "draft_id": "...", "message_id": "...", "thread_id": "...", "message": "Gmail draft created; no email was sent."}`. Exactly one `create_draft` provider call recorded (metric-verified). The owner independently verified the exact recipient/subject/body in Gmail's own UI before deleting it.

## Calendar event (P6-CAL-TEST-01)

**Zero `create_calendar_event` proposals were generated at any point.** Root cause identified by code inspection, not guessed: the calendar-proposal path (`_scheduled_event_candidate`) uses a deterministic parser (`parse_scheduling_request`) that requires an unambiguous date, start time, duration/end, and attendees extracted directly from the email text — "nothing is guessed," per the code's own docstring. A `schedule_request`-type signal *was* detected for P6-CAL-TEST-01 (confidence 0.45), confirming the message was recognised as scheduling-intent, but the wording evidently wasn't concrete enough (e.g. lacking an explicit day/time/duration) for the parser to produce a complete, `executable()` extraction.

Per the plan's explicit, owner-specified rule: **no proposal was ever approved to force completion.** This is recorded as "Calendar write not validated this pass," not a phase failure. A corrected, more concrete trigger message is a separately authorised follow-up, not performed in this phase.

## Provider-call summary

| Call | Count |
|---|---|
| Gmail `create_draft` (attempt 1, uncertain) | 1 |
| Gmail `get_draft` (verification, attempt 1) | 1 |
| Gmail `create_draft` (attempt 2, succeeded) | 1 |
| Gmail `get_draft` (verification, attempt 2) | 1 |
| Calendar `insert_event` | 0 |
| Automatic retries of any uncertain outcome | 0 |
