# First-Connection Success Criteria

**Status:** Defined; not yet evaluated against a real connection · **Date:** 2026-08-01

Companion: [first-connection-runbook.md](first-connection-runbook.md) · [emergency-stop-plan.md](emergency-stop-plan.md)

A future connection (Decision 1) may pass only when **all** of the following hold:

- The correct disposable account (Account A) is connected.
- Only the four approved scopes ([oauth-scope-matrix.md](oauth-scope-matrix.md)) are displayed and granted — no more, no fewer.
- Exactly one `v2`-encrypted credential set is stored for the connection.
- Credential metadata (`access_token_key_id`/`refresh_token_key_id`) references the currently active key.
- No `v1` or unknown-key-version credential envelope exists anywhere for this account.
- No plaintext token appears in any ordinary PostgreSQL column (only the encrypted envelope columns are populated).
- No token appears in Redis.
- No token appears in browser storage.
- No token appears in application logs.
- No token appears in Prometheus metrics.
- No token appears in Audit History.
- The Gmail read smoke test succeeds (`sync` imports messages without error).
- The Calendar read smoke test succeeds (`sync` imports events without error).
- Imported objects are correctly owner-scoped (`user_id` matches the connecting LifeFlow user).
- No provider write occurs during this test.
- Disconnect works (`POST /connected-accounts/google/disconnect` clears credential fields and is confirmed via the connection gate).
- OAuth revocation works, or — if Google's revoke endpoint is unreachable — the local-only outcome is represented truthfully, never claimed as a confirmed Google-side revocation without checking.
- Imported-data deletion works (existing privacy-tooling path, confirmed for real-provider-sourced data).
- Zero credential residue remains after cleanup (per [test-account-cleanup-plan.md](test-account-cleanup-plan.md)'s post-cleanup verification).
- The connection may be repeated (disconnect → reconnect) without unexplained state (e.g. a stale key-id column, a duplicate `ConnectedAccount` row).

## Decision

- **PASS**: every criterion above holds, with no P0/P1 finding.
- **CONDITIONAL PASS**: a non-safety P2 finding exists (e.g. an observability nicety), with an explicit closure condition, and no criterion above is itself violated.
- **FAIL**: any criterion above does not hold, or any [emergency-stop-plan.md](emergency-stop-plan.md) condition triggers during the attempt.

## Immediate stop conditions

Any condition in [emergency-stop-plan.md](emergency-stop-plan.md) triggers an immediate stop, superseding continued evaluation against this checklist until root-caused.

## Status of this document

No real connection has been attempted. This document defines the bar a future, separately-authorised connection task must clear — it is not itself evidence that any bar has been cleared.
