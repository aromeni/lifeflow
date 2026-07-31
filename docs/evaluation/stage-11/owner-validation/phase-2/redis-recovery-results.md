# Stage 11A Phase 2 — Redis Outage and Recovery Results

**Status:** Complete · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) (S11A-P2-013 to 015)

## Outage and recovery (5 repetitions)

Real `docker compose stop redis` / `docker compose start redis` against the dev-compose container, exercised 5 times via `journey-d-dependency-health.spec.ts` (re-run 5× this phase) plus the targeted unit/integration suites for each affected path:

| Context | Result | Evidence |
|---|---|---|
| Ordinary read traffic | PASS — unaffected (Redis is not on the read path) | N/A — read path never touches Redis |
| Rate limiting | PASS — fails open (`degraded=True, allowed=True`), the one approved fail-open case (ADR 0005 D64) | `test_rate_limiter.py` re-run |
| Worker enqueue | PASS — durable DB row created regardless; enqueue failure never blocks the durable write | `test_scheduled_briefs_enqueue_resilience.py` re-run |
| Deletion enqueue | PASS — same durable-row-first guarantee | `test_deletion_engine_enqueue_resilience.py` re-run |
| Scheduled-brief enqueue | PASS — same | `test_scheduled_briefs_enqueue_resilience.py` re-run |
| Readiness checks | PASS — `/ready` reports `degraded_dependencies: ["redis"]` inside a 200, never blocking | `journey-d-dependency-health.spec.ts` |

## Fail-open scope confirmed narrow

Rate limiting is the *only* approved fail-open path. Every database-backed execution guard (proposal approval/execution, deletion confirmation, brief generation idempotency) remains fully enforced with Redis down — none of these depend on Redis for correctness, only for the optional rate-limit and job-queue layers. Confirmed by re-running `test_action_concurrency.py` and `test_execution_durability.py` with no change in behaviour.

## Trusted-proxy / spoofed-header handling during degradation

Re-ran `rate_limit_ip.py`'s trusted-proxy tests; spoofed `X-Forwarded-For` headers gain no additional trust merely because Redis is degraded — the trust boundary is evaluated independently of rate-limiter availability.

## Redis inspection after recovery (S11A-P2-015)

`redis-cli --scan` + `GET` against the real dev Redis instance found two key families: `arq:result:*`/`arq:job:cron:*` (arq's own job bookkeeping) and rate-limiter bucket keys. Inspected contents:

- `arq:result:*` values contain only the function name, an internal `DataDeletionOperation`/`ScheduledBriefRun` primary-key UUID (an opaque database row id, never a user-facing identifier, email, or token), timing fields, and a boolean success flag — e.g. `{"f": "run_deletion_operation", "a": ["4340b69a-..."], "s": true, ...}`. No email address, no OAuth token, no proposal payload, no free-text content.
- Rate-limiter bucket keys (when present) are HMAC-SHA256 digests via `hash_subject` — never a raw user id, email, or IP, confirmed by `rate_limiter.py`'s implementation and `test_rate_limiter.py`.

Zero raw email addresses, zero OAuth tokens, zero proposal/draft/event payloads, zero free-text private content in any key inspected.

## Post-recovery drain

Backlog drains without duplication: re-running the enqueue-resilience suites after each of the 5 outage cycles showed identical row counts to a Redis-never-down baseline.
