# Stage 11A Phase 4A — Decision

**Status:** Decision recorded · **Date:** 2026-08-01

Companion: [acceptance-matrix.md](acceptance-matrix.md) · [defect-register.md](defect-register.md) · [f-p3-03-closure.md](f-p3-03-closure.md) · [f-p3-04-reassessment.md](f-p3-04-reassessment.md) · [phase-4b-connection-gate.md](phase-4b-connection-gate.md) · [../../owner-validation-exit-template.md](../../owner-validation-exit-template.md)

## Decision

**PASS — READY FOR PHASE 4B TEST-ACCOUNT READINESS**

## Criteria checked

- [x] **F-P3-03 closed** — key-versioned rotation implemented and verified; see [f-p3-03-closure.md](f-p3-03-closure.md).
- [x] **Key-versioned encryption operational** — `TokenKeyRing` holds one active plus zero-or-more legacy keys, implements the existing `TokenCipher` protocol unchanged, and is wired into both the API and worker processes via `build_key_ring()`.
- [x] **Active/legacy key handling verified** — new writes always use the active key (`test_key_ring_encrypts_with_the_active_key`); legacy-key rows decrypt correctly through the ring (`test_key_ring_decrypts_a_legacy_key_row`); an unknown key id fails explicitly (`test_key_ring_rejects_unknown_key_id`).
- [x] **Migration resumable** — proven via simulated interruption (rollback) followed by resume-to-completion, with zero data loss or double-processing.
- [x] **Concurrent refresh safe** — a real refresh and a real rotation batch racing the same PostgreSQL row never corrupted it or produced an inconsistent result.
- [x] **Owner/account binding proven** — real-database ciphertext-transplant attempts across accounts and across fields both failed to decrypt, exactly as required; treated as P0 if either had succeeded, and neither did.
- [x] **Zero plaintext leakage** — a sentinel scan across logs, database columns, backup dumps, and temporary files found no plaintext or key material outside the one controlled decryption boundary.
- [x] **Legacy-key retirement correctly gated** — `verify_key_retirement_safe` is the sole, directly-tested gate, proven both blocking (references exist) and permitting (references cleared).
- [x] **Backup limitations documented** — a new backup/key-ring rehearsal (3/3 cycles) proved directly that a pre-migration backup is unaffected by a later live-database migration, and that restoring with an incomplete key ring fails safely; the resulting production backup-key-retention requirement is recorded honestly.
- [x] **Full automated suite green** — 953 backend tests (915 pre-existing on the prior `main` boundary + 32 new at PR-open time + 6 more added during the PR #13 merge-integrity check; all passing — corrected from an earlier "932 pre-existing + 15 new" figure, see [defect-register.md](defect-register.md)), frontend/E2E/eval suites unaffected by this backend-only phase, Ruff/mypy clean, single Alembic head (`0012`).
- [x] **Zero unresolved P0/P1** — one implementation-time defect (D-P4A-01) was found and fixed before any commit; see [defect-register.md](defect-register.md).
- [x] **Phase 4B pre-connection gate exists and fails closed** — `credential_connection_gate()` (row S11A-P4A-047) inspects only non-secret key-version columns and blocks on any unversioned, legacy-known, or legacy-unknown reference; verified against real local database state (which initially held non-Google Playwright test residue, since removed) — see [phase-4b-connection-gate.md](phase-4b-connection-gate.md).

## Separately closed in this phase

F-P3-04 (`brace-expansion`) was reassessed with fresh, independent evidence (repeated audit, advisory-range arithmetic, dependency-chain inspection, bundle inspection) and is recommended **CLOSE** — see [f-p3-04-reassessment.md](f-p3-04-reassessment.md). With both Phase 3 P2 conditions now closed, no open P2/P3 condition remains from either phase.

## What this decision does not do

This decision does **not** create or connect a Google account, store a real or disposable-test OAuth credential, call the real Google provider, start the soak period, or authorise participant recruitment. Phase 4B (proposed: Dedicated Test-Account Readiness and Controlled Connection Gate) requires its own explicit-approval task. Stage 12 remains unstarted. No Stage 11/11A completion tag is created by this decision.

## Decided by

This task's execution (Stage 11A Phase 4A key-versioned credential encryption and rotation). Authority to begin Phase 4B rests with the project owner.

## Date

2026-08-01
