# Stage 9 Delivery Phase 1 Completion Report — Privacy & Connections Control Centre

**Branch:** `stage-9-privacy-hardening` (base `c5b60b1`). **Date:** 2026-07-22.
**Scope:** the read-only, non-destructive Privacy & Connections Control Centre.
Remotely preserved at `49f121a`. Delivery Phase 2 was subsequently remotely
finalised at `fdb4636`; this report remains the Phase 1 boundary record.

## Outcome

One consolidated, truthful privacy surface. Users can see which provider
accounts are connected, exactly what access they granted (human-labelled),
how fresh the synced evidence is, owner-scoped counts of everything stored, and
the provisional retention defaults — and understand disconnect vs. delete-data
vs. delete-memory vs. delete-account as four distinct operations. The surface
adds no deletion, retention enforcement, audit timeline, or rate limiting
(later Delivery Phases).

## What shipped

- **Backend:** `GET /privacy/summary` (`apps/api/src/lifeflow_api/privacy.py`) —
  connection summary (status, granted scopes with labels, freshness band reusing
  `evidence_freshness._freshness_band`, ever-synced, can-disconnect/reconnect),
  owner-scoped inventory counts for all 12 categories (executions via the
  proposal join), and retention classes (`enforced=False`). Wired in `main.py`.
- **Config:** nine validated retention-day settings + `trusted_proxy_cidrs` in
  `config.Settings` (positive ints; read from app state, not the cached global).
- **Frontend:** the `/connections` route expanded into the canonical "Privacy &
  Connections" Control Centre (`apps/web/src/app/connections/page.tsx`) with the
  seven required sections and four distinct data controls; disconnect/reconnect/
  sync reuse the existing routes unchanged.
- **Contracts** regenerated; `types.ts` aliases added.
- **Tests:** 15 backend (`test_privacy_api.py`) + 14 frontend
  (`connections/page.test.tsx`).

## Policy decisions recorded (ADR 0005)

Account deletion = anonymise-and-minimise with content-free tombstones (D61);
retention as validated env settings, not a table, with the provisional defaults
(D62); derived-data deletion rules (D63); rate-limiting keying + trusted-proxy
architecture, thresholds deferred (D64); the five-phase Delivery split and the
Planning-Gate vs. Delivery-Phase terminology (D59/D60). Also recorded in
`assumptions-and-decisions.md`, `stage-plan.md`, `threat-model.md`, `README.md`,
and the user guide `docs/product/privacy-centre.md`.

## Verification

All gates run against this working tree:

| Gate | Result |
|---|---|
| Backend pytest | 551 passed, 6 skipped (real-Redis, run separately: 21 passed) — total 557 incl. 15 new |
| mypy strict | clean (72 files) |
| Ruff check / format | clean / 139 files formatted |
| Frontend vitest | 61 passed (14 new) |
| ESLint / tsc / build | pass / pass / pass |
| Playwright | **4 passed** (3 consecutive clean runs) after the focused E2E remediation below |
| Evals (det, actions) | pass — precision 1.00, recall 0.94, 0 unsafe/injection/grounding |
| Alembic heads | single head `0010` (no new migration) |
| Contracts | regenerate idempotently; only the intended privacy additions |
| detect-secrets / gitleaks (19 commits) | clean |
| .env.example validation / git diff --check | 7 passed / clean |
| pre-commit (all hooks) | all pass |
| Manual API smoke | 7/7 (summary opens; counts match DB; retention not-enforced; no destructive route; refresh triggers no sync; no token/cursor/revision; imported data retained) |

## Safety review

No token/ciphertext, sync cursor, `authorisation_revision`, provider
message/event id, proposal payload/hash, or audit `safe_metadata` in the
response (sentinel-leak test). Owner-scoped throughout (isolation test).
Redis-independent (unreachable-Redis test). Never triggers a sync. No new OAuth
scopes. No destructive mutation beyond the existing disconnect.

## Focused completion remediation (E2E determinism + disconnect proof)

**E2E root cause (durable knowledge).** The `demo-brief` journey drove the shared
`dev-login {}` **singleton** demo user (via the "Try demo" button). Separate
Playwright spec files run on parallel workers, and `demo-approvals` drives the
same singleton — so one spec's brief generation raced the other's proposal
execution on the same DB rows (the failure snapshot showed `version 21`), and
the brief occasionally rendered before its "Waiting for" follow-ups were
present. It was **not** demo date logic: a fresh demo import is deterministic at
every calendar date/time (verified by a 1392-instant sweep — 400 days × 24
hours, zero empty-follow-up cases — and the fingerprint already includes
`sent_at`, so re-import re-anchors dates via the update path). `connections.spec`
never flaked because it already used unique per-test users.

**Deterministic correction.** `demo-brief.spec` now uses an **isolated, unique
demo user** per test (a unique `dev-login` email + API `demo/start`, then the
onboarding→today→generate UI), mirroring the pattern `demo-approvals.spec`
already used. No assertion was loosened, skipped, or quarantined. Proven by
**three consecutive full E2E runs, all 4 tests passing**. Regression tests added
in `test_ingestion.py`: `test_reimport_at_a_new_anchor_moves_occurred_at_forward`
(demo data re-anchors on re-import — guards against a future fingerprint change
re-freezing dates) and `test_demo_yields_a_waiting_for_signal_regardless_of_calendar_date`
(a far-future anchor still yields a follow-up), which would have caught genuine
date drift.

**Successful disconnect proof.** Backend integration test
`test_successful_disconnect_clears_tokens_and_retains_all_data` and a live API
smoke both exercise a synthetic connected Google account through the normal
`/connected-accounts/google/disconnect` route: **active + tokens present → 204 →
disconnected + both encrypted tokens NULL**, status flipped, `can_disconnect`
false / `can_reconnect` true, every imported and derived count unchanged
(sources/signals/briefs/proposals/executions/runs/prefs/memory), and reopening
the surface triggers no sync. Gmail/Calendar provider content is never touched
(the route only clears local tokens; the executor is draft/create-only). The
real Google-connected account was not used.

## Delivery Phase 2 boundaries (not built in this phase)

Imported-data deletion (durable `DataDeletionOperation` engine, preview, typed
confirmation), retention enforcement job, and account deletion
(anonymise-and-minimise) — all per ADR 0005 D61–D63. Audit history is Phase 3,
rate limiting Phase 4, resilience/telemetry Phase 5.

Delivery Phase 2 was subsequently completed at `fdb4636`. Delivery Phases 3–5
have not begun; Stage 9 is not complete, has no `stage-9-complete` tag, and has
not been merged to `main`.
