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
