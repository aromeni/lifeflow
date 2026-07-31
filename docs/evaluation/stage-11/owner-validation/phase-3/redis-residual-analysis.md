# Stage 11A Phase 3 — Redis Residual Analysis (S11A-P3-024)

**Status:** PASS · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) · [storage-surface-inventory.md](storage-surface-inventory.md)

## Direct inspection (real `redis-cli`, dev instance)

A real rate-limit bucket was created via the actual `RateLimiter`/`bucket_key`/`hash_subject` code path (subject: a realistic-looking raw user id, `"real-user-id-12345"`) and inspected directly:

```
KEY: ratelimit:v1:phase3-inspection:9e0207b2752adaaf9df2455db39fe51db7e6072141a215aca3dc70fa5be3ceb4
TYPE: hash
HGETALL: tokens=4, ts=1785524967.0554
TTL: 7192 (bounded, matches the configured token-bucket window)
```

The raw subject `"real-user-id-12345"` does not appear anywhere in the key name or value — only its 64-character HMAC-SHA256 digest. The hash value carries only a token count and a refill timestamp, never content. The database was flushed clean after inspection (`FLUSHDB`).

## Automated 5-cycle inspection

`test_stage11a_phase3_token_sentinel_search.py` and `test_stage11a_phase3_log_privacy.py` each independently scan every real Redis key (`string`/`hash` types) across 5 full lifecycle/workflow cycles, searching for sentinel token/email/subject values planted earlier in each cycle — zero occurrences found in any of the 10 total cycles across both files.

## Key namespace inventory

- `ratelimit:v1:<policy_code>:<hmac_digest>` — token-bucket state only, HMAC-pseudonymised subject, bounded TTL.
- `arq:result:*`/`arq:job:cron:*` — library-owned job bookkeeping; values contain only a function name, an opaque database-row UUID, timing fields, and a success flag (re-confirmed against Phase 2's original direct inspection, unchanged this phase).

## Restart/recovery check

Redis was restarted (`docker compose restart redis`) mid-session during this phase's dependency/container work; PostgreSQL remained authoritative throughout (all durable state — proposals, executions, deletion operations — lives in PostgreSQL, never Redis), consistent with Phase 2's exhaustive outage-recovery evidence.

## Result

Every key has an appropriate TTL or a documented durable justification (arq's own bookkeeping). No plaintext private content, token, raw email address, raw account identifier, complete proposal payload, source-item content, or browser session secret was found in any key at any point across 5+ inspection cycles. No unexplained key was found.
