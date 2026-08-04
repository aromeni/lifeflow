# Stage 11A Phase 4D — OAuth Connection Results

## Sequence

1. `.env`'s `GOOGLE_OAUTH_INITIATION_ENABLED` was flipped `false` → `true`
   as the deliberate, temporary, owner-authorised step for this connection
   window (never committed — the file remains git-ignored throughout).
2. `preconnection_readiness_check.py` was re-run and reported 15/16 PASS,
   with the single expected `[FAIL] oauth_initiation_blocked: enabled` —
   the correct signal that initiation is now deliberately live-armed, not
   a defect (that specific check exists to confirm the *pre-connection*
   blocked state).
3. The owner restarted `./scripts/demo.sh` so the running API picked up
   the new setting, then clicked the real "Connect Google" button on the
   Connections page (never a hand-constructed URL).
4. The owner completed Google's real consent screen for disposable Account
   A and was redirected back to LifeFlow automatically.

## Result

Exactly one connector-consent flow was initiated and completed, once. The
resulting `connected_accounts` row:

| Field | Value |
|---|---|
| `provider` | `google` |
| `status` | `active` |
| `granted_scopes` | `gmail.readonly`, `gmail.compose`, `calendar.readonly`, `calendar.events` — exactly the four approved scopes, nothing extra |
| `authorisation_revision` | `1` (first authorisation; no prior history) |
| `last_sync_at` | `NULL` — never synced |
| `access_token_key_id` / `refresh_token_key_id` | `dev-1` (the active key) |

A single `account.connected` audit event was recorded
(`2026-08-04 08:27:04 UTC`), with `safe_metadata_json` limited to
`{"provider": "google", "scope_count": 4, "authorisation_revision": 1}` —
no email address, token, or scope URL.

## Boundary checks

- Exactly one credential-bearing Google `connected_accounts` row existed
  system-wide at any point during the connection window (query filters on
  `encrypted_access_token IS NOT NULL`, not merely `provider = 'google'`,
  since the local dev database separately carries 158 label-only synthetic
  fixture rows with no real credential).
- No Google OIDC sign-in occurred; the connector-consent flow
  (`/connected-accounts/google/connect`) was the only flow used.
- No second account, and no personal/business account, was connected.
- The Connections page's own "Evidence freshness" panel independently
  corroborated "Never synced" immediately after connection, before any
  smoke-test call was made.
