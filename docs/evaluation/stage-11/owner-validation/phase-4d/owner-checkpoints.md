# Stage 11A Phase 4D — Owner Checkpoints

Four checkpoints in this phase required genuine, real-time action by the
project owner in their own browser. None were simulated, and none could be
— each is recorded below with the exact confirmation phrase received, the
evidence the owner supplied, and the timestamp (local session time; the
database-recorded UTC timestamps for the two identity-bearing events appear
in `oauth-connection-results.md` and `revocation-results.md`).

## §12 — Browser preparation

- Owner ran `./scripts/demo.sh`, used "Try demo," and supplied a screenshot
  of `localhost:3000/connections` showing "Connected accounts: Not
  connected" / "Granted access: No access granted," with only synthetic
  demo data populated.
- Confirmation received: `OWNER READY — ACCOUNT A ONLY — NO PERSONAL GOOGLE SESSION`
- No account address, credential, or other sensitive value was requested or
  supplied for this checkpoint.

## §14 — Consent-screen review

- Owner was walked through the exact items to check before clicking
  through Google's consent screen: Account A selected, LifeFlow testing
  app name, the expected "unverified app" Testing-status interstitial, and
  exactly the four approved Gmail/Calendar permissions with nothing extra.
- Confirmation received: `CONSENT SCREEN VERIFIED — ACCOUNT A — APPROVED FOUR-SCOPE SET`

## §15 — Callback completion

- Owner confirmed the browser was redirected back to LifeFlow's Connections
  page automatically after consent, with no error banner.
- Confirmation received: `OAUTH CALLBACK COMPLETED — RETURNED TO LIFEFLOW`
- Owner additionally supplied a screenshot of the resulting Connections
  page (`?connected=google`), independently corroborating: status
  **active**, exactly the four expected granted-access lines, and
  **"Evidence freshness: Never synced — no evidence has been imported
  yet."** This screenshot was the basis for the automatic-import boundary
  check in `credential-storage-results.md`.

## §20 — Revocation and disconnect (conditional checkpoint)

- Owner clicked "Disconnect Google" on the Connections page, which calls
  the real Google token-revocation endpoint before clearing the local
  credential (see `revocation-results.md`), and was invited to
  independently verify on `myaccount.google.com/permissions` that LifeFlow
  no longer appears under Account A's third-party access.
- Confirmation received: `DISCONNECTED — ACCOUNT A — GOOGLE ACCESS REVOKED CONFIRMED`

## What was never requested

Consistent with the governing instruction, at no point was the owner asked
to paste the Google account address, password, recovery details, MFA/backup
code, client ID/secret, state value, authorisation code, callback URL,
access/refresh token, cookie, or a screenshot containing any of those
values. The one email address the owner volunteered unprompted in chat
(before the live sequence began) was explicitly not confirmed, repeated, or
recorded anywhere in this evidence pack, in logs, or in any commit.
