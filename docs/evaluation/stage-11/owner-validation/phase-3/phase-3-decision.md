# Stage 11A Phase 3 — Decision

**Status:** Decision recorded · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) · [defect-register.md](defect-register.md) · [../../owner-validation-exit-template.md](../../owner-validation-exit-template.md)

## Decision

**CONDITIONAL PASS — READY FOR PHASE 4 READINESS GATE**

This is a conditional pass, not a failure: all 44 acceptance-matrix scenarios PASS and zero P0/P1 findings exist anywhere. The condition is programme-level, not a failed security test — two P2 findings remain open with an explicit closure condition each (`TOKEN_KEY` rotation capability; `brace-expansion` dev-tooling exposure), and neither is described as closed. Per the approved Phase 3 decision framework, unresolved non-exploitable P2 conditions require a conditional classification rather than an unqualified PASS.

## Criteria checked

- [x] Every mandatory Phase 3 scenario verified — all 44 acceptance-matrix rows (`S11A-P3-001` to `044`) PASS.
- [x] No unresolved P0/P1 — zero of either. Two P2 findings were fixed within this phase (local dev database/Redis network exposure; Next.js/postcss/sharp CVEs); two P2 findings remain **open, unresolved, with an explicit closure condition**, neither exploitable today (`TOKEN_KEY` rotation capability; `brace-expansion` in dev-tooling-only paths) — see [defect-register.md](defect-register.md). These two open conditions are the reason the decision is conditional rather than unqualified.
- [x] No cross-user exposure — 13 new owner-scoping tests, 12 cross-user-isolation tests (re-run from Phase 2, extended), zero disclosure found.
- [x] No plaintext credential exposure — a real sentinel-token lifecycle search across 5 full cycles found the plaintext nowhere outside the one encrypted envelope column, at every stage (create/refresh/disconnect/delete).
- [x] No private content in logs, metrics or Redis — a real end-to-end sentinel scan across 5 full workflow cycles (11 sentinel types each) found zero leaks in captured structured logs; metrics remain proven closed-vocabulary at the AST level; direct `redis-cli` inspection confirmed only HMAC digests and opaque job bookkeeping.
- [x] No sensitive browser-storage residue — a new Playwright privacy walkthrough confirmed empty `localStorage`/`sessionStorage`/IndexedDB/`document.cookie` at every screen (one framework-internal, non-content-bearing key found and explicitly allowlisted, not a defect).
- [x] No production-accessible test bypass — all test-control production-refusal guards re-confirmed fresh.
- [x] All four privacy operations remain distinct — disconnect, imported-data deletion (5x), inferred-preference deletion (5x), and full account deletion (10x, plus 10x preceded by an uncertain execution) all verified to stay within their own boundary at the required repetition counts.
- [x] Deletion residuals are justified and content-minimised — every surviving row/key after every deletion path classified REQUIRED RESIDUAL or self-expiring TEMPORARY RESIDUAL; zero UNJUSTIFIED RESIDUAL or DEFECT classifications.
- [x] Session invalidation works — a new expiry-boundary test and 6 malformed-cookie shapes all correctly rejected; logout confirmed to invalidate future protected requests, re-confirmed via the browser walkthrough's post-logout revisit.
- [x] Credentials become unusable after disconnect/deletion — re-confirmed via existing tests and this phase's sentinel search.
- [x] Uncertain-execution tombstones remain content-free — proven directly across 10 fresh cycles, including with a real sentinel draft body that never survives into the tombstone.
- [x] Backup limitations are documented truthfully — a new backup-vs-deletion rehearsal (3/3 cycles) proved directly, not merely asserted, that a pre-deletion backup retains pre-deletion state after later deletion, with the resulting production backup-retention-policy requirement explicitly recorded rather than silently assumed solved.
- [x] Full automated suite is green — 915 backend tests (91% coverage, up from 90%), 90 frontend tests, full functional/design/resilience E2E suites, all 5 local eval modes, contracts current, metrics regenerated twice, single Alembic head, Ruff/mypy/ESLint/TypeScript/Prettier all clean, production build succeeds on the patched Next.js 16.2.12, 28/28 contrast checks, 12/12 pre-commit hooks, `detect-secrets`/staged+full-history Gitleaks clean — see the final report's automated-suite section for exact figures.

