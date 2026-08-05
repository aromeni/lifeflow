# Stage 11A Phase 6 — Cleanup and Final Residue Results

**Date:** 2026-08-05

## Imported-data deletion (checkpoint 7)

Deletion is processed asynchronously by the `arq` background worker (`run_deletion_operation`), which `./scripts/demo.sh` does not start by design. The worker (and Redis, also not started by `demo.sh`) were started specifically to process this one pending job, confirmed complete, then both stopped — matching this project's standing "workers stopped" precondition outside an active processing window.

```
deletion.dispatch_tick drained=1 requeued=0 failed=0
deletion.operation_done operation_id=7499a527-...
data_deletion_operations.state = succeeded
```

Verified directly:

| | Before | After |
|---|---|---|
| `SourceItem`s | 52 | 0 |
| Signals | 15 | 0 |
| Action proposals | 4 | 2 (content-free execution history, correctly preserved) |
| Execution records | 2 | 2 (preserved) |

0 inferred preferences existed (no draft was edited before approval, so memory inference was never triggered).

## Revocation and disconnect (checkpoint 8)

```
account.disconnected: {"provider": "google", "revocation_confirmed": true}
```

`revocation_confirmed: true` reflects an objective HTTP 200 from Google's revoke endpoint, independently corroborated by the owner. Local credential fields cleared (`encrypted_access_token`/`encrypted_refresh_token` both `NULL`).

## Stray identity-binding cleanup (D-6-02)

A targeted, single-column update cleared the `google_subject` binding created by the OIDC sign-in boundary crossing recorded in `defect-register.md` — see that document for the full account.

## Final environment state

`GOOGLE_OAUTH_INITIATION_ENABLED` and `GOOGLE_PROVIDER_WRITES_ENABLED` both restored to `false` in `.env` (git-ignored, no tracked change).

```
preconnection_readiness_check.py: 16/16 PASS — READY
rotate_credential_keys.py --connection-gate: unversioned=0 legacy_known=0 legacy_unknown=0 clear_to_connect=True
```

Full residual-data sweep, all zero:

```
source_items:          0
signals:                0
credential_rows:        0
identity_bindings:      0
inferred_preferences:   0
pending_deletion_ops:   0
```

No `arq` worker process running. No `stage-11*` tag exists. Working tree clean on `main`.
