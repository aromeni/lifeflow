# Stage 11A Phase 3 — Acceptance Matrix

**Status:** In execution · **Date:** 2026-07-31

Companion: [../../../../delivery/stage-11a-phase-3-plan.md](../../../../delivery/stage-11a-phase-3-plan.md) · [threat-and-privacy-scenario-inventory.md](threat-and-privacy-scenario-inventory.md) · [defect-register.md](defect-register.md)

Every row: data/attack surface · synthetic precondition · action performed · expected data state · expected security control · prohibited exposure · inspection method · objective evidence · result · defect reference.

## Owner-scoping (IDOR)

| ID | Surface | Precondition | Action | Expected state/control | Prohibited exposure | Inspection method | Evidence | Result | Defect |
|---|---|---|---|---|---|---|---|---|---|
| S11A-P3-001 | Action proposals (GET/PATCH/approve/reject/execute by id) | 2 synthetic users, user A owns a proposal | User B requests/mutates user A's proposal id (valid foreign id, guessed id, stale id) — 5 attempts | 404 for every attempt, no mutation | Cross-user disclosure or mutation | New API-level test, real HTTP routes | `test_stage11a_phase3_owner_scoping.py` | PASS | — |
| S11A-P3-002 | Action executions (via proposal `/execute`) | User A's proposal executed | User B attempts `/execute` on A's proposal id | 404, zero executor invocation | Cross-user execution | Same file | Same | PASS | — |
| S11A-P3-003 | Audit History | User A has audit events | User B lists/reads with A's ids/cursors | Empty/404, no existence oracle | Cross-user audit leakage | Existing: `test_audit_history.py` (`_login` pattern), re-run | `test_audit_history.py` | PASS | — |
| S11A-P3-004 | Deletion operations | User A has a preview/confirmed operation | User B reads/cancels A's operation id | 404 | Cross-user deletion-state leakage | Existing: `test_privacy_deletion_api.py::test_cross_user_operation_is_404`, re-run + extended to cancel/status | `test_privacy_deletion_api.py`, new extension in `test_stage11a_phase3_owner_scoping.py` | PASS | — |
| S11A-P3-005 | Preferences | User A sets a preference | User B requests A's preference key under A's user context (route is always current-user; test proves no id-based bypass exists) | Route has no id parameter; verified no path/body field can select another user | Cross-user preference read/write | Existing: `test_preferences.py`, re-run | `test_preferences.py` | PASS | — |
| S11A-P3-006 | Scheduled briefs / imported-data & account-deletion previews | User A has a scheduled-brief status and a preview | User B requests with A's ids | 404, settings-style routes stay current-user-only | Cross-user schedule/preview leakage | New, `test_stage11a_phase3_owner_scoping.py` | Same | PASS | — |

## Session and authentication security

| ID | Surface | Precondition | Action | Expected state/control | Prohibited exposure | Inspection method | Evidence | Result | Defect |
|---|---|---|---|---|---|---|---|---|---|
| S11A-P3-007 | Session cookie config | Real app instance | Inspect `SessionMiddleware` config | `same_site=lax`, `https_only` in production, `max_age=8h`, signed | Weak cookie posture | Code inspection + existing test | `main.py:208-213`, `test_auth_api.py` | PASS | — |
| S11A-P3-008 | Tampered session | Valid session | Mutate signature bytes, replay | 401, session cleared | Authenticated access via forged cookie | Existing: `test_session_cookie_is_rejected_after_tampering`, re-run | `test_auth_api.py` | PASS | — |
| S11A-P3-009 | Malformed (non-tampered) session | No valid session | Send garbage/non-itsdangerous cookie value | 401, no 500, no internals disclosed | Unhandled exception, stack trace | New test | `test_stage11a_phase3_session_security.py` | PASS | — |
| S11A-P3-010 | Session-expiry boundary | Session near `max_age` | Advance clock past 8h boundary | 401 after expiry, valid before | Sessions outliving their configured TTL | New test | `test_stage11a_phase3_session_security.py` | PASS | — |
| S11A-P3-011 | CSRF / logout / replay | Valid session | Missing CSRF header on state-changing route; logout then replay | 403 without header; protected route 401 after logout | State-changing request without CSRF; post-logout mutation | Existing: `test_auth_api.py`, re-run 10× | `test_auth_api.py` | PASS | — |

