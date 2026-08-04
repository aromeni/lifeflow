# Stage 11A Phase 4D — First OAuth Connection and Read-Only Provider Validation

**Status:** In execution · **Date:** 2026-08-04

Governed by [engineering-acceptance-contract.md](engineering-acceptance-contract.md). Follows Phase 4C (`PASS — READY FOR FIRST OAUTH CONNECTION AUTHORISATION`, merged to `main` at `52a0bd7c2327bbd9fa97608c0d448b33c04cac63`) and the project owner's explicit authorisation: **AUTHORISE FIRST OAUTH CONNECTION OF ACCOUNT A — READ-ONLY SMOKE TESTS ONLY**.

## Objective

Validate one real OAuth connection of disposable `ACCOUNT_A`, prove secure v2 credential handling, perform only bounded read-only Gmail and Calendar smoke requests, and return the system to a disconnected zero-credential state.

## Authorised boundary

- Temporarily enabling OAuth initiation locally (never committed enabled).
- Using the connector-consent flow for `ACCOUNT_A` only.
- Displaying and reviewing Google's consent screen.
- Granting exactly the four previously approved scopes.
- Completing one authorisation-code callback.
- Storing the returned credential using the active v2 encrypted envelope.
- Verifying owner/account/provider/field binding.
- A tightly budgeted set of read-only Gmail and Calendar requests (see [provider-call-budget.md](../evaluation/stage-11/owner-validation/phase-4d/provider-call-budget.md)).
- Security and leakage inspection.
- Revoking access and disconnecting after validation.
- Returning the local environment to zero stored credentials.

## Prohibited boundary

Using Google OIDC sign-in; connecting `ACCOUNT_B`; connecting a personal or business account; requesting any additional scope; importing or synchronising mailbox or Calendar content; persisting Gmail messages or Calendar events as `SourceItem`s; creating a Gmail draft; sending Gmail; inserting a Calendar event; updating or deleting a Calendar event; enabling automatic synchronisation; running provider workers or schedulers; deliberately refreshing the access token; retrying an uncertain provider operation; starting the soak period; participant activity; Stage 12 work; creating a Stage 11 or Stage 11A tag. **The authorised live-provider write budget is zero.**

OAuth token exchange and security revocation are protocol and cleanup operations, not Gmail or Calendar product writes, and are permitted precisely because they are not writes to Gmail or Calendar content.

## Connector-consent route

`GET /connected-accounts/google/connect` → Google consent → `GET /connected-accounts/google/callback`. Never `GET /auth/google/login` (OIDC sign-in — prohibited for this phase). Scope set: `google_scopes.CONNECTOR_SCOPE_STRING` (four scopes, unchanged from Phase 4B/4C). Redirect URI: the single approved localhost connector callback configured in Phase 4C.

## Owner-operated checkpoints

Exactly four points in this phase require the project owner to personally act, each gated behind a completed prior step and each requesting only a fixed, content-free confirmation phrase (never a secret, value, or screenshot):

1. **Prepare the browser** (§12 of the governing instruction) — `OWNER READY — ACCOUNT A ONLY — NO PERSONAL GOOGLE SESSION`.
2. **Consent-screen review** (§14) — `CONSENT SCREEN VERIFIED — ACCOUNT A — APPROVED FOUR-SCOPE SET`, or `EMERGENCY STOP — CONSENT SCREEN MISMATCH`.
3. **Callback completion** (§15) — `OAUTH CALLBACK COMPLETED — RETURNED TO LIFEFLOW`.
4. **Google-side revocation confirmation**, only if programmatic revocation is uncertain (§20 Step B) — `GOOGLE ACCESS REVOCATION CONFIRMED OUTSIDE GIT`.

## Pre-live safeguards

Five independent, testable safeguards must all be green before the first owner checkpoint is requested:

1. **Provider-write kill switch** (`GOOGLE_PROVIDER_WRITES_ENABLED`, default `false`) — [provider-write-block-results.md](../evaluation/stage-11/owner-validation/phase-4d/provider-write-block-results.md).
2. **Import/background-activity block** — no automatic sync, worker, or scheduler activity on connect — [import-and-background-block-results.md](../evaluation/stage-11/owner-validation/phase-4d/import-and-background-block-results.md).
3. **Live read-only transport guard** — exact method+path allowlist — [live-transport-guard-results.md](../evaluation/stage-11/owner-validation/phase-4d/live-transport-guard-results.md).
4. **Provider-call budget** — counted, non-zero-exit-on-exceedance — [provider-call-budget.md](../evaluation/stage-11/owner-validation/phase-4d/provider-call-budget.md).
5. **Three-or-more fake-provider rehearsals**, each injecting the required failure scenarios — [fake-rehearsal-results.md](../evaluation/stage-11/owner-validation/phase-4d/fake-rehearsal-results.md).

