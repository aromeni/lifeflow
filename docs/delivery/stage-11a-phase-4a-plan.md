# Stage 11A Phase 4A Plan — Key-Versioned Credential Encryption and Rotation

**Status:** Complete — PASS — READY FOR PHASE 4B TEST-ACCOUNT READINESS (see [phase-4a-decision.md](../evaluation/stage-11/owner-validation/phase-4a/phase-4a-decision.md)) · **Date:** 2026-08-01

Companion: [stage-11a-owner-validation-plan.md](stage-11a-owner-validation-plan.md) · [stage-11a-phase-3-plan.md](stage-11a-phase-3-plan.md) · [docs/security/threat-model.md](../security/threat-model.md) · [phase-3-decision.md](../evaluation/stage-11/owner-validation/phase-3/phase-3-decision.md) (TOKEN_KEY rotation blocker, Path A) · [docs/evaluation/stage-11/owner-validation/phase-4a/](../evaluation/stage-11/owner-validation/phase-4a/)

## Objective

Implement and prove a durable, owner-scoped credential-key rotation model so encrypted Google credentials can be migrated between cryptographic keys without plaintext exposure, cross-account misuse, corruption, or unrecoverable credential loss — closing F-P3-03 (`TOKEN_KEY` has no rotation capability) via Path A (key-versioned migration), the path the project owner selected.

## Scope

Owner-only, synthetic-data-only. In scope: the encryption primitive and envelope format, the key-ring configuration model, database schema for key-version tracking, owner/account-bound authenticated encryption, the rotation/migration service, refresh-vs-rotation concurrency, disconnect/deletion interaction, backup/restore implications, failure injection, observability, and regression coverage. Out of scope: any real or disposable Google account, any real provider call, Phase 4B (test-account connection), the soak period, participant recruitment, Stage 12.

## Exclusions

No Google account is created or connected. No real or disposable-test OAuth credential is stored or used. No real provider is called — all rotation rehearsals use synthetic credentials and the existing fake-Google test infrastructure. No soak period starts. No participant is recruited, contacted, or evaluated. No paid infrastructure is provisioned. Stage 12 does not begin. No Stage 11/11A completion tag is created.

## Assumptions

- The existing `AesGcmTokenCipher` primitive (AES-256-GCM) is sound and is not being replaced — only extended with a key-ring wrapper and an authenticated-context (AAD) binding, per the governing instruction not to replace a secure primitive unnecessarily.
- The `v1:<key_id>:<nonce>:<ciphertext>` envelope format already anticipated a `key_id` field; this phase adds a `v2` envelope (same shape, AAD-bound) rather than changing `v1`'s wire format, preserving read-compatibility for any already-encrypted synthetic record.
- "Legacy key" in this design means: a key no longer used for new writes but still needed to decrypt not-yet-migrated rows. The key ring supports exactly the shape Path A requires — one active key, zero or more legacy keys — via a JSON-configured list rather than a fixed number of numbered env vars, so it scales to more than one legacy key without a schema/config change.

## Data-surface inventory (delta from Phase 3)

No new data surface is introduced beyond two new nullable columns on `connected_accounts` (`access_token_key_id`, `refresh_token_key_id`) — non-secret key identifiers, not key material, not tokens. No new table. No new external service.

## Threat categories addressed

- **T-4A-1 — Cross-account ciphertext transplant.** Before this phase, `AesGcmTokenCipher.decrypt()` used no associated authenticated data (AAD): any envelope decryptable under the active key would decrypt correctly regardless of which row's column it was placed in. This phase binds every new (`v2`) envelope's authentication tag to `f"{account_id}:{user_id}:{provider}:{field}"`, so an envelope moved to a different row, column, or account fails authentication (`InvalidTag`) rather than silently decrypting. Treated as P0 if it were to succeed.
- **T-4A-2 — Unsafe key retirement.** A legacy key must never be removed while any row still depends on it. The rotation service exposes an explicit zero-reference verification step; retirement is a deliberate, gated operator action, never automatic.
- **T-4A-3 — Refresh/rotation race.** Token refresh (row-locked, `SELECT ... FOR UPDATE`) and the rotation service (row-locked, `SELECT ... FOR UPDATE SKIP LOCKED`) must never corrupt a row or leave two writers' results mixed.
- **T-4A-4 — Migration data loss.** An interrupted migration must be resumable without ever marking a failed or partially-processed row as migrated, and must never delete a credential merely because it could not (yet) be decrypted.

## Inspection methods

Direct code reading of the existing cipher, service, model, and migration files (recorded in `existing-credential-boundary.md`); adversarial unit/integration tests against real PostgreSQL; a scripted multi-cycle rotation rehearsal; direct database inspection between rehearsal steps.

## Scenario inventory

See `docs/evaluation/stage-11/owner-validation/phase-4a/acceptance-matrix.md` for the full numbered list (`S11A-P4A-001` onward).

## Repetition requirements

Three complete rotation rehearsals (§11 of the governing task), each exercising the full create → dual-key → dry-run → batch-migrate → interrupt → resume → concurrent-refresh → retire → restart → verify → disconnect/delete → residue-check lifecycle.

## Severity rules

Unchanged from Phase 3's approved P0–P3 framework. Successful cross-account or cross-field decryption, plaintext leakage outside the controlled decryption boundary, silent data corruption, or a credential falsely marked migrated are P0. No threshold is lowered to accommodate a finding.

## Remediation rules

Ordinary defects are fixed before this phase is reported. Any P0 found stops closure immediately pending a fix and re-verification.

## Evidence rules

Evidence lives under `docs/evaluation/stage-11/owner-validation/phase-4a/`. No key material, plaintext credential, ciphertext derived from a real credential, raw log, raw database, backup, Redis dump, browser trace, session cookie, or absolute local path is committed. Synthetic examples in documentation are visibly non-secret placeholders.

## Residual-data decision rules

Unchanged from Phase 3: every surviving artefact after a rotation, disconnect, or deletion cycle must be classified REQUIRED RESIDUAL, TEMPORARY RESIDUAL, UNJUSTIFIED RESIDUAL, or DEFECT — no "miscellaneous."

## Exit criteria

See `phase-4a-decision.md` for the applied decision. PASS — READY FOR PHASE 4B TEST-ACCOUNT READINESS requires F-P3-03 closed, key-versioned encryption operational, migration resumable, concurrent refresh safe, owner/account binding proven, zero plaintext leakage, legacy-key retirement correctly gated, backup limitations documented, the full automated suite green, and zero unresolved P0/P1. CONDITIONAL PASS is reserved for an explicit non-exploitable P2 condition unrelated to safe storage or migration of a first disposable test-account credential. FAIL — TEST-ACCOUNT CONNECTION REMAINS BLOCKED is required for credential corruption, plaintext exposure, cross-account decryption, unsafe migration, a refresh/rotation race, inability to safely retire a legacy key, or misleading backup/deletion behaviour. Even PASS does not create or connect a Google account — that remains Phase 4B's separately-gated subject.
