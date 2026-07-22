# Stage 8 Phase 3 — manual verification checklist (inferred memory)

**Date:** 2026-07-22 · **Branch:** `stage-8-memory` · **ADR:** 0004 D51–D58

This records the manual/live verification that complements the automated suite.
The deterministic memory lifecycle (candidate → confirm → override → dismiss →
decay → delete) is proven primarily by the integration suite with a
controllable clock (`test_memory_inference.py`), the owner-scoped HTTP API by
`test_memory_api.py` (real auth + CSRF via `dev_client`), the enqueue payload
by real Redis (`test_memory_queue.py`), and the Settings UI by Vitest +
Playwright. The one path no automated test covers — **a running `arq` worker
process dequeuing and executing `recompute_user_memory`** — was verified live
below.

## Environment

- PostgreSQL 16 (`docker compose up -d db`), Redis 7 (`docker compose up -d redis`).
- Worker: `PYTHONPATH=src uv run arq lifeflow_api.worker_app.WorkerSettings`.
  Startup log confirmed three registered functions:
  `generate_scheduled_brief, recompute_user_memory, cron:dispatch_scheduled_briefs`.

## Live worker-consumption smoke (real Postgres + real Redis + real arq worker)

Seeded a fresh demo user with inference **enabled** and three
edited-then-approved `create_gmail_draft` proposals all ending "Kind regards"
(no other content), then best-effort-enqueued a recompute onto the real Redis.

| Step | Observed | Result |
|---|---|---|
| Enqueue `recompute_user_memory(user_id)` to real Redis | returned `True`; job argument was the bare user-id string only (redacted here) | ✅ |
| Worker log shows the job dispatched and completed | `…:recompute_user_memory('17f5…')  ●` (success), 0.07s | ✅ |
| Worker produced exactly one memory item | `key=preferred_email_signoff status=candidate` | ✅ |
| Inferred value | `{"value": "Kind regards"}` — the normalised token, no body stored | ✅ |
| Evidence count | `3` | ✅ |
| Confidence | `0.750` → band **High** (deterministic, not an LLM score) | ✅ |
| Suggest-only + not overridden | `application_mode=suggest_only`, `overridden_by_explicit=False` | ✅ |
| Redis payload minimisation | job carries only the user id — no draft body, recipient, or token | ✅ |

No email body, recipient, subject, or token appeared in the Redis payload, the
worker log, or the memory tables — only the short sign-off token and a reason
code, exactly as ADR 0004 D53/D56 require.

## Full production-trigger smoke (real API + real worker, no manual enqueue)

Added at focused-review request: drive the *normal product path* end to end and
prove the **approval route itself** — not a manual `enqueue_recompute` call —
triggers inference. One prior edited+approved(executed) draft was seeded as
evidence #1; the rest is pure HTTP against the running API, with a real `arq`
worker consuming the approval-triggered job.

