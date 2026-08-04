# Stage 11A Phase 4D — Revocation Results

## Action taken

The owner clicked "Disconnect Google" on the Connections page, which calls
`POST /connected-accounts/google/disconnect`. This route passes the real
`google_oauth_client` (not `None` — the connector integration was active)
into `ConnectedAccountService.disconnect(GOOGLE_PROVIDER,
oauth_client=oauth_client)`, meaning the button performs the real Google
revoke call and the local credential clear as a single action.

`GoogleOAuthClient.revoke_token()` posts to
`https://oauth2.googleapis.com/revoke` and returns `True` only on an
objective HTTP 200 (`False` for any non-200 or network error; never
raises, preserving its best-effort contract). `disconnect()` records
whatever that call actually returned, truthfully, in the audit event —
not an assumed or optimistic value.

## Result

```
account.disconnected audit event:
  safe_metadata_json = {"provider": "google", "revocation_confirmed": true}
  timestamp           = 2026-08-04 08:41:11 UTC
```

`revocation_confirmed: true` reflects a real HTTP 200 from Google's revoke
endpoint for this specific refresh token — not a default or best-effort
guess. The owner independently corroborated this by checking
`myaccount.google.com/permissions` under Account A and confirming LifeFlow
no longer appears, before sending the confirmation phrase (§20,
`owner-checkpoints.md`).

## Local state after revocation

```
connected_accounts.status                = disconnected
connected_accounts.encrypted_access_token  = NULL
connected_accounts.encrypted_refresh_token = NULL
connected_accounts.access_token_key_id     = NULL
connected_accounts.refresh_token_key_id    = NULL
```

See `disconnect-and-residue-results.md` for the full zero-state
confirmation across the rest of the database.