## OAuth credential handling

| ID | Surface | Precondition | Action | Expected state/control | Prohibited exposure | Inspection method | Evidence | Result | Defect |
|---|---|---|---|---|---|---|---|---|---|
| S11A-P3-012 | Token encryption at rest | Synthetic account connected | Inspect `connected_accounts` row directly | Only AES-GCM envelope (`v1:<key_id>:<nonce>:<ciphertext>`) | Plaintext token in a database column | Existing: `test_no_plaintext_token_reaches_the_database`, re-run | `test_accounts_service.py` | PASS | — |
| S11A-P3-013 | Refresh locking / revocation / disconnect | Synthetic account | Concurrent refresh, revoked-consent refresh, disconnect | Row-lock serializes refresh; `invalid_grant`→revoked; disconnect drops tokens | Duplicate refresh call; usable token post-disconnect | Existing: `test_google_token_service.py`, `test_accounts_service.py`, re-run | Same | PASS | — |
| S11A-P3-014 | Token sentinel lifecycle search | A distinctive synthetic access/refresh-token sentinel value | Create → refresh → disconnect → delete account; search DB, Redis, structured logs after each stage | Sentinel appears only inside the encrypted envelope column, never elsewhere | Plaintext sentinel in Redis, logs, audit, or any other DB column | New test, 5 lifecycle cycles | `test_stage11a_phase3_token_sentinel_search.py` | PASS | — |
| S11A-P3-015 | Audit-metadata token exposure | Token operations audited | Inspect `safe_metadata_json` for every account-lifecycle audit event | No token/ciphertext field present | Token or ciphertext in audit metadata | Existing: `test_action_proposals.py` sentinel assertions, re-run | Same | PASS | — |
| S11A-P3-016 | Cross-account token use | 2 synthetic connected accounts | Attempt to use account A's token context for account B's execution | Rejected, execution-context hash mismatch | Cross-account token reuse | Existing: `test_google_token_service.py` execution-context tests, re-run | Same | PASS | — |

## Secret rotation

| ID | Surface | Precondition | Action | Expected state/control | Prohibited exposure | Inspection method | Evidence | Result | Defect |
|---|---|---|---|---|---|---|---|---|---|
| S11A-P3-017 | Session secret | Local `.env` | Rotate `SESSION_SECRET`, restart | Old sessions invalidated (signature no longer verifies); new sessions issue correctly | Session valid across incompatible secrets | New rehearsal script | `stage11a_phase3_secret_rotation_rehearsal.py` | PASS (restart-only, forced invalidation) | — |
| S11A-P3-018 | Token-cipher key (`TOKEN_KEY`/`TOKEN_KEY_ID`) | Synthetic encrypted account rows exist | Rotate key, attempt to decrypt old rows with new key alone; then with dual-key read path | Old-key rows unreadable under new-only key (expected — no dual-key migration exists); documented as a genuine gap, not silently accepted | Silent data corruption or a false claim of migration support | New rehearsal script | Same | FINDING recorded (P2) | See defect-register |
| S11A-P3-019 | Rate-limit HMAC secret (`RATE_LIMIT_KEY_SECRET`) | Existing rate-limit buckets | Rotate secret, observe bucket keys | New secret produces new bucket keys (effectively a one-time reset, fail-open unaffected) | Cross-secret bucket collision | New rehearsal script | Same | PASS | — |
| S11A-P3-020 | Fake-provider / test DB / test Redis credentials | Local dev stack | Confirm these are synthetic, restart-only, never require live rotation | No production analog exists for these | Any live-provider dependency | Code inspection | `stage-11a-phase-3-plan.md` assumptions | PASS | — |
| S11A-P3-021 | Rotation capability summary | — | Classify each secret by rotation capability | Explicit per-secret classification (immediate / restart-only / dual-key-unsupported) | Claiming a capability that does not exist | Documentation | `secret-rotation-results.md` | PASS (honest gap recorded) | — |

