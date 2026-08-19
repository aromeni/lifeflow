# Stage 11A Phase 7 — Day 0: Connection Evidence

**Date:** 2026-08-05

## Starting boundary

Verified before touching any flag: readiness command 19/19 PASS, 0 stored
credentials, 0 identity bindings, working tree clean on
`stage-11a-phase-7-soak-period` (branched from `main` at
`5a7b1f1a3e2a642244c69f887d0c1ca0329860d9`, the Phase 6B merge commit). No
stray `uvicorn`/`next dev`/`arq` processes; only `db`/`redis` containers up.

## Connection window

`GOOGLE_CONNECTOR_OAUTH_ENABLED` set to `true`; `GOOGLE_OIDC_SIGNIN_ENABLED`
confirmed `false` throughout (`/config`). Owner reconnected Account A only
via the connector-consent flow (`SOAK CONNECTION SENT`).

Verified directly against the database immediately after:

- Exactly one real, credentialed `connected_accounts` row for
  `provider="google"` (`b11b4d3a-...`, the same row used since Phase 6B —
  reconnecting an existing, disconnected account updates it in place rather
  than creating a second row, per the `UniqueConstraint(user_id, provider)`).
- Status: `active`. `authorisation_revision`: `3` (incremented by exactly 1
  from its pre-soak value).
- Granted scopes: exactly the four approved scopes (`calendar.events`,
  `calendar.readonly`, `gmail.compose`, `gmail.readonly`).
- Zero other real-credentialed `google` rows for any other user (Account B
  was never connected).
- Zero `users.google_subject` bindings anywhere (OIDC sign-in never used).

`GOOGLE_CONNECTOR_OAUTH_ENABLED` was set back to `false` immediately after,
and the API process restarted to pick up the change (confirmed live via
`/config`).

## T0 — recorded Google consent timestamp

The relevant audit event is `event_type = "account.tokens_refreshed"`, not
`account.connected` — expected and not a defect: `accounts.py`'s
`store_tokens` labels the existing-row branch this way even for a full
re-consent, because Account A's row already existed from Phase 6B onward
(see `daily-checklist.md` §5 for the same note, written for reconnection
mid-soak).

**T0 = `2026-08-05T22:46:02.511575+00:00`** (`authorisation_revision: 3`,
`scope_count: 4`).

**Soak ends no earlier than `2026-08-15T22:46:02+00:00` (T0 + 240 hours).**

## Day-0 baseline

- `/health`: `{"status":"ok"}`. `/ready`: `{"status":"ok","degraded_dependencies":[]}`.
- Stability counters at baseline: `database_readiness_failures_total=0`,
  `redis_degraded_total=0` (both re-checked each day for a delta, not just
  presence).
- `docker compose ps`: `db`, `redis` both healthy.
- Duplicate checks (SourceItem by `(source_type, external_id)`): 0 rows —
  trivial at this point, since the account has 0 `source_items` (see below).
- First controlled sync:
  `{"imported":0,"updated":0,"unchanged":0,"gmail_cursor_status":"incremental","calendar_cursor_status":"incremental", ...}`.

## Finding: imported-data deletion does not reset the provider sync cursor

Not a defect — a genuine, worth-recording architectural observation. Phase
6B's cleanup deleted LifeFlow's local copy of the 53-item sync (`SourceItem`s
and `Signal`s) via the imported-data-deletion flow, but that flow
(`deletion.py`/`privacy_deletion.py`) never touches
`ConnectedAccount.sync_cursors` — only the separate, unused-here *full
account deletion* flow does (`account_deletion.py:233`). Gmail's
`historyId` and Calendar's sync token are Google-side incremental-change
cursors, not LifeFlow-side state; from Google's perspective nothing has
changed in the mailbox/calendar since the last real sync during Phase 6B, so
today's incremental sync correctly reported zero imports rather than
re-importing the still-present, disposable GM-01–18/CAL-01–11 fixture mail.

The codebase already has a documented recovery path for this
(`connectors/google_email.py:9`: "falling back to a full bounded resync on
HTTP 404 (expired historyId)"), bounded to the sync route's fixed 14-day
past window (`connected_accounts.py:46`,
`SYNC_WINDOW_PAST_DAYS = 14`). Rather than force this with an out-of-band
database write (which would bypass every audited code path this project
relies on), the daily checklist now also watches `gmail_cursor_status` /
`calendar_cursor_status` in each day's sync response — the day either flips
from `"incremental"` to `"resynced"`, the fixture dataset (including GM-12,
if it is still within the 14-day window at that point) becomes visible to
LifeFlow again, naturally, without any manual intervention. If neither
cursor ever expires within the 10-day window, this is recorded honestly as
"GM-12 could not be re-observed via a fresh import this soak" rather than
forced.

## Zero-write confirmation

`GOOGLE_PROVIDER_WRITES_ENABLED` remains `false` for the entire phase (never
toggled on Day 0, and not expected to be toggled at any point in this
phase — no proposal is approved or executed during the soak).
