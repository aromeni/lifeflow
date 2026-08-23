# Stage 11A Phase 9 — GM-12 Fresh-Trigger Verification Results

**Date:** 2026-08-23

## Reconnection

Account A reconnected via connector-consent only (`authorisation_revision`
5→6, exactly +1), same four scopes, zero other real-credentialed `google`
rows (Account B untouched), zero `google_subject` bindings — independently
verified against the database before proceeding.

## Sync

`{"imported":2,...}`. Two `SourceItem`s appeared:

| id | occurred_at | folder | thread_id |
|---|---|---|---|
| `afe2d264-...` (the trigger) | 2026-08-17 20:32:17Z | `sent` | `1a011372dea4eca4` |
| `f9115bd7-...` (unrelated) | 2026-08-20 12:52:20Z | `inbox` | `1a02132957f4742a` |

The trigger correctly landed in the `sent` folder, confirming real Gmail's
`SENT` label propagated through the real connector and normalisation layer
exactly as `detect_follow_ups` expects. The second item is an unrelated
real message with a **different thread ID** — confirmed **not** a reply to
the trigger, so the "no reply" condition the whole test depends on was
never at risk.

## Brief generation (read-only)

One brief generated. The trigger item appears in the `waiting_for` section:

```
signal_type: follow_up
confidence: 0.85
reason_codes: ["no_reply_6d"]
actionable: true
suggested_action: "Decide whether to follow up."
```

`no_reply_6d` is an exact match — the trigger was sent 2026-08-17, verified
6 real days before this check on 2026-08-23. **This is the confirmation
Phase 8 deferred**: real Gmail's `SENT`/`INBOX` labels and thread IDs
propagate correctly through the real connector into the exact shape
`detect_follow_ups` (`detectors.py:405-440`) expects — the same conclusion
`test_overdue_follow_ups` already proved for synthetic fixtures, now
confirmed for a real Gmail message via the real ingestion pipeline.

## Proposal composition

Two new proposals appeared in the same brief (`create_task`, source ref
`em-024`; `create_gmail_draft`, source ref `em-008`) — both trace to the
**synthetic demo dataset's own reference IDs**, not the real trigger
message. No proposal was composed from the real follow-up signal at all.
This does not weaken the result above (the signal itself is the object
under test, per the deferred condition's own wording), and it means there
was nothing real-account-related to leave untouched — confirmed anyway:
zero `action_executions` against the real connected account newer than
Phase 6B's original, pre-existing Calendar insertion
(`86657365-...`, 2026-08-05).

## Teardown

- Imported-data deletion via the audited preview→confirm→worker flow: `2`
  source items, `1` signal deleted, state `succeeded`. Re-confirmed: `0`
  source items remain for this account.
- Disconnect: `204`, `status: disconnected`, both token columns cleared.
  `revocation_confirmed: true` — objectively successful this time (unlike
  Phase 7's, matching Phase 8's own retry which also succeeded).
- Readiness command re-run: `19/19 PASS`.
- All manual servers (`uvicorn`, `next dev`, `arq`) stopped; only
  `db`/`redis` containers remain up.
- `GOOGLE_PROVIDER_WRITES_ENABLED` was never touched — stayed `false`
  throughout.