| Step | Action (HTTP unless noted) | Result |
|---|---|---|
| 1 | `POST /auth/dev-login` (fresh demo user) | ✅ |
| 2 | Seed one prior edited+approved(executed) "Kind regards" draft (evidence #1) | ✅ |
| 3 | `PUT /preferences/memory_inference_enabled {enabled:true}` | ✅ |
| 4 | `POST /demo/start` + `POST /briefs/generate` | ✅ |
| 5 | `PATCH /action-proposals/{id}` — edit the draft's sign-off (sets `user_edited_at`) | ✅ v2 |
| 6 | `POST /action-proposals/{id}/approve` — **no manual enqueue** | ✅ `status=approved`, `execution=None` |
| 7 | Real worker log shows `…:recompute_user_memory('bf73…')  ●` (success) | ✅ |
| 8 | `GET /memories` → exactly one candidate | ✅ `count=1` |
| 9 | Candidate value / evidence / confidence | ✅ `Kind regards`, evidence **2**, confidence **0.500** → Medium |
| 10 | No proposal auto-executed by approval | ✅ 0 proposals have an execution record |

Also proved by automated tests alongside this smoke:
- **Approval path enqueues an identifiers-only job** — `test_memory_queue.py::test_real_approval_path_enqueues_an_identifiers_only_recompute` (drives edit+approve through the real routes, asserts one `recompute_user_memory` job carrying only the user id, and that approval executed nothing).
- **Unedited approved draft → no evidence** — `test_only_user_edited_approved_gmail_drafts_are_evidence`.
- **Edited-but-unapproved draft → no evidence** — `test_edited_but_unapproved_draft_creates_no_evidence`.
- **Received email with the same sign-off → no evidence** — `test_inbound_email_text_alone_creates_no_preference`.
- **Repeated processing idempotent** — `test_recompute_is_idempotent`, `test_second_independent_recompute_never_duplicates`.

## Effective expiry (focused-review addition)

Expiry no longer waits for a later recompute. A candidate now decays with time
alone and is expired both **on read** (every `GET /memories`, like the
proposals list expires due proposals) and by a **daily maintenance cron**
(`expire_stale_memory`, 03:00 UTC) so it never depends on the user opening
Settings. The worker registers four functions now:
`generate_scheduled_brief, recompute_user_memory, cron:dispatch_scheduled_briefs, cron:expire_stale_memory`.

| Check | Evidence |
|---|---|
| Candidate active before threshold, expires with time alone | `test_candidate_stays_active_then_expires_with_time_alone` |
| Read-time expiry via API, audited once across reads | `test_reading_expires_a_decayed_candidate_and_audits_once` |
| Cross-user daily maintenance, idempotent | `test_cross_user_maintenance_expires_all_decayed_candidates` |
| Confirmed explicit preference never decays | `test_confirmed_preference_never_decays` |
| Effective confidence decays 30-day half-life, bounded | `test_effective_confidence_decays_with_time_only` |

## Atomic confirmation (focused-review addition)

Confirm and edit-and-confirm run inside the single request transaction
(ownership+version check → explicit preference write → status transition →
audit; commit at the request boundary, rollback on any error).

| Check | Evidence |
|---|---|
| Failure after preference write, before status update → full rollback | `test_confirm_rolls_back_entirely_if_it_fails_after_the_preference_write` |
| Failure after status update, before audit → full rollback | `test_confirm_rolls_back_entirely_if_the_memory_audit_fails` |
| Two confirmations cannot create contradictory preferences; retry → 409 | `test_two_confirmations_cannot_create_contradictory_preferences` |
| Stale version → 409 | `test_stale_version_is_409` |
| Edit-and-confirm invalid sign-off → 422 | `test_edit_rejects_an_unsafe_signoff` |

## Covered by automated evidence (not re-run by hand)

- **Confirm → explicit preference → adaptation**: `test_memory_api.py::test_confirm_writes_explicit_preference_and_marks_confirmed` (confirm writes the explicit `preferred_email_signoff`, `applied=true`, `memory.confirmed` + `preference.updated` audited) and `test_memory_adaptation.py::test_confirmed_signoff_adapts_future_draft_and_approval_still_required` (a future draft uses the confirmed sign-off, remains `proposed` — approval still mandatory). The adapted body is part of the payload hash (`test_adapted_body_changes_the_payload_hash`).
- **Explicit precedence / override visible**: `test_memory_inference.py::test_explicit_preference_supersedes_candidate` (candidate → `superseded`, `overridden_by_explicit=True`).
- **Dismiss sticky, materially-new-evidence reconsideration**: `test_dismissed_candidate_does_not_reappear_from_same_evidence`, `test_materially_new_evidence_reconsiders_a_dismissed_candidate`.
- **Pause creates no candidate; delete-all empties the list**: `test_paused_inference_creates_no_candidate`; `test_memory_api.py::test_delete_all_removes_every_memory`.
- **Received email text alone creates no preference**: `test_inbound_email_text_alone_creates_no_preference`.
- **Redis-unavailable isolation**: `test_memory_queue.py::test_enqueue_returns_false_when_redis_unavailable_and_never_raises` — the approval that triggers a recompute can never be broken by a down queue.
- **Ownership isolation**: `test_memory_api.py::test_memories_are_isolated_per_user` — another user gets 404, never leaked ownership.
- **UI**: Playwright E2E green (4/4) + `settings/page.test.tsx` memory tests (candidate render, confirm/edit/dismiss/delete/pause/delete-all, truthfulness copy).

## Result

Live worker consumption confirmed; all complementary paths green in the
automated suite. No user content entered Redis, logs, or the memory tables.
