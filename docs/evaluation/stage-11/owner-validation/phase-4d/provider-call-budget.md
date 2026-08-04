# Stage 11A Phase 4D — Provider-Call Budget

**Status:** Enforced structurally by the live transport guard, not merely documented · **Date:** 2026-08-04

## Maximum permitted live operations, entire phase

### OAuth

| Operation | Budget |
|---|---:|
| Authorisation initiations | 1 |
| Successful callbacks | 1 |
| Authorisation-code exchanges | 1 |
| Deliberate token refreshes | 0 |
| Revocation attempts | 1 |

### Gmail

| Operation | Budget |
|---|---:|
| `users.getProfile` | ≤1 |
| `users.messages.list` | ≤1 (`maxResults`≤5) |
| `users.messages.get` | 0 |
| Attachment reads | 0 |
| History reads | 0 |
| Drafts created | 0 |
| Messages sent | 0 |
| Modifications | 0 |

### Calendar

| Operation | Budget |
|---|---:|
| `calendars.get` (primary) | ≤1 |
| `events.list` (primary) | ≤1 (`maxResults`≤5) |
| Calendar-list mutations | 0 |
| Watches | 0 |
| Events inserted | 0 |
| Events updated | 0 |
| Events deleted | 0 |

### Retries

| Operation | Budget |
|---|---:|
| Automatic retries | 0 |
| Uncertain-operation retries | 0 |
| Callback replay attempts | 0 |

## Enforcement mechanism

Every non-zero budget row above is enforced structurally, not by convention: [live-transport-guard-results.md](live-transport-guard-results.md)'s `LiveReadOnlyGuardTransport` counts each of the six live operations and raises `LiveGuardBudgetExceededError` before transmission the moment a budget is exhausted — proven by `test_default_budget_matches_the_governing_task_exactly` and `test_call_budget_is_enforced_per_operation`. Every zero-budget row above (drafts, sends, modifications, watches, event writes, message/attachment/history reads, deliberate refresh) is enforced by the guard's allowlist itself — those operations are not merely budgeted at zero, they have no allowlist entry at all, so any attempt is refused outright regardless of count. The `first_google_readonly_smoke.py` operator command (see [read-only-smoke-results.md](read-only-smoke-results.md)) additionally exits non-zero before issuing a call that would exceed the budget it is handed, as a second, independent layer above the transport guard.

## Behaviour on provider-call failure

Per the governing instruction §8: on any provider call failure, the smoke tooling records only its content-free class and status, does not retry, does not deliberately refresh, and proceeds directly to cleanup (§20). No branch in `first_google_readonly_smoke.py` retries a failed or uncertain call.