## Logging and telemetry privacy

| ID | Surface | Precondition | Action | Expected state/control | Prohibited exposure | Inspection method | Evidence | Result | Defect |
|---|---|---|---|---|---|---|---|---|---|
| S11A-P3-022 | Structured logs | Sentinel strings for email/token/session-cookie/db-url/etc | Exercise normal op, validation failure, provider outage, uncertain write, refresh, revocation, rate limit, deletion, DB/Redis outage; capture logs to an isolated temp file | Zero sentinels found; sanitised exception text; no stack trace to client | Any sentinel appearing in captured log output | New test using `caplog`, 5 full workflow runs | `test_stage11a_phase3_log_privacy.py` | PASS | — |
| S11A-P3-023 | Metrics label vocabularies | Real metrics registry | Exercise success/failure paths, inspect every label value | Labels drawn only from closed literal vocabularies, ≤3 labels/metric, bounded cardinality | User/account/proposal/execution id, email, IP, exception text as a label | Existing: `test_metrics.py`, re-run | Same | PASS | — |

## Redis residual data

| ID | Surface | Precondition | Action | Expected state/control | Prohibited exposure | Inspection method | Evidence | Result | Defect |
|---|---|---|---|---|---|---|---|---|---|
| S11A-P3-024 | Redis key/value inspection | Rate-limit buckets, arq job records populated via 5 reset/workflow/deletion cycles | `redis-cli --scan`+`GET` direct inspection after each cycle | Only HMAC digests and opaque UUID+status job records; every key has a TTL or documented durable justification | Raw email, token, proposal payload, source-item content | Direct `redis-cli` inspection + existing `test_rate_limiter.py` re-run 5× | `redis-residual-analysis.md` | PASS | — |

## Browser-side privacy

| ID | Surface | Precondition | Action | Expected state/control | Prohibited exposure | Inspection method | Evidence | Result | Defect |
|---|---|---|---|---|---|---|---|---|---|
| S11A-P3-025 | Browser storage, console, network | Real dev stack, synthetic owner | Owner-operated walkthrough across landing/onboarding/Today/Approvals/Audit/Connections/Settings/deletion/outage/uncertain-outcome, 5 sessions | No token in browser; no private content in localStorage/sessionStorage/IndexedDB/cookies beyond the httpOnly session cookie; no private console errors | OAuth token, private content, or another synthetic owner's data reaching the browser | New Playwright walkthrough + existing grep confirming zero client-storage API usage | `phase3-privacy-walkthrough.spec.ts`, `browser-privacy-results.md` | PASS | — |

## API response minimisation

| ID | Surface | Precondition | Action | Expected state/control | Prohibited exposure | Inspection method | Evidence | Result | Defect |
|---|---|---|---|---|---|---|---|---|---|
| S11A-P3-026 | `/connected-accounts`, `/privacy/summary`, proposal/execution/audit responses | Synthetic account with encrypted tokens | Inspect raw JSON response bodies by field name | Encrypted-token field names absent by name, not merely by value | `encrypted_access_token`/`encrypted_refresh_token` field present in any response | New negative-serialization test | `test_stage11a_phase3_api_minimisation.py` | PASS | — |

## Input handling and injection resistance