## Provider-call budget

See [provider-call-budget.md](../evaluation/stage-11/owner-validation/phase-4d/provider-call-budget.md) for the full table. Summary: 1 authorisation initiation, 1 callback, 1 code exchange, 0 deliberate refreshes, 1 revocation attempt; Gmail `users.getProfile` ≤1, `users.messages.list` ≤1 (≤5 messages), zero message/attachment/history reads, zero writes; Calendar `calendars.get` (primary) ≤1, `events.list` (primary) ≤1 (≤5 events), zero writes; zero automatic retries.

## Credential-storage checks

Before any provider read: exactly one relevant connected-account credential set; owner/provider/account-identity match; encrypted access credential; encrypted refresh credential (if issued); envelope version v2; active key ID recorded; AAD binds owner+account+provider+field; no v1 envelope; no unknown key version; no plaintext token in any column, Redis key, log line, metric label, Audit History entry, URL, or browser storage; no provider `SourceItem`; no background sync job.

## Read-only smoke operations

Exactly, in order, once each: Gmail `users.getProfile` → Gmail `users.messages.list` (`maxResults<=5`) → Calendar `calendars.get(calendarId="primary")` → Calendar `events.list(calendarId="primary", maxResults<=5, bounded window)`. No page traversal, no `pageToken`/`syncToken`, no message/event body or metadata beyond what these four calls return, no persistence of any response.

## Leakage checks

Sentinel/presence-only inspection (never raw dumps) of: credential schema/columns, Redis key names, structured logs, metrics labels, Audit History, browser local/session storage, the callback landing URL, `SourceItem`s, action proposals, pending executions, and temporary files.

## Emergency stops

See [emergency-stop-results.md](../evaluation/stage-11/owner-validation/phase-4d/emergency-stop-results.md) for the full 25-condition table (wrong account, unexpected scope, callback replay, v1/unknown-key credential, plaintext exposure, automatic import, any write attempt, budget exceedance, failed revocation/disconnect, residual credential, real/participant information, unresolved P0/P1). Every condition maps to: immediate action, provider actions that must stop, local shutdown, evidence to retain/prohibit, revocation path, disconnect path, severity, and restart criteria.

## Revocation, disconnect and cleanup

Four-step mandatory sequence after any read-only validation (success or stop): (A) restore `GOOGLE_OAUTH_INITIATION_ENABLED=false` locally; (B) revoke Google OAuth access (max 1 programmatic attempt; owner-confirmed manually only if uncertain); (C) LifeFlow disconnect (clears credential ciphertext and key-version fields); (D) final residue check (all credential/binding/SourceItem/write/Redis/browser counts back to zero, `clear_to_connect=true`). This sequence runs regardless of whether the smoke reads succeed — see [disconnect-and-residue-results.md](../evaluation/stage-11/owner-validation/phase-4d/disconnect-and-residue-results.md).

## Evidence rules

Content-free throughout. Never committed: account addresses, project IDs, client ID/secret, state/nonce/PKCE verifier, authorisation codes, access/refresh tokens, provider item IDs, message/event content, raw provider responses, callback URLs, browser history, screenshots, HAR files, raw logs, database/Redis dumps, absolute local paths.

## Severity rules

P0–P3 framework per the governing instruction §23, applied identically to [defect-register.md](../evaluation/stage-11/owner-validation/phase-4d/defect-register.md). P0 blocks PASS outright (wrong binding, plaintext exposure, cross-owner use, any provider write, automatic uncertain retry, accepted replay, v1/unknown-key credential accepted, credential usable after disconnect). P1 requires a fix and, if a live consent must be repeated, a new owner authorisation. P2 is fixed where practical or given an explicit closure condition. P3 is cosmetic. The acceptance bar is never lowered to preserve PASS.

## Exit decision

Exactly one of: **PASS — FIRST OAUTH CONNECTION AND READ-ONLY SMOKE VALIDATED**, **CONDITIONAL PASS** (non-safety P2 only), or **FAIL — REAL PROVIDER CONNECTION REMAINS BLOCKED**. See [phase-4d-decision.md](../evaluation/stage-11/owner-validation/phase-4d/phase-4d-decision.md) for the full criteria, mirrored from the governing instruction §25. A PASS does not authorise reconnection, content import, drafting, calendar insertion, or the soak period — only the specific next owner decision recorded in that document.
