# Stage 11A Phase 4D — Decision

**Date:** 2026-08-04

## Summary

Phase 4D authorised and executed exactly one controlled, owner-gated,
read-only live connection of disposable Account A through LifeFlow's
connector-consent flow — the first time this project has ever exchanged a
real OAuth token with Google. All 52 acceptance-matrix rows across the
pre-live engineering, the pre-live gate, and the live owner-gated sequence
itself (§12–20) are **Verified**. Four genuine, real-time owner checkpoints
occurred (§12, §14, §15, §20), each confirmed with the exact required
content-free phrase; no credential, account address, code, state, token,
or other sensitive value was ever requested from or supplied by the owner.

## What actually happened, in order

1. Exactly the four approved scopes were granted once, for Account A only,
   via the connector-consent flow (never Google OIDC sign-in). One
   `account.connected` audit event was recorded.
2. Credential storage was verified before any provider call: a `v2`,
   AAD-bound envelope on the active key (`dev-1`), the only
   credential-bearing Google row system-wide, and zero linked
   `SourceItem`s.
3. The content-free read-only smoke sequence (`first_google_readonly_smoke.py
   --phase4d-live`) ran exactly the four authorised calls, each exactly
   once, within the enforced live transport-guard budget — Gmail
   `getProfile`, Gmail `messages.list`, Calendar `calendars.get(primary)`,
   Calendar `events.list(primary)`. All four succeeded. `PROVIDER_WRITES=0`,
   `PERSISTED_PROVIDER_ITEMS=0`.
4. The write kill switch was re-verified with fresh negative controls
   against the live-armed configuration itself (not cached test results).
5. A leakage/residual-data inspection found the audit trail clean, but
   surfaced one real, previously undetected defect (see below) — fixed
   within this phase, not deferred.
6. The owner revoked Google's grant and disconnected the account through
   LifeFlow's real "Disconnect Google" action, which called Google's real
   revoke endpoint and truthfully recorded `revocation_confirmed: true`
   from an objective HTTP 200 — independently corroborated by the owner
   checking Google's own permissions page.
7. A full residual-data sweep and a fresh `preconnection_readiness_check.py`
   run (16/16 PASS) confirmed the environment returned to exactly zero
   stored Google credentials, zero identity bindings, and initiation
   blocked — the same state it was in before this phase's live window
   began.

## Defect found and fixed

**D-4D-01** (see `defect-register.md`): uvicorn's default access logger
bypasses this application's own redaction entirely (`propagate=False` in
uvicorn's own default logging config) and printed the real, single-use
OAuth `code`/`state` query-string values to the owner's terminal during
the connector callback. Non-blocking — both values are single-use and the
callback route already rejects any replay — but real, and fixed within
this phase: a targeted `logging.Filter`
(`UvicornAccessQueryStringRedactor`) now redacts the query string on the
two OAuth callback paths specifically, verified by 9 new tests. This is
the only defect found across the entire phase.

## Addendum — PR #16 merge-integrity review (2026-08-04, same day)

Before merge, a separate integrity-check task re-verified this phase's
evidence against Git and CI rather than trusting the reports above, and
found two further genuine issues — both fixed, neither changing this
decision:

- **D-4D-01 (strengthened):** the original access-log fix matched by
  exact, case-sensitive path only; replaced with a closed sensitive-key
  vocabulary applied to every route's query string, for the reasons in
  `defect-register.md`. 10 further tests (19 total).
- **D-4D-02 (new):** PR #16's required "E2E — outage resilience journeys"
  check failed deterministically (reproduced on a clean rerun) —
  `scripts/resilience-api-env.sh` never set the new
  `GOOGLE_PROVIDER_WRITES_ENABLED`, so the write kill switch intercepted
  the two journeys that specifically need a real write to reach the fake
  server to prove an uncertain outcome is never retried. Fixed by setting
  the flag `true` for that dedicated, disposable test API instance only.

Both fixes are additional commits on the same branch (`49e0d42`,
`463964f`); no existing Phase 4D commit was amended, squashed, or rebased.
The full backend suite was re-run and now totals **1032 passed** (up from
1022, reflecting the 10 new logging tests). See the merge-integrity task's
own final report for the complete re-verification record.

## Verification pyramid

- Full backend suite: **1022 passed** at original evidence time, **1032
  passed** after the merge-integrity corrections above; 91% coverage
  (`logging_setup.py` itself at 100%).
- Ruff format + lint: clean. Mypy: clean.
- Frontend lint + typecheck: clean (no frontend code changed this phase;
  full E2E/build re-run was not required, matching this phase's own
  pre-live gate's "no diff" pattern for contracts regeneration).
- `detect-secrets` re-scan: no new secret hits; `.secrets.baseline`
  timestamp-only diff.
- Direct grep of every new/modified file for the real client
  ID/secret/key values and the account address volunteered in chat: no
  matches.
- Pre-commit: all hooks green once `.secrets.baseline` is staged.

## Boundaries that held throughout

- Zero Google OIDC sign-ins. Zero connections of Account B or any
  personal/business account. Zero additional scopes.
- Zero content imported, synchronised, or persisted as a `SourceItem`.
- Zero Gmail drafts created. Zero Calendar events inserted, updated, or
  deleted.
- Zero automatic sync, worker, or scheduler activity.
- Zero retries of an uncertain operation.
- The soak period was not started. Recruitment remains not authorised.
  Stage 12 remains unstarted. No `stage-11*` tag was created.
- The live provider-write budget was zero, and remained zero.

## Decision

**PASS — READY FOR OWNER DECISION ON SYNTHETIC DATASET POPULATION**

This verdict confirms the first real OAuth connection, credential storage,
read-only provider access, and clean revocation/disconnect all work
exactly as designed, with one real defect found and fixed along the way.
It does **not** itself authorise importing or synchronising real mailbox
or Calendar content, populating Accounts A/B with the approved synthetic
dataset, starting the soak period, provider writes, recruitment, or any
Stage 12 work — each remains a separate, explicit owner decision.

**Next owner decision required — exactly one of:**

- `AUTHORISE POPULATION OF ACCOUNTS A AND B WITH THE APPROVED SYNTHETIC GMAIL AND CALENDAR DATASET`
- `DO NOT AUTHORISE — REAL PROVIDER VALIDATION REMAINS BLOCKED`