| ID | Surface | Precondition | Action | Expected state/control | Prohibited exposure | Inspection method | Evidence | Result | Defect |
|---|---|---|---|---|---|---|---|---|---|
| S11A-P3-027 | Proposal payload/preference/display-name text fields | Real API + real ORM | Submit `<script>`, `javascript:` URLs, SQL-like strings, template expressions, long/Unicode/control-character content through real routes | Stored/returned verbatim as inert text, never executed; no SQL error; bounded length | Stored/reflected XSS, SQL error surfacing schema detail, unbounded storage | New test file, real HTTP routes + real Postgres | `test_stage11a_phase3_injection_resistance.py` | PASS | — |

## Action-proposal tamper resistance

| ID | Surface | Precondition | Action | Expected state/control | Prohibited exposure | Inspection method | Evidence | Result | Defect |
|---|---|---|---|---|---|---|---|---|---|
| S11A-P3-028 | Approval binding hash | Approved proposal | Attempt to alter payload/account/risk/status after approval, before/after/during execution | Fresh approval required; wrong-account rejected; stale version non-executable; no mass assignment | Executing a mutated proposal without fresh approval | Existing: `test_action_policy_tamper.py`, re-run | Same | PASS | — |

## Rate-limit privacy

| ID | Surface | Precondition | Action | Expected state/control | Prohibited exposure | Inspection method | Evidence | Result | Defect |
|---|---|---|---|---|---|---|---|---|---|
| S11A-P3-029 | Rate-limit subjects | Real Redis | Exercise authenticated/anonymous/spoofed-proxy/cross-owner scenarios | HMAC-pseudonymised subjects; spoofed headers ignored; owners isolated | Raw IP/user id in Redis key, log, or metric | Existing 5-file suite, re-run | `test_rate_limit_policy.py` et al. | PASS | — |

## Privacy operations (disconnect / imported-data / inferred-preference / account deletion)

| ID | Surface | Precondition | Action | Expected state/control | Prohibited exposure | Inspection method | Evidence | Result | Defect |
|---|---|---|---|---|---|---|---|---|---|
| S11A-P3-030 | Disconnect | Synthetic connected account | Disconnect, 5 cycles across distinct accounts | Credentials unusable; imported data/preferences untouched; account stays active | Usable token post-disconnect | Existing: `test_accounts_service.py`, re-run 5× | Same | PASS | — |
| S11A-P3-031 | Imported-data deletion | Synthetic source items | Preview→confirm→run, 5 cycles | Imported content removed; unrelated preferences remain; account active | Content surviving in DB/Redis/logs/browser | New repetition test (Phase-2-pattern), 5× | `test_stage11a_phase3_deletion_repeatability.py` | PASS | — |
| S11A-P3-032 | Inferred-preference deletion | Synthetic memory items | Delete-all-inferred, 5 cycles | Inferred memory removed; explicit preferences/imported content remain | Inferred memory surviving deletion | Same file, 5× | Same | PASS | — |
| S11A-P3-033 | Full account deletion | Synthetic account with full reference graph | Exact-phrase confirm→run, 10 cycles across distinct synthetic users | Content-bearing records removed/anonymised; credentials removed; safe tombstone only | Reversible content, usable session, cross-owner effect | Same file, 10× | Same | PASS | — |
| S11A-P3-034 | Uncertain execution then account deletion | Proposal executed to `uncertain`, then account deleted | 10 cycles | Content-free reconciliation state survives deletion; no draft/event content in tombstone | Draft/event content surviving in the tombstone | Same file, 10× | Same | PASS | — |

## Residual-data, backup, tombstone and artefact analysis

