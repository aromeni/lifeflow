# Stage 11A Phase 3 — Threat and Privacy Scenario Inventory

**Status:** Complete · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) · [../../../../security/threat-model.md](../../../../security/threat-model.md)

Phase 3 does not introduce new threat IDs — it exercises and extends evidence for the existing closed threat-model table (T1–T31) and closes three previously-untracked gaps the Phase 3 audit found: secret-rotation capability, dependency/container hardening, and backup-vs-deletion interaction (extensions of T1/T15/T16).

| Threat / area | Mechanism | Phase 3 contribution |
|---|---|---|
| T2 (cross-user access) | `user_id` FK + repository ownership filtering | New consolidated API-level IDOR test across proposal/execution/memory/deletion/scheduled-brief routes (S11A-P3-001/002/004/006) |
| T19 (session hijack / weak auth) | Signed, httpOnly, SameSite session cookie, 8h max-age | New session-expiry-boundary and malformed-cookie tests (S11A-P3-009/010) |
| T1 (token theft) | AES-256-GCM envelope, one active key | New sentinel lifecycle search across DB/Redis/logs (S11A-P3-014); new honest secret-rotation-capability rehearsal (S11A-P3-017/018/019) |
| T6 (secrets in logs) | `redact()` regex backstop | New end-to-end log-privacy sentinel capture across 7 real workflow stages (S11A-P3-022) |
| T31 (telemetry leak) | Closed metrics label vocabularies | Existing `test_metrics.py`, re-run fresh |
| T8 (XSS) / T10 (SQLi) | React auto-escaping, parameterised ORM | New dedicated injection-resistance test file through real routes (S11A-P3-027) |
| T13/T24 (approval tamper) | Approval binding hash | Existing `test_action_policy_tamper.py`, re-run fresh |
| T21 (rate-limit abuse) | HMAC-pseudonymised Redis subjects | Existing 5-file suite, re-run fresh; direct `redis-cli` inspection confirming no raw subject in a bucket key/value |
| T16 (deletion correctness) | Deletion engine, account anonymisation | New repetition-count coverage (5x/5x/10x/10x) the audit found missing (S11A-P3-031–034); new backup-vs-deletion validation (S11A-P3-036) |
| T15 (retention) | `retention_expires_at`, retention jobs | Residual-data analysis after every deletion path (S11A-P3-035) |
| (untracked gap, closed this phase) | Dependency vulnerability exposure | First `pip-audit`/`pnpm audit` run in this project's history (S11A-P3-039) — found and fixed real Next.js/postcss/sharp/js-yaml CVEs |
| (untracked gap, closed this phase) | Container/runtime posture | First container hardening review (S11A-P3-040) — found and fixed a loopback-binding gap |
| ADR 0005 D92 (test-control isolation) | Production-refusal guards | Existing `test_e2e_test_controls.py`, re-run fresh |
