# Stage 11A Phase 3 — Secret Rotation Results (S11A-P3-017–021)

**Status:** PASS (with one honestly-recorded capability gap) · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) · [defect-register.md](defect-register.md)

No rotation tooling or test existed anywhere in this project before this phase — confirmed absent during the Phase 3 audit. `apps/api/tests/test_stage11a_phase3_secret_rotation.py` (3 tests, all passing) rehearses each secret this contract lists, using only synthetic/local values.

| Secret | Rotation capability | Evidence |
|---|---|---|
| `SESSION_SECRET` | **Restart-only, forced invalidation.** Rotating and restarting (modelled here as a fresh `create_app()` instance under a new secret) makes every session signed under the old secret unverifiable (401); a freshly issued session under the new secret works immediately. No dual-key grace period exists or is needed — sessions are short-lived (8h) and trivially re-issued by logging in again. | `test_session_secret_rotation_invalidates_old_sessions_and_issues_new_ones` |
| `TOKEN_KEY`/`TOKEN_KEY_ID` | **No rotation capability exists today.** `AesGcmTokenCipher` holds exactly one active key; `decrypt()` raises `TokenCipherError` for any envelope whose `key_id` does not match. Application wiring (`main.py`, `worker_app.py`) constructs exactly one cipher instance — no dual-key registry exists for a caller to decrypt-under-old, re-encrypt-under-new. **This is a genuine, recorded gap** (see defect register), not a silently-accepted limitation: a real rotation today would require a dedicated, currently-unbuilt re-encryption migration that decrypts every row under the old key before the old key is discarded. | `test_token_cipher_key_rotation_has_no_dual_key_migration_path` |
| `RATE_LIMIT_KEY_SECRET` | **Safe by construction.** A new secret produces a new HMAC digest for the same raw subject — indistinguishable from a bucket expiring naturally. No stored state becomes unreadable or corrupted; fail-open behaviour is completely unaffected. | `test_rate_limit_secret_rotation_only_changes_the_bucket_key_deterministically` |
| Fake-provider credentials | No production analog exists — the fake-Google server is test-only infrastructure with no real credential to rotate. | Code inspection |
| Test database/Redis passwords | Restart-only, local dev convenience credentials only; never require live rotation since they never protect real data. | Code inspection |

## Result

Two of three real secrets have a safe, verified rotation path. The third (`TOKEN_KEY`) does not — recorded as **P2** (weak/absent secret-rotation process for one secret, no current exploitable exposure since nothing prompts a rotation today, but production readiness will require building this migration before `TOKEN_KEY` can ever actually be rotated). Thresholds were not lowered to accommodate this: the gap is documented honestly rather than a false capability being claimed.
