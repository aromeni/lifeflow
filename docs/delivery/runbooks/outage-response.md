# Outage Response Runbook

Stage 9 Delivery Phase 5. Read this first when something is degraded; it
routes to the [provider-failure](provider-failure.md) and
[worker-recovery](worker-recovery.md) runbooks for the two most common
specific causes.

## 1. Check liveness and readiness first

```bash
curl -s http://localhost:8010/health   # process up? never fails for a
                                        # provider or Redis outage
curl -s http://localhost:8010/ready    # {"status": "ok"|"unavailable",
                                        #  "degraded_dependencies": [...]}
```

| Observation | Meaning | Action |
|---|---|---|
| `/health` fails to respond at all | The API process itself is down | Restart the process; check its own stderr/stdout for a startup error (missing required env var, port in use) |
| `/ready` returns `503` | PostgreSQL is unreachable | The API cannot safely serve its core functions. Check the database container/service is up (`docker compose ps db`); check `DATABASE_URL` |
| `/ready` returns `200` with `"degraded_dependencies": ["redis"]` | Redis is unreachable, but the API is otherwise healthy | Non-urgent: rate limiting fails open (requests are allowed, not blocked) and scheduled-brief/worker status will separately report unavailable. Restart Redis when convenient; nothing needs to be replayed |
| `/ready` returns `200` with `"degraded_dependencies": []` | Fully healthy | No action |

## 2. Check operational metrics

```bash
curl -s http://localhost:8010/metrics
```

Look for (all bounded-cardinality, safe to read directly — see
`apps/api/src/lifeflow_api/metrics.py`):

- `lifeflow_database_readiness_failures_total` — nonzero and climbing means
  PostgreSQL is flapping, not just currently down.
- `lifeflow_redis_degraded_total` — nonzero means `/ready` has observed
  Redis down at least once; check the trend, not just the current value.
- `lifeflow_provider_requests_total{outcome=...}` — a rising
  `transient_error`/`auth_error` count against `provider="gmail"` or
  `"calendar"` points at a Google-side problem — see
  [provider-failure.md](provider-failure.md).
- `lifeflow_worker_job_events_total{outcome="failed"}` — a rising count for
  any `job` label points at a worker problem — see
  [worker-recovery.md](worker-recovery.md).
- `lifeflow_rate_limit_fail_open_total` — nonzero means the rate limiter is
  currently degraded (Redis down); requests are still being allowed, this
  is not itself an outage of the product.

## 3. Correlate a specific user report with logs

Every HTTP response carries an `X-Correlation-ID` header, and every log line
(HTTP or worker) carries the same `correlation_id` field
(`logging_setup.py`'s `JsonFormatter`). Given a user-reported error, find its
correlation id from the response they saw (or ask them for it if the UI
surfaced one), then:

```bash
grep '"correlation_id": "<the-id>"' <api log output>
```

Worker/cron logs get their own fresh correlation id per job invocation
(`correlation.py::with_worker_correlation`) — they will not share an id with
the HTTP request that originally triggered the enqueue; correlate by the
internal identifier the job logs instead (`run_id`, `operation_id`,
`user_id`), never by the correlation id across that boundary.

## 4. What never needs an outage response

- A single `uncertain` execution outcome. This is a correct, expected,
  durable terminal-for-now state — never retried automatically, and never a
  sign the API or Google is broadly down. The proactive sweep
  (`recover_stale_action_executions`, every minute) already resolves any
  stuck `pending` row on its own.
- A `429` rate-limit response. This is the rate limiter working as designed,
  not a dependency failure.
- `scheduler_available: false` on `GET /scheduled-briefs/status` alone,
  without a corresponding `/ready` Redis-degraded signal. Restart the worker
  process (see [worker-recovery.md](worker-recovery.md)); no data is lost —
  scheduled runs it missed will be picked up by the same drain/recovery
  passes that handle a worker restart.

## 5. Never do this

- Never manually flip an `ActionExecution.outcome` from `uncertain` to
  `succeeded`/`failed` — the product's entire safety model depends on that
  state meaning "we genuinely do not know," and a database edit cannot
  discover what actually happened at the provider.
- Never manually re-trigger a Gmail draft creation or Calendar event
  insertion for a proposal already in `executing`/`uncertain` — check
  directly with the provider (Gmail/Calendar UI) first; the product will
  never do this for you and neither should an operator, for the same
  duplicate-side-effect reason.
- Never restart Redis with `FLUSHALL` as a troubleshooting step — Redis here
  is ephemeral rate-limit/queue state, not a source of truth, but flushing it
  mid-operation can duplicate ARQ job dedup guards' effective state (a
  previously-deduplicated job id becomes eligible again). Prefer a plain
  restart.
