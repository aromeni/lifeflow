# Dry-Run Results — 18-Step Connection Rehearsal

**Status:** 3/3 cycles pass · **Date:** 2026-08-01

Companion: `apps/api/scripts/stage11a_phase4b_connection_rehearsal.py` · [first-connection-runbook.md](first-connection-runbook.md)

## Method

`stage11a_phase4b_connection_rehearsal.py` runs the full simulated lifecycle from the governing task §21 against a dedicated, isolated local PostgreSQL database created and dropped for each cycle, using the app's real HTTP routes (via in-process ASGI transport, exactly like the existing integration test suite) and `httpx.MockTransport` in place of every Google-facing HTTP call. **No Google account or Google Cloud project was ever created, and no authenticated or successful Google API interaction has ever occurred.** One unintended, unauthenticated outbound network attempt did occur — in an early, uncommitted draft of this script, before this rehearsal was ever reported as passing. It is fully documented, with its exact technical boundary, in "Exact-boundary classification of the accidental outbound attempt" below; do not read the sentence above as claiming that attempt never happened.

## Steps simulated per cycle

1–4: configuration preconditions (test-control flags inert) · 5: connection gate before any connection · 6: account identity (dev-login) · 7: owner authorisation (simulated — not fabricated) · 8: consent-screen scope review · 9: simulated callback · 10: v2 credential storage verification · 11: sentinel scan (structural — no token ever printed) · 12: read smoke test (`sync`) · 13: emergency-stop check (scope-mismatch detection) · 14: revocation · 15: disconnect verification · 16: credential-residue re-check · 17: imported-data / full-account cleanup · 18: final clean-state verification.

## Results

| Cycle | Result | Time |
|---|---|---|
| 1 | PASS | — |
| 2 | PASS | — |
| 3 | PASS | — |

All 3 cycles: **3/3 passed in 3.8s** (final run, after the two script defects below were fixed).

## Defects found and fixed — in the rehearsal script itself, not the product

The first draft of this rehearsal script had two real bugs, both caught by running it rather than assuming it would work:

1. **A real network call to Google's live API was attempted.** The script initially replaced only `app.state.google_oauth_client` with a mock transport — matching the OAuth token-exchange mock pattern from `test_google_auth_and_connections_api.py` — but not `app.state.gmail_client`/`app.state.calendar_client`, which `create_app` otherwise wires to real `httpx.AsyncClient` instances pointed at the real Gmail/Calendar hosts. The step-12 read smoke test consequently sent a real HTTP request to Google's Gmail API with a fake bearer token and received a genuine `401` back — a real network call this task's governing instruction explicitly prohibits, made by tooling, not by any product code path. **Fixed**: the script now also assigns `app.state.gmail_client`/`app.state.calendar_client` to mock-transport-backed clients, matching the exact pattern `test_google_route_integration.py`'s `_app_client` already established for testing real-provider sync. **Caught before this rehearsal was ever reported as passing** — no commit or evidence claimed success before this was found and fixed.
2. **Incorrect assumption about full-account-deletion behaviour.** The script's step-18 assertion originally expected the `User` row to be physically removed from the database. Reading `account_deletion.py`'s `_PHASE_FINALISE` showed this is incorrect by design: full deletion sets `user.account_state = UserAccountState.deleted` (an anonymised tombstone), it does not delete the row — consistent with the retention/audit design already documented in Stage 9 and referenced in this phase's own [test-account-cleanup-plan.md](test-account-cleanup-plan.md) ("retain only permitted content-free tombstones"). **Fixed**: the assertion now checks `account_state == UserAccountState.deleted` and that no `ConnectedAccount` rows remain, matching the actual, correct, already-tested product behaviour (Phase 4A's `test_full_account_deletion_removes_key_id_columns_with_the_row` asserts the same `ConnectedAccount`-removal fact, not `User`-row removal).

Neither defect was in product code — both were in this new rehearsal script, found and fixed before it was ever reported as passing, matching the "evidence over theatre" standard the rest of this delivery has followed.

## Exact-boundary classification of the accidental outbound attempt

This section corrects an earlier internal inconsistency: this document's own defect entry above always described a real network attempt, but summary text elsewhere in the Phase 4B evidence pack and cross-cutting docs said "no real Google API call was made" without qualification. Both statements needed to be true at once, and they are — but only once "call" is defined precisely. This section gives that precise definition, derived from the code path the first draft executed (`GmailDraftClient.list_messages`, `src/lifeflow_api/google/gmail_client.py:156-176`, called from the step-12 read-smoke-test) and the `401` observed at the time.

