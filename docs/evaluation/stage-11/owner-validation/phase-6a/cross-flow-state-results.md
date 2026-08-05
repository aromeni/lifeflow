# Stage 11A Phase 6A — Cross-Flow OAuth-State Isolation Results

**Date:** 2026-08-05

## Pre-existing mechanism, reconfirmed fresh

`oauth_state.py`'s `begin_oauth_flow`/`consume_oauth_flow` already bind every pending flow to a `purpose` string (`"signin"` for OIDC, the connector's own purpose constant for connector-consent), checked before the `state` value itself:

```python
if pending.get("purpose") != purpose:
    raise OAuthStateError("OAuth flow purpose mismatch.")
```

This existed before Phase 6A and was not weakened or rewritten by it — the actual defect this phase fixes was solely at the initiation-gating layer (see `existing-coupling-analysis.md`). Two new tests reconfirm this mechanism fresh, against the newly-split gates, rather than assuming it still holds:

- `test_signin_state_cannot_be_consumed_by_the_connector_callback` — generates a real sign-in-flow state, then submits it to the connector callback with an attacker-supplied code. Result: `invalid_state`, not account binding.
- `test_connector_state_cannot_be_consumed_by_the_signin_callback` — the reverse. Result: `invalid_state`, not a login session.

Both tests run with both flows enabled (the highest-risk configuration for cross-flow confusion), not just the disabled case.

## What this proves

- Cross-flow state substitution fails, unconditionally.
- The connector callback cannot create a login session (it never calls `request.session["user_id"] = ...` — only the sign-in callback's code path does that).
- The sign-in callback cannot attach a connected account (it never calls `ConnectedAccountService.store_tokens()` — only the connector callback's code path does that).
- PKCE, owner/session binding (`bound_user_id` check), single-use consumption, and TTL expiry are all unchanged and still enforced identically for both flows.

No P0 condition (successful cross-flow state acceptance) was found.
