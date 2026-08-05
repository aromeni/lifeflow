# Stage 11A Phase 6B — Fake-Provider Rehearsal Results

**Date:** 2026-08-05

Run entirely against deterministic parsing/payload code (`scheduling_phrases.py`, `action_payloads.py`) — no network, no live Google, no owner action. See `apps/api/tests/test_stage11a_phase6b_calendar_trigger_rehearsal.py`.

## Exact trigger content rehearsed

Subject: `P6-CAL-TEST-02`

Body (owner will send verbatim from Account B):

> Please schedule a meeting called "Northstar follow-up" for Thursday, 13 August 2026, from 14:00 to 14:30 Europe/London.
>
> Please invite me.

## Results

| Requirement | Result |
|---|---|
| Generates a Calendar insertion proposal | **Pass** — `has_intent=True`, `missing=()`, `executable()=True` |
| Absolute date recognised | **Pass** — 13 August 2026; stated weekday "Thursday" matches (independently confirmed via `datetime.date(2026,8,13).strftime("%A") == "Thursday"`); a deliberately mismatched weekday was separately proven to be rejected, not silently corrected |
| Start/end time recognised | **Pass** — 14:00–14:30 (30 minutes) |
| Timezone is Europe/London | **Pass** — explicit in text, confirmed to beat a different profile default |
| Proposal is insertion-only | **Pass** — `CalendarEventCreatePayload` has no update/delete counterpart in this codebase; `GoogleCalendarEventExecutor` calls only `insert_event` |
| Account B is the only attendee | **Pass** — attendee comes solely from the "invite me" self-attendee cue (the sender), never from text-scanning; the trigger body contains no `@` at all |
| Notifications disabled | **Pass** — `insert_event` hardcodes `sendUpdates=none` (`test_real_calendar_execution_calls_exactly_events_insert_with_send_updates_none`, re-run clean) |
| No Gmail proposal executed | **Pass** by construction — this signal path only ever composes a `create_calendar_event` candidate |
| No existing event can be modified or deleted | **Pass** — `GoogleCalendarEventExecutor` has no update/patch/delete method to call (T23) |
| Duplicate execution prevented | **Pass** — `test_replay_never_calls_executor_twice_for_a_completed_execution`, `test_pending_attempt_is_durably_committed_before_the_executor_is_called` (re-run clean) |
| Uncertain execution not retried | **Pass** — `test_uncertain_outcome_leaves_proposal_executing_and_is_never_retried`, `test_transport_timeout_during_real_execution_is_immediately_uncertain` (re-run clean) |

## Test results

`test_stage11a_phase6b_calendar_trigger_rehearsal.py`: 9/9 passed.
Existing regression re-run: `test_google_route_integration.py` (3 targeted tests) + `test_execution_durability.py` (6 tests): 10/10 passed.

## Verdict

Rehearsal **passed in full**. Proceeding to request the owner send the trigger (§2) and, once confirmed sent, to the live connection window (§4 onward).
