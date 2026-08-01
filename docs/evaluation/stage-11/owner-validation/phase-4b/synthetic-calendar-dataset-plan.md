# Synthetic Calendar Dataset Plan

**Status:** Designed, not created · **Date:** 2026-08-01

Companion: [synthetic-gmail-dataset-plan.md](synthetic-gmail-dataset-plan.md) · [test-account-specification.md](test-account-specification.md) · [real-provider-data-boundary.md](real-provider-data-boundary.md)

All events live on Account A's primary calendar; Account B appears only as a synthetic attendee where noted. **No event in this plan is created during Phase 4B.**

| ID | Category | Owner | Title (illustrative) | Timezone | Timing | Attendees | Notification expectation | Expected LifeFlow signal | Expected Today category | Expected evidence | Prohibited mutation | Cleanup |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CAL-01 | Upcoming meeting requiring preparation | A | "Sync with B" | Account A's local timezone | 2 days out | B | none (`sendUpdates=none` on any LifeFlow-side change) | Meeting prep needed (linked to GM-05) | Upcoming | Event id + linked email | LifeFlow must never edit/delete this event | Delete via Google Calendar |
| CAL-02 | Same-day event | A | "Team check-in" | Account A's local timezone | Today | none | none | Same-day awareness | Today | Event id | No mutation | Delete |
| CAL-03 | Next-day event | A | "Client call" | Account A's local timezone | Tomorrow | none | none | Upcoming awareness | Upcoming | Event id | No mutation | Delete |
| CAL-04 | Event in another timezone | A | "Cross-timezone planning call" | A different IANA zone than Account A's | 3 days out | B | none | Timezone-aware scheduling (linked to GM-17) | Upcoming | Event id + timezone metadata | No mutation | Delete |
| CAL-05 | Event with Account B as attendee | A | "Review meeting" | Account A's local timezone | 4 days out | B | none | Attendee-aware evidence | Upcoming | Event id + attendee list | No mutation | Delete |
| CAL-06 | Event without attendees | A | "Focus block" | Account A's local timezone | Tomorrow | none | none | Low-priority/no-action | (none) | Event id | No mutation | Delete |
| CAL-07 | All-day event | A | "Conference (all day)" | Account A's local timezone | 5 days out, all-day | none | none | All-day handling correctness | Upcoming | Event id | No mutation | Delete |
| CAL-08 | Overlapping events | A | "Call A" / "Call B" (same time slot) | Account A's local timezone | Same day, overlapping times | none | none | Scheduling-conflict detection (linked to GM-10) | Needs attention | Both event ids | No mutation | Delete both |
| CAL-09 | Cancelled event (API visibility) | A | "Cancelled: old sync" | Account A's local timezone | Past or near-term, status=cancelled | none | none | Correct handling of a cancelled-status event (excluded from active signals) | (none) | Event id + status | No mutation | Delete |
| CAL-10 | Event linked to a synthetic email thread | A | "Prep session" | Account A's local timezone | 2 days out | none | none | Cross-source evidence linking (linked to GM-05) | Upcoming | Event id + email cross-reference | No mutation | Delete |
| CAL-11 | Existing event LifeFlow must never edit/delete | A | "Recurring 1:1" | Account A's local timezone | Recurring, ongoing | none | none | Read-only awareness only | Upcoming (each occurrence) | Event id | **This is the explicit non-mutation proof event — LifeFlow's read-only Calendar behaviour on a pre-existing event must be manually confirmed against it** | Delete |
| CAL-12 | Proposed new event suitable for LifeFlow insertion | A | "Proposed: follow-up meeting" (not yet created) | Account A's local timezone | To be scheduled | B | notifications explicit at insertion time | Suggested action: create a calendar event | Suggested actions | (created event id, once inserted) | **This is the one event used for the single controlled Calendar insertion in Decision 2 (first-provider-write), never during connection-only validation** | Remove manually or via approved cleanup outside LifeFlow after verification |

## Notes

- All 12 required scenario categories from the governing instruction are covered by CAL-01 through CAL-12.
- CAL-11 is the deliberate proof point for "LifeFlow must never edit or delete an existing event" — during the eventual read-only smoke test, the owner should attempt (via LifeFlow's own UI/API, not directly in Google Calendar) to confirm no update/delete path exists for this event, corroborating the structural test in [oauth-scope-matrix.md](oauth-scope-matrix.md) (`test_calendar_client_has_no_update_or_delete_method`).
- CAL-12 is the only event this dataset plan associates with an actual future insertion, and only under the separate, explicit Decision 2 (provider-write authorisation) — never during Decision 1 (connection-only) testing. See [provider-write-authorisation-gate.md](provider-write-authorisation-gate.md).
- This plan does not create any of these events. It exists as a ready, reviewed script for the owner to manually create in Google Calendar once Account A/B are connected (a separate, future owner-authorised step).
