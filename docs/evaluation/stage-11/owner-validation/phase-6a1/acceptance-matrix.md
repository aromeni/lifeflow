# Stage 11A Phase 6A.1 — Acceptance Matrix

**Date:** 2026-08-05

| # | Item | Result |
|---|---|---|
| P6A1-001 | Local `main` = `origin/main` = starting `HEAD` = `c7f1254f476ab70ebf52f8deba1ca527cfa6efad` | **Verified** |
| P6A1-002 | Phase 6A merged; both OAuth controls independent | **Verified** — 19/19 readiness checks PASS at the starting boundary |
| P6A1-003 | Both Google accounts disconnected; 0 stored credentials; 0 identity bindings | **Verified** |
| P6A1-004 | Working tree clean; no `stage-11*` tag | **Verified** |
| P6A1-005 | Frontend discrepancy identified and documented before editing | **Verified** — see `existing-frontend-behaviour.md` |
| P6A1-006 | `/config` exposes exactly three closed booleans, no secret material | **Verified** — schema and 5 backend tests |
| P6A1-007 | Master `google_provider_configured` never by itself implies either flow authorised | **Verified** — each per-flow boolean folds in provider-configuredness server-side; `test_config_never_reports_a_flow_enabled_when_provider_is_unconfigured` |
| P6A1-008 | Landing page sign-in control follows only the sign-in capability | **Verified** — `page.tsx`, 5 relevant unit tests |
| P6A1-009 | Connections page connector control follows only the connector capability, safe text when disabled | **Verified** — `connections/page.tsx`, 6 relevant unit tests |
| P6A1-010 | Frontend capability-load failure fails closed on both pages | **Verified** — dedicated tests on both pages |
| P6A1-011 | Backend guards unchanged; still authoritative | **Verified** — no route/guard files touched; full Phase 6A suite re-run clean |
| P6A1-012 | Frontend 5-scenario truth table (both disabled / sign-in only / connector only / both enabled / provider unconfigured) | **Verified** — see `truth-table-results.md` |
| P6A1-013 | Regression coverage: independence both directions, fail-closed, no secret leakage, exact Phase 6 incident configuration reproduced on both pages | **Verified** — 4 new backend tests, 6 new landing-page tests, 6 new connections-page tests |
| P6A1-014 | Accessibility of disabled-state wording/controls | **Verified** — `e2e-design/accessibility.spec.ts` "Connections has no serious accessibility violations" passes unchanged |
| P6A1-015 | Evidence pack created; Phase 6A decision addended, not rewritten | **Verified** — this pack; addendum in `phase-6a-decision.md` |
| P6A1-016 | Zero provider activity throughout | **Verified** — see `zero-provider-activity-results.md` |
| P6A1-017 | Full verification gate run | **Verified** — see `automated-verification-results.md` |
| P6A1-018 | PR opened against `main`, not merged, not tagged, no Google account connected | **Verified** — PR #19 |
