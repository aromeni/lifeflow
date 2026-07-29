# Worker Recovery Runbook

Stage 9 Delivery Phase 5. The ARQ worker (`uv run arq
lifeflow_api.worker_app.WorkerSettings`) runs three job functions and four
per-minute-or-daily cron jobs. All are idempotent by durable-state design —
restarting the worker at any point, including mid-job, never duplicates a
side effect and never loses work permanently.

## If the worker process is down

Symptoms:

- `GET /scheduled-briefs/status` reports `"scheduler_available": false`.
- The Settings page shows "The scheduler is not currently reachable —
  scheduled briefs may be delayed until it is back" (`role="status"`, not an
  error — this is expected, accurate wording, not a bug).
- Deletion operations stay `pending`/`running` longer than expected.
- `ActionExecution` rows can accumulate as `pending` past `STALE_PENDING_AGE`
  (120s) until the next `recover_stale_action_executions` cron tick runs.

Recovery:

```bash
cd apps/api
uv run arq lifeflow_api.worker_app.WorkerSettings
```

Nothing else is required. On the next cron tick (every job registers
`run_at_startup=True` for its cron counterpart where relevant):

- `dispatch_scheduled_briefs` — enqueues anything due, recovers stale
  `running` runs, and drains anything left `pending`/`enqueued_at=None`
  from before the outage (`_recover_never_enqueued`).
- `dispatch_deletion_operations` — recovers stale `running` operations past
  their heartbeat timeout and drains anything never enqueued.
- `recover_stale_action_executions` — flips any `ActionExecution` still
  stuck `pending` past `STALE_PENDING_AGE` to the durable `uncertain`
  outcome.
- `expire_stale_memory` — daily only; a missed run is caught by the next
  day's run, or by read-time expiry in the meantime.

## If Redis is down while the worker is running

The worker's own queue connection depends on Redis (ARQ's core mechanism);
if Redis goes down, the worker cannot receive new jobs until it recovers.
This is different from the API process, which is largely Redis-independent
(see [outage-response.md](outage-response.md)). When Redis recovers, the
worker reconnects on its own; no restart is needed. Any operation that was
queued but not yet picked up will still be there once the worker reconnects,
*unless* the enqueue attempt itself failed while Redis was down — those are
handled by the drain passes above, not by anything Redis-side.

## Confirming a specific stuck row will self-heal

```sql
-- A pending execution older than 120s — will be flipped to `uncertain` on
-- the next recover_stale_action_executions tick (every minute).
SELECT id, outcome, started_at FROM action_executions
WHERE outcome = 'pending' AND started_at < now() - interval '120 seconds';

-- A scheduled-brief run stuck pending with no enqueue — will be drained on
-- the next dispatch_scheduled_briefs tick.
SELECT id, status, enqueued_at FROM scheduled_brief_runs
WHERE status = 'pending' AND enqueued_at IS NULL;

-- A deletion operation stuck pending with no enqueue — same, drained by
-- dispatch_deletion_operations.
SELECT id, state, enqueued_at FROM data_deletion_operations
WHERE state = 'pending' AND enqueued_at IS NULL;
```

If any of these queries return rows and a full minute has passed with the
worker running and Redis reachable, something is wrong beyond ordinary
recovery — check `lifeflow_worker_job_events_total{outcome="failed"}` for
the relevant `job` label and the worker's own logs (correlation id is fresh
per invocation, see `correlation.py::with_worker_correlation`) before
escalating further.

## Never do this

- Never run more than one worker process against the same Redis/database in
  a way that isn't the documented horizontal-scaling pattern (ARQ's own
  `_job_id` dedup and this app's atomic-claim patterns, e.g.
  `deletion.py::claim_operation`, are what make concurrent workers safe —
  do not work around them manually).
- Never manually change a `DataDeletionOperation.state`,
  `ScheduledBriefRun.status`, or `ActionExecution.outcome` column directly in
  the database to "unstick" something — every one of these has an atomic
  claim/recovery mechanism already; a manual edit can race it and produce
  the exact double-execution these mechanisms exist to prevent.
- Never `kill -9` a worker process in a shared dev/CI Redis if you can avoid
  it. ARQ holds a per-cron `arq:in-progress:cron:<name>:<ts>` lock key in
  Redis for the duration of each tick to prevent two workers double-running
  the same cron job; a graceful shutdown (`SIGTERM`, as `scripts/e2e.sh`
  already does) clears it, but a hard kill leaves it until its own TTL
  expires — a *later* worker started against the same Redis will silently
  skip that cron job until then (observed directly during Stage 9 Delivery
  Phase 5 manual verification: a `kill -9`'d worker's stale
  `dispatch_deletion_operations` lock delayed the next worker's own run of
  that cron by several minutes, until the lock's TTL lapsed). This is
  self-healing and bounded, never a stuck-forever state, but `redis-cli
  keys "arq:in-progress:*"` combined with `redis-cli flushall` (dev/test
  Redis only, never anything with real data) clears it immediately if you
  don't want to wait.
