# Health and Readiness Semantics

Stage 9 Delivery Phase 5. What each probe means, exactly, for anyone
configuring an orchestrator/load balancer or writing a monitor against this
API.

## `GET /health` — liveness

`{"status": "ok"}`, always, unconditionally, as long as the process can
accept a request. Touches no dependency. **Never fails because Google,
Redis, or PostgreSQL is unavailable.** An orchestrator killing/restarting
the process on this check failing would be actively harmful during a
downstream outage — restarting a healthy process does not fix a database or
Google outage, and loses in-flight work for no benefit.

## `GET /ready` — readiness

```json
{"status": "ok", "degraded_dependencies": []}
```

or

```json
{"status": "unavailable"}
```
(HTTP 503, PostgreSQL unreachable)

- **PostgreSQL is checked and blocking** (`503` if unreachable): the API
  cannot safely serve its core functions — reading or writing any user data
  — without it.
- **Redis is checked but never blocking**: reported via
  `degraded_dependencies: ["redis"]` in an otherwise-`200` response. Redis
  absence does not compromise core functionality — rate limiting fails open
  (ADR 0005 D64) and background scheduling/queueing has its own separate,
  unaffected status surface (`GET /scheduled-briefs/status`).
- **Google is never checked.** Provider health is per-connected-account, not
  a property of the API process — there is no meaningful single "is Google
  up" check to make, and probing it on every readiness check would be an
  unnecessary, unbounded-latency provider call on a hot path (`/ready` is
  scraped frequently by design).

An orchestrator should route traffic away from an instance returning `503`
here, but should not necessarily kill it — a `503` clears on its own once
PostgreSQL recovers, with no restart needed.

## `GET /metrics` — operational metrics

Prometheus text exposition format (`prometheus-client`). Unauthenticated,
like the other three infrastructure routes, and exempt from rate limiting
for the same reason (a scraper polling every few seconds must never be
throttled). Contains only bounded-cardinality counters/histograms — see
`apps/api/src/lifeflow_api/metrics.py`'s module docstring for the label-
safety rule this file enforces.

## `GET /config` — public capability flags

Unrelated to health/readiness but co-located in `health.py` for historical
reasons (all four are rate-limit-exempt, unauthenticated, static-cost
routes). `{"google_oauth_enabled": bool}` only.

## Caching

None of the four checks are cached. `/health` touches nothing so there is
nothing to cache. `/ready`'s PostgreSQL check (`SELECT 1`) and Redis check
(a bounded `PING`, `WORKER_HEALTH_CHECK_TIMEOUT_SECONDS`, default 0.5s) are
both cheap enough that running them fresh on every call is preferable to the
staleness risk of caching, at the request rates an orchestrator or scraper
actually generates (typically every few seconds to a minute). Revisit only
with evidence these checks are themselves a measurable load problem.

## Deployment note

`/health`, `/ready`, `/config`, and `/metrics` must all be reachable without
authentication and without the CSRF header the rest of the API requires — a
reverse proxy or orchestrator health check will not have a session cookie.
