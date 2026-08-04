# Stage 11A Phase 4D — Live Transport Guard Results

**Status:** PASS — exact allowlist implemented and verified · **Date:** 2026-08-04

## Design

`apps/api/scripts/stage11a_phase4d_live_readonly_guard.py::LiveReadOnlyGuardTransport` — an `httpx.AsyncBaseTransport` wrapper installed around the real Google transport during the live smoke run only (never in `create_app()`, never in production wiring). It allows exactly six `(method, host, path)` combinations and refuses everything else before the wrapped transport is ever invoked:

| Operation | Method | Host | Path | Live budget |
|---|---|---|---|---:|
| Token exchange | `POST` | `oauth2.googleapis.com` | `/token` | 1 |
| Token revocation | `POST` | `oauth2.googleapis.com` | `/revoke` | 1 |
| Gmail profile | `GET` | `gmail.googleapis.com` | `/gmail/v1/users/me/profile` | 1 |
| Gmail message list | `GET` | `gmail.googleapis.com` | `/gmail/v1/users/me/messages` | 1 |
| Calendar primary metadata | `GET` | `www.googleapis.com` | `/calendar/v3/calendars/primary` | 1 |
| Calendar event list | `GET` | `www.googleapis.com` | `/calendar/v3/calendars/primary/events` | 1 |

This is a default-deny **allowlist**, not a blocklist of dangerous operations — any endpoint not named above is refused, including ones that do not exist yet. The OAuth token and revocation endpoints are explicitly permitted as protocol/cleanup operations, per the governing instruction's own framing — they are not Gmail or Calendar content writes.

## Requirements checklist

| Requirement | How satisfied |
|---|---|
| Exact method-and-path allowlist | `ALLOWED_OPERATIONS: frozenset[tuple[str,str,str]]`, checked by exact tuple membership |
| Immune to provider-origin environment overrides | The guard reads only `request.method`/`request.url.host`/`request.url.path` — never a `Settings` value or environment variable; `test_no_environment_variable_can_select_an_unapproved_operation` sets `GOOGLE_API_ORIGIN_OVERRIDE` and confirms it has no effect |
| Counts attempted calls | Per-operation counters, exposed only via `content_free_metrics()` |
| Emits content-free metrics only | `content_free_metrics()` returns `{"METHOD /path": count}` — no host, no query string, no header, no response body |
| Never logs query secrets or headers | Violation/budget error messages include only method, host, and path — confirmed by direct inspection of both raised-exception messages |
| Has regression tests | 24 tests, `test_stage11a_phase4d_live_readonly_guard.py` |
| Fails closed | Every branch other than an exact allowlist hit + budget check raises before calling the wrapped transport |

## Explicitly proven blocked (regression tests, one row per requirement in the governing instruction §7)

Gmail `POST`/`PUT`/`PATCH`/`DELETE` (drafts endpoint used as the representative write path) · Calendar `POST`/`PUT`/`PATCH`/`DELETE` on events · an unapproved Google endpoint (an arbitrary unnamed host) · message-content retrieval (`/messages/{id}`) · attachment retrieval (`/messages/{id}/attachments/{id}`) · Gmail history traversal (`/history`) · Calendar watch creation (`/events/watch`) · a batch endpoint (`/batch/gmail/v1`) · an arbitrary/unapproved host · a redirect to an unapproved host (refused on the followed hop, not the first) · any request exceeding its call budget (every one of the six approved operations is proven to allow exactly its budgeted count and then refuse the next identical request).

## Relationship to the Phase 4B no-live-network guard

`lifeflow_api.testing.no_live_network` (Phase 4B) and this guard are deliberately separate and never combined: the Phase 4B guard's entire purpose is that **no** non-loopback host may ever be reached (for fake-provider rehearsals, where reaching Google at all would be a defect). This guard's purpose is the opposite: it exists only for the one authorised live session, where reaching Google is the point, narrowed to an exact six-operation allowlist. Neither guard is weakened by the other's existence — the fake-provider rehearsals in [fake-rehearsal-results.md](fake-rehearsal-results.md) continue to use the Phase 4B guard, never this one.
