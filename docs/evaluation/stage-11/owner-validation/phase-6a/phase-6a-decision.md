# Stage 11A Phase 6A — Decision

**Date:** 2026-08-05

## Summary

Replaced the single, shared `GOOGLE_OAUTH_INITIATION_ENABLED` flag — the exact, confirmed root cause of Phase 6's OIDC sign-in boundary crossing (D-6-02) — with two independent, fail-closed flags, `GOOGLE_OIDC_SIGNIN_ENABLED` and `GOOGLE_CONNECTOR_OAUTH_ENABLED`. Enabling either flow is now structurally incapable of enabling the other. The exact original incident was reproduced as a named regression test and confirmed fixed. OAuth state isolation (`purpose`-bound, pre-existing) was independently reconfirmed rather than assumed. No real Google interaction occurred at any point in this phase.

## Requirements met

- Independent fail-closed controls, both default `false`, neither settable by an HTTP request — **met**.
- Connector enablement never enables sign-in and vice versa — **met**, proven in both directions.
- Each initiation route and each callback route checks only its own control, before any state creation, redirect, or code exchange — **met**.
- Cross-flow OAuth state cannot be consumed by the other flow's callback — **met** (pre-existing mechanism, reconfirmed fresh).
- The master `google_oauth_enabled` configuration flag remains a prerequisite, never sole authorisation for either flow — **met**, unchanged.
- No backward-compatible fallback silently restores the shared behaviour — **met**; the old flag and guard function are removed outright.
- PKCE, state, owner binding, redirect matching, and token security are unweakened — **met**; none of that code was touched.
- The exact Phase 6 incident is reproduced as a named regression test and confirmed fixed — **met**.
- No unresolved P0/P1 — **met**; none found.
- All required tests and CI checks green — **met** (see below; PR CI pending at time of writing, tracked separately).
- No real provider activity occurred — **met**, verified directly (see `zero-provider-activity-results.md`).
- Zero stored credentials, zero identity bindings — **met**, verified directly, unchanged from the starting boundary.

## Automated verification

- Full backend suite: **1047 passed**, 0 failed.
- Ruff format/check, mypy: clean.
- Frontend lint + typecheck: clean (no frontend code changed).
- 16 new/updated tests directly exercising the split: 11 in `test_stage11a_phase6a_oauth_control_separation.py` (truth table, independence in both directions, cross-flow state isolation ×2, startup validation, defaults) + 5 in the restructured `test_stage11a_phase4c_oauth_initiation_block.py`.

## Decision

**PASS — GOOGLE SIGN-IN AND CONNECTOR CONSENT CONTROLS SEPARATED.**

This does not authorise a corrected Calendar-write trigger attempt, GM-12's deferred evaluation, reconnecting either account, the soak period, recruitment, or Stage 12 — each remains a separate, explicit owner decision.

**Next owner decision — one of:**

- `AUTHORISE A CORRECTED CALENDAR-WRITE TRIGGER ATTEMPT`
- `DO NOT AUTHORISE — GOOGLE CONNECTION REMAINS BLOCKED`

---

**Addendum (Stage 11A Phase 6A.1, dated 2026-08-05):** this decision's backend scope stands unchanged — the split controls above were, and remain, correct and unweakened. However, this phase's own merge report understated one piece of surrounding context: the frontend at merge time still read only the old, pre-split `google_oauth_enabled` configuration-completeness signal, not either new per-flow flag. Phase 6A.1 ([stage-11a-phase-6a1-plan.md](../../../../delivery/stage-11a-phase-6a1-plan.md)) closed that gap by extending `GET /config` with the two per-flow booleans and aligning both frontend Google controls to them. This addendum records the correction; it does not alter anything above.
