# Stage 11A Phase 3 — Session and Authentication Security Results (S11A-P3-007–011)

**Status:** PASS · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md)

## Configuration (code-inspected)

`main.py:208-213` — `SessionMiddleware(secret_key=_session_secret(settings), session_cookie="lifeflow_session", same_site="lax", https_only=environment=="production", max_age=28800)`. `_session_secret()` raises `RuntimeError("SESSION_SECRET must be set in production.")` when unset in production; dev/test get an ephemeral random secret per process. CSRF: `security/csrf.py::CsrfProtectionMiddleware` requires a custom `X-LifeFlow-CSRF: 1` header on every non-safe method, relying on the header plus `SameSite=Lax` rather than a token-based scheme (documented rationale in the module).

## Existing evidence, re-run fresh

`test_auth_api.py` (7 tests, all passing): unauthenticated `/me` returns 401; dev-login sets `httponly`/`samesite=lax`; logout ends the session; CSRF header is required on state-changing requests; a bit-flipped (tampered) session signature is rejected with 401.

## New coverage this phase

`apps/api/tests/test_stage11a_phase3_session_security.py` — 7 tests, all passing:

- **Session-expiry boundary (S11A-P3-010)**: using a fixed, known `session_secret` and a custom `itsdangerous.TimestampSigner` subclass that signs with a caller-chosen timestamp, a session signed one second before the 8h `max_age` boundary is accepted (200); one second past it is rejected (401, `unauthenticated`). Proves the server enforces the configured TTL rather than trusting an unexpired-looking signature indefinitely.
- **Malformed, non-tampered cookie (S11A-P3-009)**: 6 distinct garbage cookie values (a plain string, empty string, `"...."`, a 500-character string, binary/control-byte content, a SQL-injection-shaped string) each produce a clean 401 with no stack trace and no `itsdangerous`-internals leaked in the response body.

## Result

Every case returns a controlled 401/403, never a 500, never a disclosed authentication internal. Logout invalidates future protected requests. Production requires a real, non-empty session secret (existing `RuntimeError` guard, unchanged). Session values never appear in logs (confirmed as part of the log-privacy sentinel scan, which plants and searches for a real session cookie value).
