# Stage 11A Phase 4D — Provider-Write Block Results

**Status:** PASS — hard kill switch implemented and verified · **Date:** 2026-08-04

## Design

`Settings.google_provider_writes_enabled: bool = False` (`config.py`) — a third, independent operator flag alongside `google_oauth_enabled` and `google_oauth_initiation_enabled`, following the exact same shape and naming convention Phase 4C established. It gates `create_gmail_draft`/`create_calendar_event` execution only; disconnect, sync (reads), and OAuth initiation are unaffected.

`google_wiring.py::build_google_executor_registry` — the single place both write executors (`GoogleGmailDraftExecutor`, `GoogleCalendarEventExecutor`) are ever constructed — now checks this flag immediately after confirming Google integration is otherwise ready, and returns a new `ProviderWritesDisabledExecutorRegistry` (`action_executors.py`) instead of the real registry when it is false. This registry's `.execute()` raises `FinalExecutionError("provider_writes_disabled")` unconditionally, for both action types, before any Gmail/Calendar client method is called — no provider HTTP request is ever attempted.

This reuses the exact machinery `ActionProposalService.execute()` already has for a genuine wiring gap (`UnavailableGoogleExecutorRegistry`, "always a controlled, final failure — never a silent fallback to simulation," per its own docstring), giving the write-block a distinct, unambiguous error code (`provider_writes_disabled`, not `google_execution_unavailable`) so the two causes — "Google isn't configured" vs. "writes are deliberately disabled" — are never confused in an audit trail.

## Requirements checklist

| Requirement | How satisfied |
|---|---|
| Disabled by default | `bool = False` in `Settings` |
| Configuration cannot be supplied through a user request | Server-side `Settings` field, populated only from environment/`.env`; no route reads or accepts it |
| Checked before proposal execution reaches a provider client | `build_google_executor_registry` returns the blocking registry before `GoogleGmailDraftExecutor`/`GoogleCalendarEventExecutor` are ever constructed |
| Checked by workers as well as the API process | No worker/scheduler code path constructs `ActionProposalService` or calls `build_google_executor_registry` at all — `grep` across `worker_app.py`/`scheduled_briefs.py` confirms zero matches; execution is exclusively a synchronous, per-request, human-approval-gated API route |
| Produces a safe, explicit failure | `FinalExecutionError("provider_writes_disabled")` → `outcome=failed`, `error_code="provider_writes_disabled"`, safe fixed message, audited as `execution.failed` |
| Creates no pending uncertain execution | The registry raises synchronously before any network call — never reaches the `uncertain` branch (that requires a `GoogleTransientError` from an actual attempted call, which never happens) |
| Cannot be bypassed through replay | `build_google_executor_registry` is called fresh on every `execute()` request; there is no cache or stored decision to replay around |
| Cannot be bypassed through an existing approved proposal | The gate is unconditional on the executor-construction path, independent of proposal approval state — an already-approved proposal is refused exactly like a freshly-approved one |
| Does not expose secrets | No credential, token, or account value appears in the error code, message, or audit metadata |
| Has focused regression tests | See below |

## Regression tests

`apps/api/tests/test_google_route_integration.py`:

- `test_gmail_write_blocked_when_provider_writes_disabled` — real, correctly-scoped, connected Google account; approves and executes a `create_gmail_draft` proposal with `google_provider_writes_enabled=False`; asserts `effective_status=="failed"`, `error_code=="provider_writes_disabled"`, and **zero** Gmail HTTP requests beyond the OAuth token exchange (the mock transport raises `AssertionError` on any other path, and the test asserts the captured-calls list is empty).
- `test_calendar_write_blocked_when_provider_writes_disabled` — identical shape for `create_calendar_event`; zero Calendar HTTP requests.
- Both pass; the existing `test_real_gmail_execution_calls_exactly_drafts_create` and `test_real_calendar_execution_calls_exactly_events_insert_with_send_updates_none` (which prove writes succeed when the switch **is** enabled) continue to pass unchanged, now with `google_provider_writes_enabled=True` added to their shared settings baseline — proving the flag genuinely gates behaviour in both directions, not just the disabled one.

## Negative controls run during this phase's live rehearsal (§10)

A synthetic attempted Gmail draft and a synthetic attempted Calendar insertion are run against the fake-provider rehearsal harness with a real (fake) connected account and `google_provider_writes_enabled=False`, proving the same block holds end-to-end through the full app, not merely in an isolated unit test — see [fake-rehearsal-results.md](fake-rehearsal-results.md).