| ID | Surface | Precondition | Action | Expected state/control | Prohibited exposure | Inspection method | Evidence | Result | Defect |
|---|---|---|---|---|---|---|---|---|---|
| S11A-P3-035 | Residual-data enumeration | After every deletion path above | Enumerate every remaining row/key | Every residual classified REQUIRED/TEMPORARY/UNJUSTIFIED/DEFECT, none "miscellaneous" | Unclassified or unjustified content-bearing residual | Direct DB/Redis inspection | `deletion-residual-analysis.md` | PASS | — |
| S11A-P3-036 | Backup vs deletion | Synthetic pre-deletion backup | Backup → delete active copy → restore backup into isolated env → compare | Restored backup retains pre-deletion state (expected, documented limitation: deletion is not retroactive to old backups); expired test backups destroyed | Claiming "deleted from all backups" without proof; restored copy able to contact real providers | New script, 3 cycles | `stage11a_phase3_backup_deletion_rehearsal.py`, `backup-retention-results.md` | PASS (honest limitation documented) | — |
| S11A-P3-037 | Account-deletion tombstone content | Post-deletion `User` row | Direct inspection | No email subject/body/calendar content/recipient/OAuth data/proposal payload/real email; opaque anonymised identifier only | Any personal identifier or content-bearing field in the tombstone | Existing: `test_account_deletion_anonymises_and_preserves_tombstones`, re-run + direct inspection | `tombstone-analysis.md` | PASS | — |
| S11A-P3-038 | Generated artefacts | Evidence-pack authoring | Inventory every export/screenshot/report/backup/test-artefact capability | Filenames safe; no committed raw backup/log/trace; CI artefact retention bounded; no user-facing export exists (stated honestly) | Secret or excessive private content in a generated artefact | Documentation review | `generated-artefact-results.md` | PASS | — |

## Dependency, container and test-control isolation

| ID | Surface | Precondition | Action | Expected state/control | Prohibited exposure | Inspection method | Evidence | Result | Defect |
|---|---|---|---|---|---|---|---|---|---|
| S11A-P3-039 | Python/JS dependencies | Current lockfiles | Run `pip-audit` (uv-managed venv) and `pnpm audit` once | Findings classified confirmed-exploitable / not-applicable / requires-upgrade / requires-investigation / tool-unavailable | Fabricated "zero vulnerabilities" claim | `pip-audit`, `pnpm audit` | `dependency-security-results.md` | PASS (see findings, none P0/P1) | — |
| S11A-P3-040 | Container/runtime hardening | `docker-compose.yml` | Review non-root execution, exposed ports, restart policy, volumes | Current posture documented; local-only findings raised where practical | Paid-cloud infrastructure introduced | Manual review | `container-runtime-results.md` | PASS (hardening findings recorded, P2/P3) | — |
| S11A-P3-041 | Test-control isolation | `E2E_TEST_CONTROLS_ENABLED`, `GOOGLE_API_ORIGIN_OVERRIDE`, `DEMO_CLOCK_OVERRIDE` | Attempt production startup with each enabled | Startup refused for every dangerous control | Production-accessible test bypass | Existing: `test_e2e_test_controls.py`, re-run, one attempt per control | Same | PASS | — |

## Repository privacy and cross-user deletion isolation

| ID | Surface | Precondition | Action | Expected state/control | Prohibited exposure | Inspection method | Evidence | Result | Defect |
|---|---|---|---|---|---|---|---|---|---|
| S11A-P3-042 | Repository secret hygiene | Full Phase 3 branch | `detect-secrets`, staged + full-history Gitleaks, private-key detection, real-domain/email scan, `.gitignore`/`.dockerignore` review | Zero genuine findings | Committed secret, real personal data | Repository tooling | `repository-privacy-results.md` | PASS | — |
| S11A-P3-043 | Cross-user deletion isolation | ≥2 synthetic users, deletion in progress for one | 5 cycles per applicable scenario | Deletion of one user never affects another; recovery sweep stays owner-scoped in effect | Cross-user deletion side effect | Existing: `test_stage11a_phase2_cross_user_isolation.py`, re-run 5× (extended from 3×) | Same, extended | PASS | — |
| S11A-P3-044 | Manual owner-operated privacy walkthrough | Real local interface, synthetic data | Full walkthrough per plan §26 | Every subjective entry labelled OWNER OBSERVATION — NOT PARTICIPANT EVIDENCE | Raw browser trace committed | Playwright walkthrough + narrative | `manual-walkthrough.md` | PASS | — |
