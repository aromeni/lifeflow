# Stage 11A Phase 4D — Zero-Write Enforcement Results

## Live configuration proof

The read-only smoke sequence itself already refuses to run if
`GOOGLE_PROVIDER_WRITES_ENABLED` is `true` (see
`read-only-smoke-results.md`'s precondition list). Separately, the actual
write-blocking call path was inspected directly against the *live*
settings object the running API process uses:

```
google_provider_writes_enabled (live) = False
```

`google_wiring.py::build_google_executor_registry` checks this flag
**before** calling `build_google_token_service` or constructing either
Google executor — when the flag is false it returns
`ProviderWritesDisabledExecutorRegistry()` unconditionally, at the top of
the function. No already-approved proposal, replayed request, or other
runtime state can reach a real Gmail/Calendar write call while the flag is
false, because no token is even decrypted on that path.

## Fresh negative controls

Re-ran, right now, against the current branch (not from cached prior
results):

```
tests/test_google_route_integration.py::test_gmail_write_blocked_when_provider_writes_disabled PASSED
tests/test_google_route_integration.py::test_calendar_write_blocked_when_provider_writes_disabled PASSED
2 passed in 3.18s
```

Both assert the route returns `error_code=provider_writes_disabled`
without any mock Gmail/Calendar client method being invoked.

## Result

`PROVIDER_WRITES=0` for the entire live window (also directly asserted by
`first_google_readonly_smoke.py`'s own output). No Gmail draft was
created, no Calendar event was inserted, updated, or deleted, at any point
during Account A's connection.
