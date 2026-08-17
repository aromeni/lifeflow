# Stage 11A Phase 8 — GM-12 Cheap-Path Closure Attempt

**Date:** 2026-08-17

## What was tried

Per `stage-11a-phase-8-plan.md`'s cheapest-first approach: reconnected
Account A (connector-consent only) and attempted a controlled sync
immediately, on the chance that ~16 real days since GM-12 was originally
sent (~2026-08-01) had been enough for either Gmail's `historyId` or
Calendar's sync token to expire into the documented full-resync fallback.

## Result

**Did not work.** The sync response was `{"imported":0,"updated":0,"unchanged":0,...}`
with both `gmail_cursor_status` and `calendar_cursor_status` still
`"incremental"` — no full resync occurred. GM-12 remains unobserved.

## Reconnection verification (independent, before the attempt)

`status: active`, `authorisation_revision` incremented from `4` to `5`
(exactly +1), exactly the same four scopes, zero other real-credentialed
`google` rows (Account B untouched), zero `google_subject` bindings.

## Immediate re-disconnection

Since the cheap path failed and the fallback (a fresh trigger + a ~5-6 day
wait) doesn't require Account A to stay connected in the meantime, Account
A was disconnected again immediately rather than left idle-connected for
days. `POST /connected-accounts/google/disconnect` returned `204`.
Confirmed: `status: disconnected`, both token columns `NULL`. This time
**`revocation_confirmed: true`** — the revoke call succeeded objectively,
unlike Phase 7's attempt (see `revocation-closure.md`), suggesting that was
a transient failure rather than a persistent one. Readiness command re-run:
19/19 PASS. All manual servers (`uvicorn`, `next dev`) stopped; only
`db`/`redis` containers remain up.

## Next step

Falling back to the plan's second option: design and rehearse a fresh
stale-follow-up trigger message, have the owner send it, and schedule
exactly one follow-up check-in no sooner than 5 days later. See the
detector-logic research this evidence pack's next entry is based on before
finalising the exact trigger content.
