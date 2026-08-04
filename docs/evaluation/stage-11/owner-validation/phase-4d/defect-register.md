# Stage 11A Phase 4D — Defect Register

One defect was found during this phase's live-connection leakage
inspection (§19) and later strengthened during the PR #16 merge-integrity
review; a second, unrelated defect was found by that same review's required
CI checks. No other defects were found across the pre-live engineering
phase, the live connection sequence, or the post-cleanup verification
pyramid.

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
- **Update (PR #16 merge-integrity review):** the fix above matched by
  exact, case-sensitive path only. Reviewed again before merge, this was
  found not to generalise to a differently-cased path, a denied-consent
  error redirect (which carries `state` without `code`), or any future
  route that happens to carry one of these keys. Replaced with a closed
  sensitive-key vocabulary (`code`, `state`, `nonce`, `id_token`,
  `access_token`, `refresh_token`, `client_secret`, `code_verifier`,
  `session`, `session_state`) applied to every route's query string —
  matching keys are redacted case-insensitively after percent-decoding,
  repeated keys are all redacted, unrelated parameters are preserved, and
  an unparseable query string is redacted wholesale rather than emitted
  unfiltered. 10 further tests, including an end-to-end run through
  uvicorn's real `AccessFormatter`, for 19 total in `tests/test_logging.py`.

## D-4D-02 — resilience E2E journeys broken by the new write kill switch

- **Found during:** PR #16's required CI checks (`E2E — outage resilience
  journeys`), during the merge-integrity review — not by any script or
  test written as part of Phase 4D's own pre-live engineering.
- **Root cause:** `journey-b-uncertain-write.spec.ts` and
  `stage10-uncertain-execution-fixture.spec.ts` (both pre-existing, Stage
  9/10 coverage) each execute a real Gmail draft write against the fake
  Google server and expect `effective_status: "uncertain"` — the fake
  server deliberately withholds its response to prove an uncertain write
  is never retried, including across an API restart. Stage 11A Phase 4D's
  `GOOGLE_PROVIDER_WRITES_ENABLED` kill switch defaults `false` and was
  never added to `scripts/resilience-api-env.sh` (the single source of
  truth both the dedicated resilience API's initial launch and Journey
  B's mid-test restart source), so the kill switch intercepted the write
  before it ever reached the fake server — turning the intended
  `"uncertain"` outcome into an unconditional `"failed"`.
- **Impact:** both journeys failed identically (`Expected: "uncertain",
  Received: "failed"`) on the first CI run against the final PR head; a
  rerun of just the failed job reproduced the same failure deterministically
  (not a flake — the sibling `E2E — demo journey` failure on the same CI
  attempt was a genuine, unrelated flake that passed clean on rerun).
- **Severity:** blocking for merge (a required CI check), but with zero
  live-provider or credential impact — this only affects the fake-provider
  resilience suite's own dedicated, disposable API instance.
- **Disposition: FIXED.** Added
  `export GOOGLE_PROVIDER_WRITES_ENABLED=true` to
  `scripts/resilience-api-env.sh`, since these journeys exist specifically
  to prove real execution behaviour. No test assertions were weakened,
  skipped, or removed to reach green.
