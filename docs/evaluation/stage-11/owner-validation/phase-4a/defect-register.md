# Stage 11A Phase 4A — Defect Register

**Status:** 0 unresolved P0/P1 · 1 implementation-time defect found and fixed before any commit · **Date:** 2026-08-01

Companion: [acceptance-matrix.md](acceptance-matrix.md) · [phase-4a-decision.md](phase-4a-decision.md)

## P0 findings

None. No cross-account exposure, no plaintext leakage outside the controlled decryption boundary, no silent corruption, no record falsely marked migrated, no deleted credential resurrected, and no unbounded retry were found anywhere in this phase's testing (see [owner-account-binding-results.md](owner-account-binding-results.md), [concurrent-refresh-results.md](concurrent-refresh-results.md), [failure-injection-results.md](failure-injection-results.md)).

## P1 findings

None.

## Implementation-time defect (found and fixed before commit)

- **D-P4A-01 — a new account's first-ever encryption would have used the wrong AAD context.** While implementing `ConnectedAccountService.store_tokens()`'s context-binding, the new-account branch called `_encrypt_field()` (which derives its AAD from `account.id`) before the account had ever been flushed. SQLAlchemy's `mapped_column(default=uuid.uuid4)` is a flush-time default, not a construction-time one — verified directly (`account.id` returns `None` immediately after `ConnectedAccount(...)`, confirmed with a one-line interpreter check before touching the fix). Left uncorrected, every brand-new OAuth connection's very first encryption would have been bound to the context string `"None:<user_id>:google:access_token"`; the account's `id` would then be assigned as normal, and every subsequent decrypt attempt (using the real id) would derive a different, non-matching context and fail authentication outright — a full, immediate outage of the OAuth-connect path, not a subtle bug. **Fixed**: an explicit `await self._session.flush()` was added immediately after adding a brand-new account to the session, before any field is encrypted, guaranteeing `account.id` is real before it is used to derive an encryption context (`accounts.py`, `store_tokens()`). **Caught before any commit** by writing the real-database `test_stage11a_phase4a_credential_rotation.py` suite and the full backend test run — no user, deployment, or committed code was ever affected, since Phase 4A was implemented entirely on this feature branch with no intermediate merge.

## Non-defects explicitly considered and ruled out

- **`dry_run_inventory` counting field-references rather than rows** (a 6-account, 2-field-each dataset reports 12, not 6, references to a legacy key) — this is the correct, documented behaviour (the inventory answers "how many fields need migrating," which is what a bounded-batch migration actually processes), not a bug. The rotation rehearsal script's own first draft assumed row-counting and was corrected to match the service's actual, intentional semantics.
- **Redis untouched by this phase** — the rotation service performs no Redis I/O; there is nothing new for a Redis-residual scan to find, and none was fabricated.
- **No user-facing rotation UI or status endpoint** — deliberately not built, per the governing instruction that rotation must never be reachable from a user-controlled request (see [migration-design.md](migration-design.md)).

## Automated-suite regressions

None. The full pre-existing backend suite (932 tests, unrelated to this phase's own 15 new tests) was re-run in full after every substantive change and passed 100% on the final run.
