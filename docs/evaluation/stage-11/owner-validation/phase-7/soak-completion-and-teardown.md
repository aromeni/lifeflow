# Stage 11A Phase 7 — Soak Completion and Teardown

**Date:** 2026-08-16

## Duration

T0 = `2026-08-05T22:46:02.511575+00:00` (see
[day-00-connection-evidence.md](day-00-connection-evidence.md)). Completion
check-in at `2026-08-16T16:41:57+00:00` — **257.9 hours elapsed (10.75
days)**, comfortably past the required 240-hour minimum. See
[soak-daily-log.md](soak-daily-log.md) for the full day-by-day record,
including the one full gap-recovery cycle (Docker/DB/Redis outages, most
likely host sleep/reboot, self-recovered every time with no data loss and
no flag drift) and the 7-day Testing-status boundary event with its
controlled reconnection (Day 7).

## Imported-data deletion

One `SourceItem` remained at completion (see `soak-daily-log.md`'s final
entry — an old, pre-T0 fixture email that surfaced via a genuinely
incremental, non-full-resync sync on the last day, for reasons explained
there). Deleted via the product's own audited preview → typed-confirmation
→ worker-processed flow (`POST /privacy/imported-data/{account_id}/preview`
→ `POST /privacy/deletion-operations/{operation_id}/confirm`, phrase
`DELETE IMPORTED DATA`), driven directly against the API with the
`arq` worker started to process the resulting job — the same code path the
Connections page UI would use. Preview and final `deleted_counts_json` both
showed exactly `{"source_items": 1}`. Confirmed directly against the
database: `0` `source_items` remain for this account.

## Access revocation and disconnection

`POST /connected-accounts/google/disconnect` returned `204`. Confirmed
directly against the database:

- `connected_accounts.status`: `disconnected`.
- `access_token_key_id`, `refresh_token_key_id`: both `NULL`.
- `encrypted_access_token`, `encrypted_refresh_token`: both `NULL`.

**Revocation classification: `REVOCATION ATTEMPT RECORDED — PROVIDER RESULT
UNCERTAIN`.** The `account.disconnected` audit event records
`"revocation_confirmed": false` — unlike Phase 6B, Google's revoke endpoint
did **not** return an HTTP 200 for this attempt. Per `accounts.py`'s own
documented contract (`oauth.py::revoke_token`), `false` covers both an
explicit non-200 response and a network failure indistinguishably, and no
application-level warning or error was logged for the attempt (the codebase
deliberately does not log this path beyond the truthful audit-metadata
boolean, so as not to fabricate false confidence). Local disconnect
proceeded regardless, per the product's own D20 guarantee that Google being
unreachable must never block a user's local disconnect — and it worked
exactly as designed: local credentials are fully and verifiably cleared
either way. **This does not block soak completion**, but it does mean the
soak's own record cannot claim confirmed Google-side revocation this time.
**Recommended action for the owner:** independently check
`myaccount.google.com/permissions` (or the equivalent connected-apps page)
to confirm the LifeFlow OAuth client no longer has access; if it is still
listed, revoke it there directly. There is no way to retry the revocation
call through the product now that the local refresh token has already been
cleared by the disconnect that already ran.

## GM-12 — not observed this soak

Discussed directly with the project owner before this check-in (no
objection to leaving it unobserved rather than forcing it). Neither Gmail's
`historyId` cursor nor Calendar's sync token ever expired into the
documented full-resync fallback during the 240+ hours of daily/near-daily
incremental syncs, so GM-12 — whose local copy was deleted by Phase 6B's
cleanup before this soak began — never became visible to a fresh import.
**Not a defect and not a soak failure**: every alternative to observe it
this soak (an out-of-band database write clearing `sync_cursors`, or a full
account deletion) would have been materially worse than leaving it
undone — see the recommendation recorded in-session and reflected in
`phase-7-decision.md`. **Recommended follow-up** (separate, small, future
task, not a reason to extend or repeat this soak): send a *fresh* stale-
follow-up trigger message and let it age past 5 days under a normal sync
that was never preceded by a deletion of that same item — the same pattern
already validated for the Calendar-write path in Phase 6B.

## Zero-residue verification (independently re-checked against the database, post-teardown)

| Check | Result |
|---|---|
| `connected_accounts.status` (real account) | `disconnected` |
| Access/refresh token ciphertext | both `NULL` |
| Access/refresh token key IDs | both `NULL` |
| `SourceItem`s for this account | `0` |
| `action_executions` with `started_at` after T0 | `0` |
| Pending/uncertain executions | `0` |
| `users.google_subject` bindings | `0` |
| Other real-credentialed `google` rows (Account B) | `0` — never connected |
| Redis keys | only routine, TTL-bound `arq` job-queue bookkeeping (job names, an operation-result record) — no token or secret material |
| Readiness command | **19/19 PASS**, `READY` |
| Credential connection gate | `unversioned=0 legacy_known=0 legacy_unknown=0` |
| `GOOGLE_OIDC_SIGNIN_ENABLED` | `false` |
| `GOOGLE_CONNECTOR_OAUTH_ENABLED` | `false` |
| `GOOGLE_PROVIDER_WRITES_ENABLED` | `false` (never toggled `true` at any point this entire phase) |
| Stray manual servers (`uvicorn`/`next dev`/`arq`) | none — all stopped |
| Docker | only `db`/`redis` containers running |
| Duplicate `SourceItem`/`Signal`/proposal rows, across every check-in | `0`, every single day |
| New `action_executions` across the entire soak | `0` |
