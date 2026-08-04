# Stage 11A Phase 4D — Leakage and Residual-Data Inspection

## Audit trail

The `account.connected` event's `safe_metadata_json` was inspected
directly:

```json
{"provider": "google", "scope_count": 4, "authorisation_revision": 1}
```

No email address, token, scope URL, or other identifying value. Clean.

## Application logging

`lifeflow_api.auth` and `lifeflow_api.connected_accounts` only log fixed
literal warning messages on failure paths (`exc_info=True`, passed through
`redact()` via `JsonFormatter`); the success path this connection took
logs nothing at info level. No route handler interpolates a request URL,
query string, or token into a log message.

## Finding: uvicorn's default access log leaked the OAuth callback query string

Inspection of `scripts/demo.sh` showed uvicorn is launched without
`--no-access-log`. Uvicorn's own default `LOGGING_CONFIG` gives
`uvicorn.access` its own handler with `propagate=False`, so it never
passes through this application's `JsonFormatter`/`redact()` at all — it
writes the raw HTTP request line straight to stdout, including the query
string. During this connection, that meant the real, single-use OAuth
`code` and `state` values from
`/connected-accounts/google/callback?code=...&state=...` were printed in
plaintext to the owner's terminal.

Mitigating factors present at time of discovery:
- Both values are single-use; the connector callback flow rejects any
  replay of an already-consumed `(code, state)` pair
  (`test_replaying_a_consumed_connector_callback_is_rejected`), so the
  printed values could not be reused even by someone with terminal access.
- Nothing was persisted to a file or shipped externally — this was local
  terminal stdout only, for the one process the owner started themselves.

**Classification:** LOCAL CALLBACK-QUERY DISCLOSURE THROUGH FRAMEWORK
ACCESS LOG — SINGLE-USE VALUES EXPOSED TO THE OWNER'S LOCAL TERMINAL; NO
REPOSITORY, CI OR EXTERNAL EVIDENCE EXPOSURE; ACCESS LATER REVOKED AND
CREDENTIALS REMOVED. Supporting facts, established by inspection rather
than assumed:
- The access-log line is emitted only after the route handler returns a
  response (it records the response status code), and the connector
  callback handler exchanges the code and consumes/invalidates the state
  value *before* returning — so by the time the line was printed, both
  values were already single-use-consumed by the app itself, independent
  of the later Google-side revocation.
- `scripts/demo.sh` performs no output redirection of its own (checked
  directly: no `>`/`tee` in the script), so no repository-controlled
  mechanism wrote this line to a file; this connection was run via
  `demo.sh`, never via `e2e.sh` or CI, so no CI artifact was ever in the
  path either. Whether the owner's own terminal application separately
  persists scrollback (e.g. session logging, tmux capture) is outside
  this repository's visibility and cannot be proven one way or the other
  — stated honestly rather than assumed absent.
- No evidence file, screenshot, or test report created during this phase
  ever captured raw terminal output; only browser screenshots and typed
  confirmation phrases were requested from the owner.
- A full-repository pattern scan of the Phase 4D diff for query-string-
  shaped content (`code=`, `state=`, `access_token=`, etc.) found no real
  value — only placeholder config, function-call keyword arguments, test
  fixture literals, and this file's own prose.
- Independent of the logging fix, the resulting credential itself was
  later fully revoked (objective HTTP 200 from Google) and the local
  credential cleared (`revocation-results.md`) — a second, independent
  invalidation on top of the code/state pair's own single-use design.

This is recorded as a real, non-blocking defect — see
`defect-register.md` — and was fixed within this phase rather than merely
documented as accepted risk. The first version of the fix
(`lifeflow_api/logging_setup.py`'s `UvicornAccessQueryStringRedactor`, a
`logging.Filter` attached directly to the `uvicorn.access` logger — filters
attached to a logger run regardless of that logger's `propagate` setting)
matched by exact path only; a subsequent PR #16 merge-integrity review
found that would not generalise to a differently-cased path, a
denied-consent error redirect, or a future route carrying one of these
keys, and replaced it with a closed sensitive-key vocabulary applied to
every route's query string (see `defect-register.md`'s D-4D-01 update).
Verified with 19 tests in `tests/test_logging.py`, including an end-to-end
run through uvicorn's real `AccessFormatter`.

## Residual-data sweep (post-disconnect)

Every table with a foreign key into `connected_accounts`, filtered on this
connection's row id:

```
source_items:             0
action_proposals:         0
data_deletion_operations: 0
```

No content of any kind — imported, proposed, or scheduled for deletion —
was ever associated with this connection.
