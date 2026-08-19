# Stage 11A Phase 7 — Soak Daily Log

Append-only. One entry per owner check-in, using
[daily-checklist.md](daily-checklist.md). T0 (soak start) is recorded in
[day-00-connection-evidence.md](day-00-connection-evidence.md) once Account A
is reconnected.

---

## Day 0 — 2026-08-05T22:46:02Z (T0) — 0.0h elapsed

- Connection: Account A reconnected, verified (see
  [day-00-connection-evidence.md](day-00-connection-evidence.md)). Account B
  still disconnected. `google_subject` bindings: 0.
- Stability: `/ready` ok, 0 degraded dependencies. `database_readiness_failures_total=0`,
  `redis_degraded_total=0`. `db`/`redis` healthy.
- Sync: `imported=0 updated=0 unchanged=0`, both cursors `"incremental"` —
  expected; see the sync-cursor finding in `day-00-connection-evidence.md`
  (imported-data deletion doesn't reset the provider cursor).
- Duplicates: 0/0/0 (trivial — 0 `source_items` for this account currently).
- GM-12: not observable yet (no items imported this soak; will re-check once
  a cursor flips to `"resynced"`).
- Reconnection events: none (this was the initial Day-0 connection, not a
  post-expiry reconnection).
- Observed gaps: none.

## Day 1 — 2026-08-06T20:49Z — 22.1h elapsed

- Flags: all three confirmed `false` at check-in start.
- Observed gap: Docker Desktop (and therefore `db`/`redis`) was down at
  check-in time — `/health` ok, `/ready` `"unavailable"`
  (`database_readiness_failures_total` incremented from 0 to 1 across the
  gap). Most likely cause: the host machine slept overnight; no evidence of
  any flag drift or unexpected process during the gap. Restarted Docker
  Desktop and `docker compose up -d db redis --wait`; both containers came
  back healthy within seconds (same containers, not recreated — "6 days
  ago" created, so no data loss). `/ready` recovered to `ok` **without any
  API restart** — the app's own DB/Redis connection handling recovered on
  its own once the dependencies returned. Logged as an observed gap per the
  soak's best-effort-uptime model, not a failure; the Google-side
  authorisation/token clock is unaffected by local downtime.
- (An apparent API-process-identity discrepancy was investigated and ruled
  out as a non-event — the "new" PID was simply this soak's own Day-0
  restart, whose OS-recorded start time reflected real elapsed conversation
  time, not a second, unlogged restart.)
- Connection status: `active`, `authorisation_revision: 3` — unchanged,
  unaffected by the local outage, as expected.
- Sync: `imported=0 updated=0 unchanged=0`, both cursors still
  `"incremental"` — no resync yet.
- Duplicates: 0/0/0 (SourceItem/Signal/proposal group-by checks, all empty).
- Writes: confirmed 0 `action_executions` with `started_at` after T0 — the
  one execution row tied to this account is Phase 6B's pre-soak Calendar
  insertion (`started_at` 2026-08-05T18:51:11Z, before T0), unaffected.
- GM-12: not observable yet (no resync yet).
- Reconnection events: none.

## Day 2 — 2026-08-08T07:25Z — 56.7h elapsed

- Flags: all three confirmed `false` at check-in start. API/web processes
  are the same PIDs as Day 1 (no crash, no restart in between).
- Observed gap: Docker Desktop was down again at check-in (same signature as
  Day 1 — most likely the host sleeping between check-ins). Same recovery:
  reopened Docker Desktop, `docker compose up -d db redis --wait`, same
  containers came back healthy in seconds (7 days old, not recreated), no
  API restart needed, `/ready` recovered to `ok`.
- New counter since Day 1: `provider_requests_total{operation="refresh_access_token",provider="google_oauth",outcome="success"}=1` —
  the stored Google access token expired (normal, ~1h lifetime) and was
  successfully refreshed using the refresh token at some point in this
  window. This is expected, healthy behaviour, and separate from the 7-day
  refresh*-token*-itself expiry this phase is watching for.
- Connection status: `active`, `authorisation_revision: 3` — unchanged.
- Sync: `imported=0 updated=0 unchanged=0`, both cursors still
  `"incremental"` (no full resync yet) — but `gmail_incomplete=2` appeared
  for the first time (previously 0). Per the code's own documented D38
  case, this means Gmail's history API referenced 2 message IDs that then
  404'd on individual fetch — a real, non-error outcome the connector
  already handles, not a LifeFlow defect. No corresponding `SourceItem` was
  created for either (consistent with "incomplete", not "imported"). Noted
  for the record; will keep watching whether this count grows.
- Duplicates: 0/0/0.
- Writes: confirmed 0 `action_executions` with `started_at` after T0.
- GM-12: not observable yet (no resync yet).
- Reconnection events: none.

## Day 3 — 2026-08-09T16:07Z — 89.4h elapsed

- Flags: all three confirmed `false` at check-in start. Same API/web PIDs
  as Day 1/2 — no crash or restart since Day 0.
- Observed gap: Docker Desktop down again at check-in, same signature as
  Day 1/2 (host sleep between check-ins). Same clean recovery: containers
  came back healthy in seconds (8 days old, not recreated), no API restart
  needed, `/ready` recovered to `ok`.
- Counters: `refresh_access_token` success now `2` (one more successful
  access-token refresh since Day 2, expected). `get_message` /
  `client_error` = `2` confirms Day 2's `gmail_incomplete=2` was exactly 2
  individual message-fetch 404s, not a miscount.
- Sync: `imported=0 updated=0 unchanged=0`, both cursors still
  `"incremental"`. `gmail_incomplete` back to `0` this time — Day 2's
  occurrence was a one-off, not a growing/persistent issue.
- Connection status: `active`, `authorisation_revision: 3` — unchanged.
- Duplicates: 0/0/0.
- Writes: confirmed 0 `action_executions` with `started_at` after T0.
- GM-12: not observable yet (no resync yet).
- Reconnection events: none.

## Day 4 — 2026-08-10T14:30Z — 111.7h elapsed

- Flags: all three confirmed `false` at check-in start. Same API/web PIDs
  since Day 0.
- No observed gap this time — Docker/db/redis stayed up continuously since
  Day 3 (22h container uptime at check-in), first fully clean interval.
- Counters: `refresh_access_token` success now `3` (one more since Day 3,
  expected). `get_message`/`client_error` unchanged at `2` — Day 2's
  incomplete-fetch pair has not recurred or grown.
- Sync: `imported=0 updated=0 unchanged=0`, both cursors still
  `"incremental"` — no resync yet, ~4.7 days in, within the expected ~7-day
  window.
- Connection status: `active`, `authorisation_revision: 3` — unchanged.
- Duplicates: 0/0/0.
- Writes: confirmed 0 `action_executions` with `started_at` after T0.
- GM-12: not observable yet (no resync yet).
- Reconnection events: none.

## Day 5 — 2026-08-11T09:57Z — 131.2h elapsed

- Flags: all three confirmed `false` at check-in start. Same API/web PIDs
  since Day 0.
- No observed gap — Docker/db/redis stayed up continuously since Day 4
  (42h container uptime at check-in).
- Counters: `refresh_access_token` success now `4` (one more since Day 4,
  expected). `get_message`/`client_error` still `2`, unchanged.
- Sync: `imported=0 updated=0 unchanged=0`, both cursors still
  `"incremental"` — ~5.5 days in, still within the expected ~7-day window,
  getting close; watching closely from here.
- Connection status: `active`, `authorisation_revision: 3` — unchanged.
- Duplicates: 0/0/0.
- Writes: confirmed 0 `action_executions` with `started_at` after T0.
- GM-12: not observable yet (no resync yet).
- Reconnection events: none.

## Day 6 — 2026-08-12T22:19Z — 167.6h elapsed (6.98 days)

- Flags: all three confirmed `false` at check-in start.
- Observed gap, different in kind from Day 1/2/3: no `uvicorn`/`next
  dev`/`arq` processes were running at all (not just Docker) — a full
  machine reboot is the likely cause, not just sleep. Docker Desktop was
  also down. Recovery: reopened Docker Desktop, `docker compose up -d db
  redis --wait` (same containers, 12 days old, not recreated — no data
  loss), confirmed `SESSION_SECRET` still fixed in `.env` (so no session
  disruption once the API restarted), restarted the API process fresh.
  `/health`/`/ready`/`/config` all confirmed healthy and flags still safe
  immediately after restart.
- Counter caveat: Prometheus counters are in-process only and reset on an
  API restart, so this check-in's `refresh_access_token`/`list_history`/
  `list_events` all read `1` rather than continuing yesterday's tally — this
  reflects the restart, not a regression; the historical counts from Day
  0–5 remain valid for the intervals they covered.
- **7-day boundary status**: at 6.98 days elapsed, the connection is still
  `status: active` and the controlled sync succeeded (HTTP 200,
  `imported=0 updated=0 unchanged=0`, both cursors still `"incremental"`).
  The refresh token has not expired yet — right at the edge of the
  documented ~7-day window, not past it. Watching the next check-in closely
  for the expected `revoked`/409 event.
- Duplicates: 0/0/0.
- Writes: confirmed 0 `action_executions` with `started_at` after T0.
- GM-12: not observable yet (no resync yet).
- Reconnection events: none.

## Day 7 — 2026-08-14T18:35Z (expiry) / 22:52Z (reconnection) — 211.8h elapsed at check-in

**The 7-day Testing-status boundary occurred.** No gap this time (Docker/API
had been up 44h continuously; same PIDs since the Day 6 restart).

- First sync attempt at check-in (211.8h / 8.83 days elapsed) returned
  **HTTP 409 `reauthorisation_required`**. Verified in the database
  immediately after: `connected_accounts.status` flipped from `active` to
  `revoked`; `audit_events` recorded `account.revoked` at
  `2026-08-14T18:35:58.657833+00:00`. The last confirmed-`active` check-in
  was Day 6 at 6.98 days, so the actual expiry happened somewhere in that
  ~46-hour gap between check-ins — consistent with, though not more
  precisely pinned within, Google's documented "~7 days from consent"
  Testing-status window.
- Bounded-failure check: `provider_requests_total{operation="refresh_access_token",outcome="grant_invalid"}=1`,
  no repeat attempts, and `list_history`/`list_events` counters did **not**
  increment on this call — the sync correctly short-circuited on the failed
  refresh rather than proceeding to call Gmail/Calendar anyway. A single,
  non-retried 409 was returned to the caller. No cron/background job in
  this codebase touches Google, so no retry storm was possible by
  construction, consistent with the fake-provider rehearsal from earlier
  phases.
- Residue note for the record: `store_tokens`'s revocation handling clears
  `encrypted_access_token` but **not** `refresh_token_key_id`/
  `encrypted_refresh_token` — both were still present (`has_refresh: true`)
  while the account sat in `revoked` status, before reconnection. Not a
  soak-blocking issue (the refresh token itself is already rejected by
  Google and unusable), but worth being precise about for the final
  zero-residue check at soak completion — "0 stored credentials" needs to
  be verified strictly *after* disconnect, not merely inferred from the
  revoked state.
- **Controlled reconnection**: `GOOGLE_CONNECTOR_OAUTH_ENABLED` set to
  `true`; API and web restarted; owner reconnected Account A only
  (`SOAK RECONNECTION SENT`). Verified independently against the database
  before proceeding: `status: active`, `authorisation_revision` incremented
  from `3` to `4` (exactly +1), exactly the same four scopes, exactly one
  `connected_accounts` row for this user+provider (no duplicate row created
  by the reconnect), zero other real-credentialed `google` rows (Account B
  still untouched), zero `google_subject` bindings. Audit event:
  `account.tokens_refreshed` at `2026-08-14T22:52:37.53686+00:00`
  (`authorisation_revision: 4`) — same pre-existing audit-vocabulary quirk
  noted in `daily-checklist.md` §5. `GOOGLE_CONNECTOR_OAUTH_ENABLED` set
  back to `false` immediately after, confirmed live via `/config`.
- Resumed the daily protocol post-reconnection: sync succeeded
  (`imported=0 updated=0 unchanged=0`, both cursors still `"incremental"` —
  the sync cursor survived the revoke/reconnect cycle, same as it survived
  Phase 6B's disconnect/reconnect). Duplicates: 0/0/0. Writes: confirmed 0
  `action_executions` with `started_at` after T0.
- GM-12: still not observable (no resync yet).
- **T0 is unchanged** — the soak clock remains anchored to the original
  2026-08-05T22:46:02Z consent, per the plan ("the soak clock does not
  reset" on a mid-soak reconnection). Soak still ends no earlier than
  2026-08-15T22:46:02Z — under 24h away from this check-in.

## Day 8 — 2026-08-15T10:20Z — 227.6h elapsed (9.48 days)

- Flags: all three confirmed `false` at check-in start. Same API/web PIDs
  since Day 7's post-reconnection restart; Docker up 2 days continuously —
  no observed gap.
- Connection status: `active`, `authorisation_revision: 4` — unchanged
  since the Day 7 reconnection, refresh continuing to work normally on the
  new grant.
- Sync: `imported=0 updated=0 unchanged=0`, both cursors still
  `"incremental"`.
- Duplicates: 0/0/0.
- Writes: confirmed 0 `action_executions` with `started_at` after T0.
- GM-12: still not observable (no resync yet — it has now gone unobserved
  for the entire soak; will record this honestly at completion rather than
  force it, per the plan).
- Reconnection events: none since Day 7.
- **Soak completes at 2026-08-15T22:46:02Z — approximately 12.4 hours from
  this check-in.** Next check-in at or after that time should be the final
  one, moving to the completion teardown (imported-data deletion,
  revocation, disconnect, zero-residue proof) instead of another daily
  cycle.

## Day 9 (final) — 2026-08-16T16:41Z — 257.9h elapsed (10.75 days)

**Past the 240-hour minimum — this is the completion check-in.** No gap
since Day 8 (Docker up 3 days continuously, same PIDs). Flags confirmed
`false` at check-in start.

- Connection status: `active`, `authorisation_revision: 4` — unchanged.
- Sync: `imported=1 updated=0 unchanged=0`, `gmail_cursor_status` still
  `"incremental"` (not `"resynced"` — this was not a full resync). The one
  imported item is an `email` SourceItem with `occurred_at` `2026-08-01`,
  i.e. original fixture mail from *before* T0, not anything newly sent
  during the soak. Its subject does not match GM-12's known text. Most
  likely explanation: Gmail's history log generated a change event
  referencing this already-existing message (e.g. a label/read-state
  change) that only surfaced now, distinct from the deletion/cursor
  interaction documented on Day 0. It produced **zero** new `Signal`s or
  `ActionProposal`s — this soak never triggered brief generation/extraction
  (only the daily read-only sync), so a freshly imported item stays inert
  until a separate, human-initiated step acts on it; none did.
- Duplicates: 0/0/0 (re-checked after the new import — still empty).
- Writes: confirmed 0 `action_executions` with `started_at` after T0.
- GM-12: **not observed this soak.** Discussed with the owner before this
  check-in; the agreed position (owner did not request forcing it) is
  recorded in `phase-7-decision.md` — not a defect, a documented and
  understood limitation of testing against fixture mail whose local copy
  was already deleted before the soak began, not a soak failure.
- Proceeding to completion teardown below.
