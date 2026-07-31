# Stage 11A Phase 2 — Token Expiry, Refresh, and Revoked-Consent Results

**Status:** Complete · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) (S11A-P2-020 to 023)

## Expired access token with valid refresh (S11A-P2-020)

PASS, 3 repetitions. Bounded refresh occurs via `GoogleTokenService.get_valid_access_token`; the exact connected account is used (row-scoped, never a bare `(user, provider)` lookup for execution — Stage 7 remediation); the row lock (`with_for_update()`) prevents duplicate concurrent refresh; credentials remain encrypted at rest (`AesGcmTokenCipher`); the original operation resumes safely. Evidence: `test_google_token_service.py` re-run.

## Concurrent refresh attempts (S11A-P2-021)

PASS, **10 concurrency rounds × 5 simultaneous callers** (the required repetition count — the pre-existing test covered only 1 round × 2 callers). Exactly one refresh wins every round; no token corruption; no cross-account use (verified separately for two *different* users refreshing simultaneously, proceeding fully independently rather than serialising against each other — proving the row lock is per-account, not global).

- New: `test_stage11a_phase2_concurrent_oauth_refresh.py::test_ten_rounds_of_five_concurrent_refreshes_never_double_refresh` — 10/10 rounds, exactly 1 real OAuth call each.
- New: `test_stage11a_phase2_cross_user_isolation.py::test_concurrent_refresh_for_different_users_proceeds_independently` — 3 rounds, both users' refreshes succeed independently (1 call each, not serialised to 1 total).

## Refresh failure (S11A-P2-022)

PASS, 3 repetitions. Safe classification, no raw token or provider body exposed, appropriate reauthorisation guidance. Evidence: `test_google_token_service.py::test_missing_refresh_token_requires_reauthorisation` and related cases, re-run.

## Revoked consent (S11A-P2-023)

PASS, 3 repetitions. Google's `invalid_grant` classifies to `InvalidGrantError` → `AccountStatus.revoked` (distinct from `authentication_expired`) — non-retryable, reconnection guidance shown (not temporary-outage copy — confirmed rendered correctly by the manual walkthrough's screenshot 2, `sync-error-notice` with "reconnect Google"), ingestion stops safely, no write attempted, existing imported data not silently deleted, disconnect/deletion remain distinct API operations, no automatic reconnection. Evidence: `test_google_token_service.py::test_invalid_grant_marks_account_revoked_and_raises`, `test_execution_invalid_grant_marks_revoked_not_context_changed`, `test_google_oauth.py::test_revoked_grant_is_a_distinct_metric_outcome_not_unknown_error`, all re-run 3×.

No real Google credentials were used anywhere in this section — every case uses a stub OAuth transport (`_StubOAuthClient`) or the fake Google server's `permanent_failure` scenario.
