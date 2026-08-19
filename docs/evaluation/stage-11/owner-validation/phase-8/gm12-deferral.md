# Stage 11A Phase 8 — GM-12: Explicitly Deferred, Not Closed

**Date:** 2026-08-19

## Why this is deferred rather than closed or force-closed

The cheap-path attempt (reconnect + immediate sync, on the chance ~16
elapsed days had been enough for a natural sync-cursor expiry) did not
work — see `gm12-cheap-path-attempt.md`. The fallback — a fresh trigger
(`P8-FOLLOWUP-TEST-01`), sent by the owner from Account A to Account B on
2026-08-17 — is in motion, but `detect_follow_ups`
(`apps/api/src/lifeflow_api/detectors.py:405-440`) requires **real elapsed
time**, `(reference - item.occurred_at).days >= 5`, computed against the
message's actual Gmail timestamp. There is no way to satisfy this today
(2026-08-19, two days after send) without either backdating data — which
would defeat the point of testing real Gmail integration — or waiting.

The project owner asked directly whether the wait was necessary before
authorising this phase's closure. The honest answer: the constraint itself
is real and not proceedable-around, but it does **not** need to block
Stage 11A's exit, because what it would additionally prove is narrower than
it might first appear:

- The deterministic detection *logic* is already unit-tested independent
  of any live-Gmail question (`test_overdue_follow_ups`,
  `apps/api/tests/test_detectors.py:54-59`) — proven correct against
  synthetic fixtures with the same 5-day/no-reply structure.
- What a live GM-12 (or fresh-trigger) observation would additionally
  confirm is that real Gmail's `SENT`/`INBOX` labels and thread IDs
  propagate correctly through the real connector and normalisation layer
  into the shape the detector expects — a real-integration question, not a
  correctness-of-logic question.
- No safety, privacy, or duplicate/write concern is implicated by this gap
  in either direction.

This is exactly the shape `owner-validation-exit-template.md`'s
`CONDITIONAL READINESS` outcome exists for: "one or more explicit,
testable, non-safety P2 conditions remain... state what must change, by
when, and how it will be re-verified."

## Deferred condition (for the Stage 11A exit decision)

**What must happen:** the owner (or a future session) checks back after
2026-08-23 — the trigger message will be ≥ 5 days old by then. **How it
will be re-verified:** reconnect Account A, sync (confirm the trigger
`SourceItem` imports with `metadata_json.folder == "sent"`), generate a
brief (read-only — the step that actually runs `detect_follow_ups`, which
the Phase 7 soak deliberately never triggered), confirm a follow-up
`Signal` references the trigger item, then tear down (imported-data
deletion, disconnect, revoke, zero-residue verification) exactly as every
prior phase has. `GOOGLE_PROVIDER_WRITES_ENABLED` stays `false` throughout
— nothing gets approved or executed regardless of outcome. **By when:**
no fixed deadline — this is a real-integration nice-to-have, not a
blocking safety condition, and the deterministic logic it would confirm is
already proven independently.

This condition does not need to be closed before Stage 11A's exit
decision is recorded; it is carried forward explicitly rather than
silently dropped.
