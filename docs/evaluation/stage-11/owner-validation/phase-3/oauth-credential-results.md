# Stage 11A Phase 3 — OAuth Credential Handling Results (S11A-P3-012–016)

**Status:** PASS · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md)

## Existing evidence, re-run fresh

`test_token_cipher.py`, `test_accounts_service.py`, `test_google_token_service.py` — all passing. Together they prove: tokens are encrypted before ever reaching the database (`test_no_plaintext_token_reaches_the_database`), the AES-GCM envelope round-trips and rejects tampering/wrong-key/malformed input, refresh is serialized per-account via a row lock, a rejected refresh token marks the account `revoked` rather than surfacing Google's rejection directly, disconnect drops both tokens, and execution-context binding rejects wrong-account/provider-mismatch/inactive-account/revision-mismatch/missing-scope cases.

## New coverage this phase

`apps/api/tests/test_stage11a_phase3_token_sentinel_search.py` (S11A-P3-014) — 5 lifecycle cycles, each with a fresh, unique sentinel access/refresh-token pair, searched for after every stage:

1. **Create** — sentinel tokens stored via `ConnectedAccountService.store_tokens`.
2. **Refresh** — the stored token is already expired, forcing a real refresh call through a stubbed OAuth client returning a second, distinct sentinel access token.
3. **Disconnect** — `ConnectedAccountService.disconnect`.
4. **Full account deletion** — the complete preview→confirm→run pipeline.

After every stage, all three sentinel values were searched for across: every content-bearing PostgreSQL column (`connected_accounts`, `audit_events`, `users`, via a raw `to_jsonb(...)::text ILIKE` scan), the real dev Redis instance (every key, `string`/`hash` values), and captured structured logs (an in-memory `JsonFormatter` handler, DEBUG level, for the full cycle). Zero occurrences found anywhere at any stage, in any of the 5 cycles (25 total sentinel-value/stage/cycle combinations checked).

## Result

Plaintext tokens never reach any storage surface outside the one encrypted envelope column, and even that column is cleared on disconnect and removed on deletion. Cross-account token reuse remains rejected (existing execution-context tests). No gap found beyond what was already comprehensively covered — this phase's contribution is the end-to-end search proof the audit found missing.
