# Stage 11A Phase 4D — Defect Register

One defect was found during this phase's live-connection leakage
inspection (§19). No other defects were found across the pre-live
engineering phase, the live connection sequence, or the post-cleanup
verification pyramid.

## D-4D-01 — uvicorn access log leaked OAuth callback query string

- **Found during:** §19 leakage/residual-data inspection, real live
  connection.
- **Root cause:** `scripts/demo.sh` launches uvicorn without
  `--no-access-log`. Uvicorn's default `LOGGING_CONFIG` gives
  `uvicorn.access` `propagate=False` and its own dedicated handler, so it
  never passes through this application's `JsonFormatter`/`redact()`
  backstop — it writes the raw request line, including the query string,
  straight to stdout.
- **Impact:** the real, single-use OAuth authorisation `code` and `state`
  values from the connector-consent callback were printed in plaintext to
  the owner's local terminal during this connection.
- **Severity:** non-blocking. Both values are single-use and the callback
  route rejects any replay of an already-consumed pair (existing
  regression test), so the printed values could not be reused. Nothing was
  persisted to a file or transmitted externally — local terminal stdout
  only, for a process the owner started themselves.
- **Disposition: FIXED, not merely documented.**
  `lifeflow_api/logging_setup.py` now attaches
  `UvicornAccessQueryStringRedactor` (a `logging.Filter`) directly to the
  `uvicorn.access` logger — filters attached to a logger run before
  dispatch to that logger's own handlers regardless of `propagate` — which
  rewrites the query string on `/auth/google/callback` and
  `/connected-accounts/google/callback` specifically to `?[REDACTED]`,
  leaving every other route's access log line untouched. 9 new tests in
  `tests/test_logging.py` cover both callback paths, a non-OAuth path
  (proving the fix isn't overly broad), the no-query-string case, the
  filter's `True` return contract, and that `configure_logging()` actually
  registers it.
- **Residual risk:** none identified for future connections through this
  application's own launch path. `--no-access-log` was deliberately not
  used instead, to preserve access logging's general operational value for
  every non-OAuth route.
