# Stage 11A Phase 4D — Read-Only Smoke Results

Command: `uv run python3 scripts/first_google_readonly_smoke.py --phase4d-live`
(run from `apps/api`, against the real Account A connection, immediately
after the credential-storage checks passed).

## Preconditions checked by the script itself before any network call

- `GOOGLE_PROVIDER_WRITES_ENABLED` is `false` (aborts otherwise).
- No fake-provider test controls (`e2e_test_controls_enabled`,
  `google_api_origin_override`) are active — this is a genuine live run,
  not a rehearsal.
- Exactly one credential-bearing Google `connected_accounts` row exists.
- The connection gate is clear (`unversioned=0 legacy_known=0
  legacy_unknown=0`).

## Output (content-free by construction)

```
GMAIL_PROFILE_MATCH=true
GMAIL_MESSAGE_LIST_REQUEST=PASS
GMAIL_RESULT_COUNT=4
CALENDAR_PRIMARY_METADATA_REQUEST=PASS
CALENDAR_EVENT_LIST_REQUEST=PASS
CALENDAR_RESULT_COUNT=0
PROVIDER_WRITES=0
PERSISTED_PROVIDER_ITEMS=0
```

Exit code `0`.

## Boundary checks

- Exactly the four authorised calls were made, each exactly once, in the
  fixed order (Gmail `getProfile` → Gmail `messages.list` → Calendar
  `calendars.get(primary)` → Calendar `events.list(primary)`) —
  `LiveReadOnlyGuardTransport` would have raised
  `LiveGuardViolationError`/`LiveGuardBudgetExceededError` before any
  sixth call or any non-allow-listed `(method, host, path)` tuple; neither
  fired.
- The access token was used exactly as decrypted from storage — the
  script bypasses `GoogleTokenService`'s refresh-capable path entirely, so
  no code path in this run could ever have issued a token-refresh request.
- Every identifying value (the Gmail profile email, the calendar id) was
  discarded immediately after use (`del email`, `del calendar_id`) and
  never appears in the printed output, matching the content-free contract
  the script's own docstring commits to.
- `PROVIDER_WRITES=0` and `PERSISTED_PROVIDER_ITEMS=0` are asserted by the
  script itself, not merely absence of contrary evidence — no Gmail draft,
  no Calendar event, and no `SourceItem` was created by this run (confirmed
  independently in `credential-storage-results.md` and re-confirmed after
  this run: `source_items` count for this account remained `0`).