## TOKEN_KEY rotation — Phase 4 connection blocker

**No Google test account may be connected until the project owner approves and the repository validates one of the following credential-key rotation paths.** This blocker is recorded here because it is the one open P2 condition (F-P3-03) with a direct, structural bearing on Phase 4: Phase 4 proposes connecting real (disposable, synthetic) Google test accounts, and this project has no tested way to rotate the key protecting those accounts' stored credentials.

### Path A — key-versioned migration

A tested mechanism supporting:

- active and legacy decryption keys held concurrently;
- versioned encrypted credential records (a stored key-id per envelope, as `AesGcmTokenCipher`'s `v1:<key_id>:<nonce>:<ciphertext>` envelope format already anticipates);
- new encryption performed only with the active key;
- controlled re-encryption of existing credentials from the legacy key to the active key;
- atomic owner/account-bound migration (no partial-migration state left visible to policy or execution code);
- rollback and failure handling if a migration run is interrupted;
- removal of the retired key only after every affected credential has been confirmed re-encrypted.

### Path B — disposable-account destructive rotation

Allowed only during owner-only pre-production testing with synthetic, disposable Google accounts. It requires:

- disconnecting every test account;
- removing all encrypted credential rows for those accounts;
- proving by direct inspection that no credential ciphertext under the retiring key remains anywhere (database, backups, Redis);
- rotating `TOKEN_KEY`;
- restarting all relevant services;
- reconnecting the disposable accounts under the new key;
- proving the old key is no longer referenced or needed anywhere in the system.

**Path B must never be used for**: a personal account, a participant account, a client account, a production account, or any account containing real or confidential information. It is destructive by design and is only acceptable where every affected credential is disposable and synthetic.

### What is and is not authorised by this record

- Phase 4 **readiness planning** may begin.
- Google test-account **creation and connection remain blocked** until the project owner chooses Path A or Path B (or a different, formally reviewed key-management design) for this specific gap.
- A **production deployment** still requires a durable, key-versioned rotation design (Path A or an equivalent formally reviewed key-management system) regardless of which path is chosen for pre-production test-account use — Path B's destructive rotation is not a substitute for production key-rotation capability.
- This record does **not** choose Path A or Path B on the project owner's behalf. That choice, and its timing relative to Phase 4, rests with the project owner.

## What this decision does not do

This decision does **not** authorise Phase 4 execution, participant recruitment, test-account connection, or the soak period — each remains separately gated. Phase 4 (proposed: Dedicated Test-Account Readiness and Controlled Connection Gate) requires its own explicit-approval task and does not itself authorise Google test accounts or the soak period. Recruitment remains blocked by `recruitment-authorisation-checklist.md`; test accounts and the soak period remain planning-only per `stage-11a-owner-validation-plan.md` §B/§C.

## A note on scope honesty

Most of the mechanisms this phase's acceptance matrix required were already correctly implemented before this phase began (Stages 7–9, Phase 1, Phase 2) — this phase's real contribution is: (1) re-verifying that existing evidence fresh, (2) extending automated coverage to the specific repetition counts, sentinel-search depth, and cross-cutting angles (browser storage, real network responses) no prior test met, and (3) running this project's first-ever dependency-vulnerability and container-hardening scans, which found and fixed two genuine, real-world security gaps (loopback-only local service binding; multiple high-severity Next.js/postcss/sharp CVEs) that no amount of application-level testing alone would ever have surfaced. One test-script defect (T-P3-1, a leftover Redis key causing order-dependent test pollution) was found and fixed; zero product-code defects were found anywhere in `apps/api/src` or `apps/web/src`.

## Decided by

This task's execution (Stage 11A Phase 3 security, privacy and residual-data validation). Authority to begin Phase 4 rests with the project owner.

## Date

2026-07-31
