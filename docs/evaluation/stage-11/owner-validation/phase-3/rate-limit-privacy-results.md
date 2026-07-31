# Stage 11A Phase 3 — Rate-Limit Privacy Results (S11A-P3-029)

**Status:** PASS · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) · [redis-residual-analysis.md](redis-residual-analysis.md)

## Existing evidence, re-run fresh

All 5 named files re-run this phase, all passing: `test_rate_limit_policy.py`, `test_rate_limit_ip.py`, `test_rate_limiter.py` (real Redis), `test_rate_limiting_api.py` (real Postgres + Redis, full route table, re-run 5 consecutive times for this phase's repetition requirement), `test_rate_limit_uvicorn_regression.py` (a real Uvicorn subprocess, not `ASGITransport`).

Together they prove: Redis stores only an HMAC digest, never a raw subject or payload (`test_redis_stores_no_raw_subject_or_payload`); a spoofed `X-Forwarded-For` header from an untrusted peer is ignored (`test_spoofed_forwarded_header_from_untrusted_peer_is_ignored`, confirmed against a real Uvicorn subprocess so Uvicorn's own header-trust middleware is genuinely exercised, not bypassed by `ASGITransport`); separate users and separate anonymous IPs get separate buckets (cross-owner isolation); Redis unavailability fails open rather than blocking the request, without ever creating a duplicate execution or deletion operation (the database-level guards remain authoritative regardless of the limiter's state).

## Direct inspection this phase

A real bucket was created and inspected via `redis-cli` (see [redis-residual-analysis.md](redis-residual-analysis.md)) — confirmed the key contains only an HMAC digest and the value only a token count and timestamp, no raw subject.

## Result

No gap found. Raw IPs/user ids never appear in Redis keys, logs, or metrics (also independently confirmed by this phase's log-privacy sentinel scan). Test controls cannot disable production limits (rate limiting's own enablement flag is a normal settings value, not a request-controllable one, and is not among the test-control-isolation flags — it has no production-refusal requirement because it fails open, not open-by-bypass).
