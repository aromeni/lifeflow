# Stage 11A Phase 4D — Import and Background-Activity Block Results

**Status:** PASS — no automatic import path exists; confirmed by inspection and a new regression test · **Date:** 2026-08-04

## What normally happens after a Google account connects

Direct inspection of `connected_accounts.py::google_connector_callback` (the only code path a successful OAuth callback runs): it exchanges the code, stores the encrypted credential via `ConnectedAccountService.store_tokens`, and redirects to `/connections?connected=google`. It does not call `GoogleSyncService`, does not enqueue a job, and does not create a `SourceItem`.

The frontend's `/connections` page (`apps/web/src/app/connections/page.tsx`) fetches `GET /privacy/summary` exactly once, on mount — a read of LifeFlow's own database, never a Google call — per its own design comment: *"The only fetch happens here, once, in response to the component mounting — never on a timer and never as a side effect of a provider sync, so opening or refreshing this page never causes Google traffic."* Sync is exclusively triggered by the operator clicking "Sync now" (`syncGoogle()`, a `POST /connected-accounts/google/sync` call with no automatic trigger anywhere in the component).

Worker/scheduler inspection: `grep` for `google_sync`, `GoogleSyncService`, and `build_google_sync_service` across `worker_app.py`, `scheduled_briefs.py`, and `scheduled_brief_status.py` returns zero matches — no scheduled or background job ever touches Google sync. The scheduled-brief worker operates only on already-imported `SourceItem` rows; it has no code path that could pull fresh Google content.

## Conclusion

**No new fail-closed "Phase 4D validation mode" was needed.** The existing architecture already has no automatic-import path to block — connecting an account has never done anything beyond storing a credential and redirecting. This is confirmed, not assumed: a new regression test closes the coverage gap that let this go unverified.

## Regression test

`test_connecting_google_never_triggers_automatic_import` (`test_google_route_integration.py`): connects a real (mock-transport) Google account for a fresh user with zero pre-existing data, then asserts the `source_items` count for that user is exactly `0` immediately after the callback completes. The mock transport also raises `AssertionError` on any request beyond the token exchange, so any future accidental sync-on-connect would fail this test at the transport level even before the database assertion runs.

## Live-run operational requirements (§6)

During the live checkpoint (§13 onward):

- API process: running (required to serve the connect/callback routes).
- Frontend: running (required for the owner to use the real UI, per the governing instruction's explicit prohibition on a handcrafted authorisation URL).
- PostgreSQL and Redis: running (required for the API to function at all).
- Provider workers (`arq` worker process): **stopped** — not required for any part of this phase's read-only smoke sequence, which runs entirely through the API's HTTP routes and a dedicated operator script, never through a queued job.
- Scheduler: **stopped** — same reasoning.
- `E2E_TEST_CONTROLS_ENABLED`: **false** (production-guard default; also blocks `GOOGLE_API_ORIGIN_OVERRIDE` and the demo clock).
- `GOOGLE_API_ORIGIN_OVERRIDE`: **unset** (fake-provider override must be inert; this phase talks to the real Google hosts).
- Demo-clock override: **false** (irrelevant to this phase but confirmed inert regardless, per the same shared test-control gate).

These are verified as part of [pre-live-gate-results.md](pre-live-gate-results.md) immediately before the first owner checkpoint.
