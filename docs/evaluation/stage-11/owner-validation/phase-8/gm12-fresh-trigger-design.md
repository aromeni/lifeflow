# Stage 11A Phase 8 — GM-12 Fresh-Trigger Design

**Date:** 2026-08-17

## Detector logic grounding

`detect_follow_ups` (`apps/api/src/lifeflow_api/detectors.py:405-440`) is
**purely structural** — unlike the Calendar-write trigger, it does not
parse subject/body text at all:

- Eligibility: `metadata_json["folder"] == "sent"` (traced to Gmail's
  `SENT` label via `normalisation.py`'s `_folder_for()`) — i.e. the message
  must be one Account A itself sent, not received.
- Threshold: `(reference - item.occurred_at).days >= 5` — pure elapsed
  time since the outgoing message's timestamp, no reply-by date.
- No-reply check: no other `SourceItem` sharing the same Gmail
  `thread_id` with `folder == "inbox"` and a later `occurred_at`.

The deterministic logic itself is already unit-tested independent of any
live-Gmail question (`test_overdue_follow_ups`,
`apps/api/tests/test_detectors.py:54-59`, using demo-dataset fixtures, not
GM-12). What a fresh trigger actually validates is narrower than the
Calendar trigger's text-parsing question: whether **real Gmail's
`SENT`/`INBOX` labels and thread IDs correctly propagate through the real
connector and normalisation path** into the same `folder`/`thread_id`
shape the detector expects — an integration question, not a parsing one.
Because content isn't parsed, the trigger's wording can be simple and
fictional; only its **direction** (sent by Account A, not received) and
**silence** (no reply) matter.

## Trigger design

- **Sender**: Account A (not Account B — GM-12's own definition was
  `A → B`, i.e. outgoing from the connected mailbox).
- **Recipient**: Account B.
- **Subject**: `P8-FOLLOWUP-TEST-01` (a fresh, distinctly-labelled trigger,
  not a resend of the original GM-12 — avoids any ambiguity about which
  message a later detection traces to).
- **Body**: short, fictional, disposable — no real content, no
  scheduling-phrase requirements (the detector doesn't read it).
- **Critical condition**: Account B must **not reply** to this message.
  Any reply in the same thread would make the detector correctly exclude
  it, which would falsely look like a detector failure rather than the
  intended non-reply scenario.

## Timing

Threshold is `>= 5` full days by `occurred_at`. Scheduling the follow-up
check no sooner than **6 days** after send, to sit safely past the
threshold rather than land exactly on an hour-level edge (the same
margin-over-precision approach used for the Phase 7 7-day-boundary
observation).

## Verification plan (at the follow-up check-in, not now)

1. Reconnect Account A (connector-consent only, same as every prior
   phase), verify independently against the database as usual.
2. Sync — confirm the trigger message is imported as a `SourceItem` with
   `metadata_json.folder == "sent"`.
3. Generate a brief (read-only composition — this is the step that
   actually runs `detect_follow_ups`; the daily soak checklist deliberately
   never did this, which is *why* GM-12 was never evaluated during the
   soak itself). Confirm a follow-up `Signal` exists referencing the
   trigger item, with the expected `signal_type` and evidence.
4. If brief/proposal composition produces an actionable suggestion (e.g. a
   `create_gmail_draft` candidate), it must be left exactly as `proposed`
   — **never approved or executed**. `GOOGLE_PROVIDER_WRITES_ENABLED` stays
   `false` throughout this check, same as the rest of Stage 11A.
5. Full teardown afterwards: imported-data deletion, disconnect, revoke,
   zero-residue re-verification — same discipline as every prior phase.
