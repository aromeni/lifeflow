# Stage 11A Phase 4D — Credential Storage Results

Verified against the real, live-created `connected_accounts` row
(`id = b11b4d3a-c36b-486b-b9e9-eafa42fb5c9c`) before any provider read.

## Envelope format and active key

```
access_envelope_prefix  = v2:dev-1:
refresh_envelope_prefix = v2:dev-1:
access_is_v2_active_key  = true
refresh_is_v2_active_key = true
```

Both the access and refresh token fields are `v2` (AAD-bound) envelopes,
both on the current active key (`dev-1`) — not a legacy key, and not the
no-AAD `v1` format. `credential_connection_gate()` was re-run immediately
before the smoke sequence and reported `unversioned=0 legacy_known=0
legacy_unknown=0` — the whole database, not just this row, is clear of any
unversioned or legacy-keyed credential.

## AAD binding

`accounts.py::_field_context` derives the AAD context for every
encrypt/decrypt call as `credential_context(connected_account_id, user_id,
provider, field)` — bound to the specific row, not just the record type.
This is the real call site the connector-consent callback used to store
this credential (not a re-derived or assumed value): a ciphertext copied
into a different row, or the sibling field of the same row, fails
authentication rather than quietly decrypting.

## No plaintext anywhere

- The `connected_accounts` table holds only the two envelope strings above
  — no plaintext column exists on this table.
- The `account.connected` audit event's `safe_metadata_json` is limited to
  `provider`, `scope_count`, and `authorisation_revision` (see
  `oauth-connection-results.md`) — no token material.
- `first_google_readonly_smoke.py` decrypts the access token directly via
  `TokenKeyRing.decrypt()`, holds it only in a local variable for the
  duration of the four HTTP calls, and never logs, prints, or persists it.

## Zero content imported

```sql
SELECT count(*) FROM source_items
WHERE source_account_id = 'b11b4d3a-c36b-486b-b9e9-eafa42fb5c9c';
-- 0
```

Zero `SourceItem` rows are linked to the new connection at any point before
the read-only smoke sequence — connecting the account did not, by itself,
import or persist anything, consistent with `import-and-background-block-results.md`'s
structural proof from the pre-live engineering phase. The 36
"imported emails & events" visible on the Connections dashboard both
before and after this connection belong to a separate, pre-existing
`synthetic`-provider row used by the local demo seed — confirmed
structurally unrelated (different `connected_accounts.id`, different
`provider` value, zero shared `source_items`).
