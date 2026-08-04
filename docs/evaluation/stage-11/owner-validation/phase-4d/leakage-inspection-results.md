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

This is recorded as a real, non-blocking defect — see
`defect-register.md` — and was fixed within this phase rather than merely
documented as accepted risk:
`lifeflow_api/logging_setup.py` now registers
`UvicornAccessQueryStringRedactor`, a `logging.Filter` attached directly
to the `uvicorn.access` logger (filters attached to a logger run
regardless of that logger's `propagate` setting), which rewrites the query
string on `/auth/google/callback` and `/connected-accounts/google/callback`
specifically to `?[REDACTED]` before the access-log line is formatted. No
other route's access log line is altered. Verified with 9 new unit tests
in `tests/test_logging.py`, including a direct construction of uvicorn's
own 5-tuple `LogRecord.args` shape (`AccessFormatter.formatMessage`), a
proof that non-OAuth paths are untouched, and a proof
`configure_logging()` actually registers the filter.

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
