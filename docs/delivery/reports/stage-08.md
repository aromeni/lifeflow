# Stage 8 Completion Report

## Outcome

LifeFlow now adapts to the user transparently, without any hidden profiling.
Stage 8 delivered three independently reviewable phases: **explicit typed
preferences** (Phase 1), an **opt-in scheduled daily brief** with DST-correct,
durable, idempotent worker execution (Phase 2), and **transparent inferred
memory** (Phase 3). A user can configure their brief, have it generated
automatically at their chosen time in their timezone, and see one narrow thing
LifeFlow has *learned* from their own deliberate actions — their email sign-off
— with visible confidence and inspectable evidence, which they can confirm,
edit, dismiss, or delete. Explicit choices always win, and nothing learned can
approve or execute anything: a confirmed sign-off only changes *future* draft
proposals, which the user still previews and approves in full.

## Implemented (Phase 3 — see prior sections of this report for Phases 1–2)

- **Closed, typed memory registry** (`apps/api/src/lifeflow_api/memory_registry.py`): one key, `preferred_email_signoff`; a documented, tested `PROHIBITED_MEMORY_CATEGORIES` deny-list; a closed-vocabulary sign-off extractor; and a deterministic confidence model (`strength × consistency × freshness`, 30-day half-life, Low/Med/High bands). All pure and unit-tested.
- **Durable model + migration**: `MemoryItem` and `MemoryEvidence` (`models.py`, migration `0010`), both cascading from `users`; `(user_id, memory_key)` and `(memory_item_id, source_proposal_id)` unique constraints as the final concurrency/idempotency guards.
- **Recompute lifecycle** (`memory_inference.py`, DB-only, testable without Redis): gathers evidence from the user's own edited-then-approved Gmail drafts, evaluates, upserts one item, and reconciles status (candidate/confirmed/superseded/dismissed/expired) against the explicit preference and dismissal fingerprint. Plus a best-effort `enqueue_recompute` that never raises.
- **Owner-scoped API** (`memory.py`, registered in `main.py`): `GET /memories`, `GET /memories/{id}`, `POST /memories/{id}/confirm`, `PUT /memories/{id}` (edit-and-confirm), `POST /memories/{id}/dismiss`, `DELETE /memories/{id}`, `DELETE /memories`. Confirm/edit write the explicit `preferred_email_signoff` preference through the ordinary registry.
- **Worker + enqueue wiring**: `worker_app.recompute_user_memory` registered on the Phase 2 arq worker; the approve route best-effort-enqueues a recompute on a user-edited Gmail-draft approval when inference is enabled.
- **Visible adaptation** (`proposal_composition.py`, `action_proposal_service.py`, `brief_composition.py`): a confirmed sign-off replaces the composer default "Best" for future drafts, recorded in the proposal `rationale`, part of the payload hash and approval binding — approval, policy, executor, recipients unchanged.
- **Settings Memory section** (`apps/web/src/app/settings/page.tsx`): list with value, confidence label+number, evidence count, last-seen, status badge, explanation; confirm / edit&confirm / dismiss / delete; pause toggle; delete-all; truthfulness copy.
- Two preference keys added (`memory_inference_enabled` default off, `preferred_email_signoff`); contracts regenerated.

## Architecture decisions

ADR 0004 extended with Phase 3 decisions **D51–D58** and a reconstructed
requirements matrix (R1–R8): one safe vertical slice with meeting-duration
deferred (D51); closed registry, sensitive keys fail closed (D52); user-edited
approved drafts as the only evidence, token-only storage (D53); deterministic
confidence (D54); lifecycle/precedence/dismissal/deletion-vs-pause (D55); async
recoverable arq recompute (D56); composition-only adaptation (D57); audit and
deletion-safe events (D58).

## Tests and evidence

