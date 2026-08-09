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