| Question | Answer |
|---|---|
| Hostname / exact URL | `gmail.googleapis.com` — `GET https://gmail.googleapis.com/gmail/v1/users/me/messages` |
| HTTP operation | `GET` (read-only list; not a write) |
| TCP/TLS connection established | Yes — a completed TLS handshake and application-layer HTTP exchange is required to receive any HTTP status code back, including `401` |
| HTTP request reached the endpoint | Yes |
| Response received | Yes — HTTP `401 Unauthorized` |
| Client ID or client secret present in the request | No — this endpoint takes a bearer token, not client credentials; no client ID/secret was submitted in this request |
| Authorisation code present | No |
| Access token / refresh token present | An `Authorization: Bearer rehearsal-access-token` header was sent — a fabricated placeholder string local to this rehearsal, never a genuine Google-issued token |
| Session cookie present | No — this was a server-to-server call, not browser-mediated |
| Real account identifier or user data present | No — the request's only parameters were a numeric date-range query (`q=after:<epoch> before:<epoch>`) computed from the local server clock; no real email address, message content, or search term was sent |
| Was the attempt authenticated | No — Google rejected the fabricated bearer token, which is exactly what the `401` means |
| Could any provider-side object or state have been created | No — `list_messages` is a read-only `GET`; the code path attempted has no write capability, and no draft/event-creation call was ever made or attempted |
| Code change that removed the behaviour | The (never-committed) fix now visible at `apps/api/scripts/stage11a_phase4b_connection_rehearsal.py:163-166`: `app.state.gmail_client`/`app.state.calendar_client` are also assigned mock-transport-backed clients, and `_full_transport()` (lines 96-125) answers `/messages`, `/profile`, and `/events`-shaped requests without ever leaving the process |

**Classification: UNINTENDED UNAUTHENTICATED OUTBOUND ATTEMPT — NO CREDENTIAL OR USER DATA TRANSMITTED; NO SUCCESSFUL GOOGLE API INTERACTION.**

This attempt was never committed, never part of any passing rehearsal run, and never reported as evidence before this correction. It is closed as a process/test-tooling finding (see [defect-register.md](defect-register.md)), and is now additionally prevented at the transport layer by a durable no-live-network guard (below), not merely by the specific fix that closed this one instance.

## No-live-network guard

`apps/api/src/lifeflow_api/testing/no_live_network.py` (new) provides `block_live_google_network()`, an `httpx.AsyncBaseTransport` wrapper: any outbound request whose host is not on the loopback allowlist (`localhost`, `127.0.0.1`) raises `LiveNetworkAttemptError` before the wrapped transport is ever invoked — a default-deny allowlist, not a blocklist of specific Google hostnames, so it covers every current and future non-loopback Google host, not just the five named in the governing instruction.

It is deliberately **not** wrapped around the rehearsal's own `_full_transport()` mock — that mock's whole job is to answer requests addressed to the real Google hostnames the application code genuinely constructs (`gmail.googleapis.com`, `oauth2.googleapis.com`, `www.googleapis.com`), and `httpx.MockTransport` already guarantees zero real socket I/O for any host, so wrapping it there would only block the correctly-mocked flow (this was tried and immediately caught by the rehearsal itself failing, before being corrected). Instead, `stage11a_phase4b_connection_rehearsal.py` installs it as a **safety net** on `app.state.google_http_client` — the single real, network-capable client `create_app()` wires all three Google-facing clients to — replacing its transport with the guard wrapping a real `httpx.AsyncHTTPTransport()` *before* the script's explicit per-cycle mock overrides run. This exactly closes the historical gap: if a future edit forgets to override one of the three clients with the mock (the precise mistake that caused the original incident), that client now falls back to the guarded client and is refused before any socket opens, instead of silently falling back to a real, unguarded one. `preconnection_readiness_check.py` needs no such guard — it never constructs a Google-facing HTTP client at all; it only inspects local configuration, the database, and Redis.

Regression coverage (`test_stage11a_phase4b_no_live_network_guard.py`, 12 tests) proves: each of `accounts.google.com`, `oauth2.googleapis.com`, `gmail.googleapis.com`, `www.googleapis.com`, and `calendar.googleapis.com` is blocked; an arbitrary non-loopback host not on that named list is also blocked; loopback hosts still reach the wrapped transport; no environment variable can select a live origin (the guard consults only the outgoing request's resolved host, never any setting); a redirect response pointing at a non-loopback host is refused on the followed hop; and — reproducing the exact historical shape — a `GmailDraftClient` built directly on the safety-net client, standing in for a forgotten mock override, is refused before any request reaches `gmail.googleapis.com`.

## What this proves and does not prove

This proves the full connection→smoke-test→disconnect→revoke→cleanup lifecycle behaves correctly against the *fake* provider, end to end, through the app's real routes. It does not prove anything about Google's actual behaviour (real consent-screen rendering, real token issuance, real API responses) — that can only be proven by the future, separately-authorised real connection described in [first-connection-runbook.md](first-connection-runbook.md).
