# Stage 11A Phase 3 — Log Privacy Results (S11A-P3-022)

**Status:** PASS · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md)

## What was already proven

`test_logging.py` (3 tests, re-run fresh) proves `redact()` catches `authorization`/`cookie`/`access_token`/`refresh_token`/`client_secret`/`api_key`/`password`-shaped patterns at the unit level.

## What this phase added

`apps/api/tests/test_stage11a_phase3_log_privacy.py` — 5 full-workflow cycles, each with 11 fresh sentinel values covering every content type the governing task names: email address, subject, OAuth access token, OAuth refresh token, a second (refreshed) access token, a revoked refresh token, a Gmail-draft body, a calendar-event description, a calendar attendee address, a provider-response message, and a proposal rationale.

Each cycle exercised, against the real application (with the capture handler correctly re-attached *after* `create_app()`'s own `configure_logging()` call, which otherwise silently wipes any earlier handler):

1. Normal operation — user/account/source-item creation.
2. An uncertain (provider-outage-style) write for both a Gmail-draft and a calendar-event proposal, via a scripted registry returning a sentinel-laden provider-response message.
3. A validation failure via a real HTTP request (`PATCH /me` with an invalid timezone, 422).
4. A token refresh through a stubbed OAuth client.
5. A revoked-consent refresh (`InvalidGrantError`).
6. Rate-limit exhaustion against real Redis with a tiny synthetic policy.
7. Full imported-data deletion of the seeded source item.

Logs were captured in memory only (a `JsonFormatter`-backed `StringIO` handler, never written to disk) and searched for all 11 sentinels afterwards. Sanity-checked that the capture is non-vacuous (379+ bytes of real structured-log content per cycle, not an empty buffer).

## Result

Zero sentinels found in captured log output across all 5 cycles (55 total sentinel/cycle checks). No credential, token, session cookie, or private content reached the logs at any workflow stage. Correlation IDs (not personal content) were the only structured field beyond level/logger/message present. No raw exception text or stack trace reached a client response during the validation-failure stage.
