# Emergency-Stop Plan

**Status:** Designed; rehearsed in dry runs, never triggered against a real account · **Date:** 2026-08-01

Companion: [test-account-cleanup-plan.md](test-account-cleanup-plan.md) · [first-connection-runbook.md](first-connection-runbook.md) · [dry-run-results.md](dry-run-results.md)

A future connection or provider-write test must stop immediately for any of the 19 conditions below (every condition named in the governing instruction §15).

| # | Condition | Detection | Immediate action | Evidence to preserve | Evidence not to preserve | Severity | Restart criteria |
|---|---|---|---|---|---|---|---|
| 1 | Unexpected OAuth scope | Manual review of the Google consent screen against [oauth-scope-matrix.md](oauth-scope-matrix.md) before clicking Allow | Do not click Allow; abandon the flow | The unexpected scope string (name only) | Screenshot containing any account identifier beyond the scope list | P0 | Re-derive scopes from `google_scopes.py`, fix the OAuth client config, retry |
| 2 | Account mismatch | Consent screen or post-connection identity check shows a different Google account than Account A | Do not complete consent; if already completed, disconnect immediately | Which account appeared (email only) | The account's own content | P0 | Verify only Account A is signed into the browser profile used for testing; retry |
| 3 | Wrong Google Cloud project | OAuth client id in the consent screen URL does not match the dedicated project's client id | Abandon the flow | The mismatched client id (not secret) | — | P0 | Correct `.env`, retry |
| 4 | Wrong callback URI | Browser address bar after redirect does not match `first-connection-runbook.md` step 15 | Abandon the flow before consent | The observed URI (redacted of any code/state) | The raw URI with `code`/`state` values | P0 | Fix Cloud Console/`.env` mismatch, retry |
| 5 | Token visible in browser or URL | Manual inspection of dev tools/URL bar shows a token-shaped value | Immediately revoke the connection (Google Account → Security → Third-party access), disconnect in LifeFlow | The fact that this occurred, and where | The token value itself | P0 | Root-cause before any retry — this must not recur |
| 6 | Token visible in logs, Redis, metrics, or Audit History | Sentinel scan (existing Phase 3 methodology) | Revoke and disconnect immediately; purge the affected log/Redis/metrics data | The fact and location | The token value itself | P0 | Root-cause and add a regression test before any retry |
| 7 | Credential stored outside the v2 envelope | `credential_connection_gate` reports non-zero after the connection | Investigate before any further action; do not proceed to Decision 2 | Gate output (bounded counts only) | — | P0 | Root-cause via Phase 4A tooling before retry |
| 8 | Connection gate becomes blocked | Gate exits non-zero at any preconnection check | Do not proceed | Gate output | — | P0 | Resolve the blocking condition, re-run gate, retry |
| 9 | Cross-owner account binding | A second LifeFlow user's session ends up bound to Account A's credential | Disconnect immediately; investigate | Which LifeFlow user ids were involved | — | P0 | Root-cause via the existing OAuth-binding tests before retry |
| 10 | Unexpected Gmail-send capability | Any evidence a send occurred that LifeFlow did not explicitly, manually trigger via a reviewed draft-only path | Revoke immediately | What was observed | Message content | P0 | Root-cause — this should be structurally impossible per [oauth-scope-matrix.md](oauth-scope-matrix.md); treat as a P0 defect in the client, not just an incident |
| 11 | Calendar edit or delete capability | Any evidence an existing event was modified/removed by LifeFlow | Revoke immediately | What was observed | Event content | P0 | Same as above |
| 12 | Duplicate provider object | Two drafts or two events created from one approval | Stop further writes; manually clean up the duplicate | Draft/event ids (not content) | — | P1 | Root-cause idempotency before retry |
| 13 | Automatic uncertain-write retry | Logs show a retry of a write whose outcome was uncertain | Stop; do not retry manually either until root-caused | Log excerpt (content-free) | — | P1 | Fix retry logic, add a regression test |
| 14 | Provider write before explicit write authorisation | Any Gmail draft/Calendar insert attempted under Decision 1 only | Stop; treat as a process violation, not just a technical one | What was attempted | — | P0 | Requires owner review before any further testing |
| 15 | Real or confidential information entering the account | Owner notices anything beyond the synthetic datasets in [synthetic-gmail-dataset-plan.md](synthetic-gmail-dataset-plan.md)/[synthetic-calendar-dataset-plan.md](synthetic-calendar-dataset-plan.md) | Remove the content immediately from the Google account | That it happened and was removed | The real content itself | P0 | Review [real-provider-data-boundary.md](real-provider-data-boundary.md) before any further testing |
| 16 | Inability to revoke or disconnect | Revocation/disconnect action fails or cannot be confirmed | Escalate to manual Google Account security-settings revocation | The failure mode | — | P0 | Must be resolved before any further connection attempt |
| 17 | Deletion or cleanup inconsistency | Post-cleanup verification (per [test-account-cleanup-plan.md](test-account-cleanup-plan.md)) finds residue | Re-run cleanup; escalate if residue persists | What residue was found (content-free) | — | P1 | Resolve before declaring cleanup complete |
| 18 | Unexplained database credential row | A `connected_accounts` row with credential fields exists that no known authorised connection created | Investigate before any further action | Row metadata (ids, timestamps — never decrypted content) | — | P0 | Root-cause before any retry |
| 19 | Test-control activation in the real-provider stack | `E2E_TEST_CONTROLS_ENABLED=true` or `GOOGLE_API_ORIGIN_OVERRIDE` set while attempting a real connection | Stop immediately | The setting that was active | — | P0 | Fix configuration, re-verify via the preconnection readiness command, retry |

## General principle

Every P0 stop condition above requires resolving the root cause — not merely retrying — before any further connection or write attempt. No condition in this table may be downgraded to obtain a PASS decision.
