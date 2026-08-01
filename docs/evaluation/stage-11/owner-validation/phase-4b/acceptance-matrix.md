# Stage 11A Phase 4B — Acceptance Matrix

**Status:** In execution · **Date:** 2026-08-01

Built before implementation began, per the governing task instruction. This phase is readiness-and-planning only: no row here requires or performs a real Google account, Google Cloud project, OAuth client, or provider call. Each row is verified by an automated test, a repository/documentation inspection, or a scripted dry run against the existing fake-provider infrastructure.

| ID | Readiness area | Method |
|---|---|---|
| S11A-P4B-001 | Starting boundary matches the governing instruction exactly (HEAD, main, tags, working tree, prior-phase evidence) | inspection |
| S11A-P4B-002 | Phase 1–4A evidence present and recorded status unchanged | inspection |
| S11A-P4B-003 | F-P3-03 and F-P3-04 remain CLOSED | inspection |
| S11A-P4B-004 | Migration 0012 present; single Alembic head | automated |
| S11A-P4B-005 | Key-versioned credential encryption (`TokenKeyRing`) active in `main.py`/`worker_app.py` | inspection |
| S11A-P4B-006 | Phase 4B connection gate (`credential_connection_gate`) exists and is callable | automated |
| S11A-P4B-007 | Credential inventory reports zero stored credentials and `clear_to_connect=true` | automated (dry run) |
| S11A-P4B-008 | No Google account, OAuth credential, or real API call exists anywhere in the repository or local state | inspection |
| S11A-P4B-009 | Current official Google OAuth/Cloud/Gmail/Calendar requirements documented with source and date | manual (web research), dated |
| S11A-P4B-010 | Testing-status refresh-token 7-day expiry and 100-test-user cap documented as a soak-period precondition, not solved in this phase | manual, dated |
| S11A-P4B-011 | Gmail scope restricted-verification requirement documented; Testing-status exemption documented | manual, dated |
| S11A-P4B-012 | Calendar scope sensitive-verification requirement documented; Testing-status exemption documented | manual, dated |
| S11A-P4B-013 | Test-account model defines exactly two disposable accounts (A, B) with purpose, naming, and prohibited-use rules | inspection |
| S11A-P4B-014 | Test-account model explicitly prohibits personal/business/academic/client/participant accounts | inspection |
| S11A-P4B-015 | Test-account model requires MFA, password-manager storage, and a neutral naming convention | inspection |
| S11A-P4B-016 | No account is created by this task | inspection |
| S11A-P4B-017 | Google Cloud project plan defines a dedicated, non-shared, non-billed project for owner-only testing | inspection |
| S11A-P4B-018 | No Google Cloud project is created by this task | inspection |
| S11A-P4B-019 | OAuth scope matrix lists only the four scopes actually requested by the current implementation (`google_scopes.py`) | automated (grep/inspection cross-check) |
| S11A-P4B-020 | Every listed scope maps to an implemented, approved product operation — no speculative scope | inspection |
| S11A-P4B-021 | `gmail.send`/`https://mail.google.com/`/`gmail.modify` are confirmed absent from the codebase | automated |
| S11A-P4B-022 | Calendar `patch`/`update`/`delete` methods are confirmed absent from the codebase | automated |
| S11A-P4B-023 | An automated test proves `GmailDraftClient` cannot construct a send request | automated (existing: `test_real_gmail_execution_calls_exactly_drafts_create`) |
| S11A-P4B-024 | An automated test proves `CalendarEventClient` has no update/delete method | automated (new structural test) |
| S11A-P4B-025 | Redirect URI plan documents the exact current configured values as placeholders, confirms server-controlled construction, and confirms no client-supplied redirect is accepted | inspection |
| S11A-P4B-026 | OAuth state is cryptographically strong, single-use, and TTL-bound | automated (existing) |
| S11A-P4B-027 | OAuth state is bound to the initiating session/user (connector-consent flow) | automated (existing) |
| S11A-P4B-028 | Cross-owner account binding is rejected | automated (existing) |
| S11A-P4B-029 | Purpose mismatch (sign-in state reused for connect, or vice versa) is rejected | automated (existing) |
| S11A-P4B-030 | Denied/cancelled Google consent (`error=access_denied`) is handled with a safe, explicit redirect rather than falling through an unrelated branch | automated (new — gap found and fixed) |
| S11A-P4B-031 | Replaying an already-consumed callback (same code+state) at the route level is rejected safely | automated (new — gap found and fixed) |
| S11A-P4B-032 | Callback after logout is rejected safely | automated (new — gap found and fixed) |
| S11A-P4B-033 | Malformed/partial callback parameters do not crash the route | automated (new) |
| S11A-P4B-034 | OAuth client secret handling plan defines env-only storage, never logged/returned/persisted in PostgreSQL/Redis/Audit History | inspection |
| S11A-P4B-035 | `.env.example` contains only placeholder Google credential values, never live-secret-shaped | automated (existing hook) |
| S11A-P4B-036 | Connection gate re-run 3× from clean state reports `clear_to_connect=true` | automated (dry run) |
| S11A-P4B-037 | A CI-safe test ensures the connection gate remains available and blocks a simulated unsafe state | automated (new) |
| S11A-P4B-038 | Synthetic Gmail dataset plan covers all 18 required scenario categories with stable IDs | inspection |
| S11A-P4B-039 | Synthetic Calendar dataset plan covers all 12 required scenario categories with stable IDs | inspection |
| S11A-P4B-040 | No synthetic message or event is created/sent during this phase | inspection |
| S11A-P4B-041 | First-connection runbook defines the exact 28-step controlled sequence from the governing instruction | inspection |
| S11A-P4B-042 | Connection authorisation (Decision 1) and write authorisation (Decision 2) are defined as separate, non-implying owner decisions | inspection |
| S11A-P4B-043 | Emergency-stop plan covers all 19 required stop conditions with detection/action/evidence/severity | inspection |
| S11A-P4B-044 | Cleanup plan covers OAuth revocation, LifeFlow disconnect, imported-data deletion, inferred-preference deletion, full deletion, and Google-side cleanup | inspection |
| S11A-P4B-045 | Real-provider data boundary explicitly separates permitted synthetic content from prohibited real/confidential categories | inspection |
| S11A-P4B-046 | Provider-call budget sets connection-only write budget to zero for Gmail drafts and Calendar insertions | inspection |
| S11A-P4B-047 | First-connection success criteria enumerate PASS/CONDITIONAL PASS/FAIL/stop conditions | inspection |
| S11A-P4B-048 | First-provider-write success criteria enumerate Gmail and Calendar requirements separately, and do not themselves authorise the writes | inspection |
| S11A-P4B-049 | Three complete dry runs of the 18-step rehearsal pass using only the existing fake-provider infrastructure | script (3 cycles) |
| S11A-P4B-050 | A content-free preconnection readiness command exists, returns non-zero on any mandatory-prerequisite failure, and never displays secrets | automated |
| S11A-P4B-051 | Readiness command covers: Alembic head, migration 0012, active key, dev-key-id rejection, connection gate, zero stored credentials, no dangerous test controls, no fake-provider override active, local services healthy | automated |
| S11A-P4B-052 | Fake-provider pathway cannot run when `E2E_TEST_CONTROLS_ENABLED=true` in production | automated (existing) |
| S11A-P4B-053 | Fake Google server refuses to start without its explicit opt-in env var | automated (existing) |
| S11A-P4B-054 | Demo-clock override cannot run in production | automated (existing or new) |
| S11A-P4B-055 | Consent-screen copy states factual placeholder values and explicitly labels the environment OWNER-ONLY DISPOSABLE-ACCOUNT TESTING, with no verification/approval/production claim | inspection |
| S11A-P4B-056 | Evidence-handling plan enumerates permitted vs prohibited evidence categories | inspection |
| S11A-P4B-057 | Owner walkthrough covers all 14 required screens/flows with the owner-observation template | manual |
| S11A-P4B-058 | No screenshot or evidence document contains real information, secrets, or absolute local paths | inspection |
| S11A-P4B-059 | Full automated backend/frontend/E2E/eval suite green after any remediation | automated |
| S11A-P4B-060 | Exact-boundary security proof finds nothing prohibited staged for commit | automated |

All 60 rows must PASS for this phase's decision to be PASS or CONDITIONAL PASS; any FAIL on a P0-class row (021–024, 026–029, 040, 046, 052–054, 060 — the rows matching the P0 examples in §27: send/update-delete capability, OAuth state/account-binding correctness, provider-write budget, and production test-bypass guards) forces **FAIL — GOOGLE CONNECTION REMAINS BLOCKED**. Rows 030–033 (denied-consent labelling, callback replay, post-logout callback, malformed-parameter handling) are P1/P2-class hygiene and observability rows — real gaps worth closing, but not on their own P0 stop conditions, since none of them permits cross-owner binding, token exposure, or an unauthorised write.