| Check | Result | Evidence |
|---|---|---|
| Unit + integration tests (backend) | PASS | `uv run pytest` — 529 passed (51 new for Phase 3) |
| Frontend tests | PASS | `pnpm web:test` — 52 passed (6 new memory tests) |
| Type checking (backend) | PASS | `uv run mypy` — no issues in 71 files |
| Type checking (frontend) | PASS | `pnpm web:typecheck` |
| Lint (backend/frontend) | PASS | `uv run ruff check .`; `pnpm web:lint` |
| Format | PASS | `ruff format`; `pnpm web:format:check` |
| Build | PASS | `pnpm web:build` |
| E2E | PASS | `./scripts/e2e.sh` — 4 passed |
| Evals (brief, actions) | PASS | 0 grounding/injection violations, deterministic |
| Real-Redis integration | PASS | `test_memory_queue.py`, `test_scheduled_briefs_queue.py` |
| Migration round-trip | PASS | `alembic upgrade head` → `downgrade 0009` → `upgrade head` |
| Contract freshness | PASS | `./scripts/generate-contracts.sh` — memory schemas present |
| Secret scanning | PASS | pre-commit, detect-secrets, gitleaks full-history (0 leaks) |
| `.env.example` / `git diff --check` | PASS | `test_env_example_placeholders.py`; clean |

## Manual verification

A live smoke test with real Postgres, real Redis, and a real `arq` worker
process confirmed the worker dequeues `recompute_user_memory` and produces a
`candidate` item (value "Kind regards", evidence 3, confidence 0.750/High,
suggest-only) with only the user id on the queue — no draft content in Redis,
logs, or the memory tables. Recorded in
[stage-08-phase-3-manual-checklist.md](../stage-08-phase-3-manual-checklist.md).

## Known limitations

- One memory type (`preferred_email_signoff`); `preferred_meeting_duration_minutes` is deliberately deferred (D51) — no safe missing-duration composition point exists under Stage 7's fail-closed calendar extraction.
- Real-LLM evaluation of any memory-influenced output remains gated behind the Stage 10 provider-metrics work (ADR 0002), as for the rest of the pipeline.

*(Focused-review closure, 2026-07-22: effective expiry is now complete — a candidate decays with time alone and is expired both on every authenticated read and by a daily maintenance cron, so it can never be shown as active indefinitely. Confirmation is proven atomic across the request transaction. The production approval-to-inference trigger is proven end-to-end by an automated test and a full HTTP smoke.)*

## Files changed

- **Backend new**: `memory_registry.py`, `memory_inference.py`, `memory.py`, migration `0010_inferred_memory.py`, tests `test_memory_registry/inference/api/adaptation/queue.py`.
- **Backend modified**: `models.py`, `repositories.py`, `preferences.py`, `worker_app.py`, `action_proposals.py`, `action_proposal_service.py`, `proposal_composition.py`, `brief_composition.py`, `main.py`.
- **Frontend**: `settings/page.tsx`, `settings/page.test.tsx`, `lib/types.ts`, regenerated `packages/contracts/*`.
- **Docs**: ADR 0004, assumptions-and-decisions, stage-plan, threat-model, README, this report, Phase 3 manual checklist, metrics.

## Run instructions

```bash
docker compose up -d db redis --wait
cd apps/api && uv run alembic upgrade head
uv run uvicorn --app-dir src lifeflow_api.main:app --reload --port 8010
PYTHONPATH=src uv run arq lifeflow_api.worker_app.WorkerSettings   # worker (memory recompute + scheduled brief)
pnpm web:dev   # Settings → Learned preferences
```

## Recommended commit message

`feat(stage-8): add transparent inferred memory (preferred_email_signoff)`

## Gate

Stage 8 (all three phases) is complete and fully verified. All three phases
passed the committed-state closure review as one integrated milestone, and
Stage 8 has been **approved for remote completion**. The Phase 3 commit is
`466de179a7af1fe6410ee4e4f661402bec5b8925`. Stage 9 (privacy, audit UX,
resilience) has not begun; all remaining work belongs to Stage 9.
