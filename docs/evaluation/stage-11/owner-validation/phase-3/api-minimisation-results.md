# Stage 11A Phase 3 — API Response Minimisation Results (S11A-P3-026)

**Status:** PASS · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md)

## Structural finding

Every route in this codebase is built through an explicit Pydantic `response_model=` (never a bare `.dict()`/`.__dict__` dump of an ORM object), so field exclusion is structural, not defensive-filtering: `ConnectedAccountView` declares only `provider/status/granted_scopes/last_sync_at`; `AuditHistoryItem` declares only a closed, pre-validated set of safe fields; `ActionProposalResponse`/`ActionExecutionResponse` never declare a token or ciphertext field. This means an encrypted-token field cannot serialise into a response body even by accident.

## New coverage this phase

`apps/api/tests/test_stage11a_phase3_api_minimisation.py` — 2 tests, both passing: seeds a real connected account with real encrypted ciphertext and a distinctive sentinel plaintext, then inspects the *raw JSON text* of `/connected-accounts` and `/privacy/summary` responses, asserting `encrypted_access_token`/`encrypted_refresh_token`/`access_token`/`refresh_token` never appear by field name, and the sentinel plaintext never appears by value. Also asserts `/connected-accounts`'s response keys are exactly `{provider, status, granted_scopes, last_sync_at}` — no extra field leaked — and `/privacy/summary` never serialises `authorisation_revision`.

## Result

Zero token field names or values found in either response, by direct text search (not merely schema inspection) — this closes the one gap the audit found (the property was previously proven only by construction, never asserted directly against the raw response body). Existing negative-serialization assertions in `test_privacy_api.py`/`test_action_proposals.py` (sensitive sentinel absence in audit metadata) were re-run fresh and remain green.
