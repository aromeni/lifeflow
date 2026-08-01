# F-P3-03 Closure — TOKEN_KEY Rotation Capability

**Status:** CLOSED — KEY-VERSIONED ROTATION IMPLEMENTED AND VERIFIED · **Date:** 2026-08-01

Companion: [docs/evaluation/stage-11/owner-validation/phase-3/defect-register.md](../phase-3/defect-register.md) (original finding) · [docs/evaluation/stage-11/owner-validation/phase-3/secret-rotation-results.md](../phase-3/secret-rotation-results.md) · [docs/delivery/stage-11a-phase-4a-plan.md](../../../../delivery/stage-11a-phase-4a-plan.md) · [migration-design.md](migration-design.md) · [rotation-rehearsal-results.md](rotation-rehearsal-results.md)

## Original finding

Phase 3 recorded F-P3-03: `AesGcmTokenCipher` held exactly one active key; application wiring constructed exactly one cipher instance; a real key rotation had no supported path beyond a manual, ad-hoc, one-off script. This was one of the two open, non-exploitable P2 conditions that made Phase 3's decision CONDITIONAL PASS rather than an unqualified PASS, and it directly blocked Phase 4 (test-account connection) per the "TOKEN_KEY rotation — Phase 4 connection blocker" section of `phase-3-decision.md`.

## Closure criteria, checked against this phase's actual evidence

- [x] **All mandatory tests pass** — 15/15 new Phase 4A tests, 41/41 in the combined cipher+rotation suite, 932/932 pre-existing backend tests unaffected.
- [x] **All three rehearsals pass** — the key-rotation rehearsal (18-step lifecycle) and the backup/key-ring rehearsal, 3/3 cycles each, both runs repeated twice during this phase with identical results.
- [x] **Migration is resumable** — proven directly via a simulated interruption (rollback before commit) followed by a resume-to-completion run; no row was left half-migrated or double-processed.
- [x] **Concurrent refresh is safe** — a real token refresh and a real rotation batch racing the same row, against real PostgreSQL, never corrupted the row or produced an inconsistent result.
- [x] **No plaintext leaks** — a real sentinel scan across logs, database columns, backup dumps, and temporary files found zero occurrences of plaintext or key material outside the one controlled decryption boundary.
- [x] **No cross-account use occurs** — real-database transplant tests (ciphertext moved between accounts, and between a row's own access/refresh fields) both failed to decrypt, as required.
- [x] **Legacy-key retirement is gated by zero references** — `verify_key_retirement_safe` is the sole, directly-tested gate; retirement was proven blocked while references exist and permitted once they do not.
- [x] **Backup implications are documented** — the backup/key-ring rehearsal proves a pre-migration backup is unaffected by a later live-database migration, and that restoring with an incomplete key ring fails safely; the resulting production backup-key-retention requirement is recorded honestly, not solved (no production backup infrastructure exists yet).
- [x] **Production configuration fails safely** — malformed/duplicate/missing key configuration all raise at startup (`TokenCipherError` → `RuntimeError` in `main.py`); a new guard additionally refuses the literal `.env.example` development key-id default in production.

Every criterion is met. **F-P3-03 is closed.**

## What remains true and unchanged

Phase 3's historical decision — **CONDITIONAL PASS — READY FOR PHASE 4 READINESS GATE** — is not rewritten as though it were originally unconditional. It was conditional at the time it was recorded, correctly, because F-P3-03 was open then. This closure is a dated addendum to that history, not a retroactive edit of it. The remaining Phase 3 P2 condition (F-P3-04, `brace-expansion`) is unaffected by this closure and is handled independently — see [f-p3-04-reassessment.md](f-p3-04-reassessment.md).

## What this closure does and does not authorise

Closing F-P3-03 removes the specific, named blocker Phase 3's decision recorded against Google test-account connection. It does **not**, by itself:

- create or connect a Google account;
- store a real or disposable-test OAuth credential;
- call the real Google provider;
- start the soak period;
- authorise participant recruitment;
- begin Stage 12;
- authorise Phase 4B.

Phase 4B (test-account connection) remains its own, separately-gated task requiring its own explicit approval, per this task's governing instruction.
