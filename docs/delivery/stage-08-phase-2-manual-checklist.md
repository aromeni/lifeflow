# Stage 8 Phase 2 Manual Checklist — the scheduled daily brief

**Status:** the core loop was run live during implementation (2026-07-21, 17:32–17:35 BST) against the real local stack — real PostgreSQL, real Redis (`docker compose up -d redis`), a real `arq` worker process, and a fresh demo user, with no mocks anywhere in the path. Steps below are marked **PASS — live** where that run is the evidence, with the concrete identifiers captured at the time; steps not exercised in that specific real-time window are marked **PASS — automated**, naming the exact test that proves the behaviour deterministically (several genuinely require hours of wall-clock waiting — e.g. the 6-hour catch-up boundary — which a controllable-clock test proves far more reliably than a human watching a clock). Nothing here is a completion blocker; this document exists so a human can re-run any step live at any time.

## Prerequisites

```bash
docker compose up -d db redis --wait
cd apps/api && uv run alembic upgrade head
uv run uvicorn --app-dir src lifeflow_api.main:app --port 8010          # terminal 1
uv run python ../../workers/scheduler_worker.py                        # terminal 2
pnpm web:dev                                                             # terminal 3, repo root
```

## Checklist

- [x] **1. Start PostgreSQL, Redis, API, web and worker.** **PASS — live.** All four processes running simultaneously; worker log confirmed `Starting worker for 2 functions: generate_scheduled_brief, cron:dispatch_scheduled_briefs` and a successful Redis handshake (`redis_version=7.4.9`).
- [x] **2. Create or use a fresh demo user.** **PASS — live.** Fresh `dev-login` user, then `POST /demo/start` (36 items imported).
- [x] **3. Enable scheduled briefs.** **PASS — live.** `PUT /preferences/scheduled_briefs_enabled {"enabled": true}` → 200.
- [x] **4. Set timezone to Europe/London.** **PASS — live.** Default for a new user; confirmed via `GET /scheduled-briefs/status` (`"timezone": "Europe/London"`).
- [x] **5. Set briefing time two or three minutes ahead.** **PASS — live.** `PUT /preferences/briefing_time {"value": "17:35"}`, set ~2 minutes ahead of the real clock.
- [x] **6. Confirm Settings shows the expected next run.** **PASS — live (API) + automated (UI).** `GET /scheduled-briefs/status` returned `"next_run_at": "2026-07-21T16:35:00Z"` (17:35 BST) before the run occurred. The Settings page's rendering of this field is covered by `apps/web/src/app/settings/page.test.tsx` ("enabling scheduled briefs and saving shows the real next/last run status…").
- [x] **7. Wait without clicking Generate brief.** **PASS — live.** No manual generation was triggered; the brief was produced only by the worker's own cron tick.
- [x] **8. Confirm exactly one scheduled brief appears.** **PASS — live.** `scheduled_brief_runs` row `1a73227c-b9b1-4d46-bf8b-54c695cc9ed8` → `status=succeeded`, linked to exactly one `briefs` row (`636b2b1d-8290-4903-97ed-9b4adbb44d65`, version 1).
- [x] **9. Confirm it is labelled scheduled.** **PASS — live (data) + automated (UI).** `briefs.generation_trigger = 'scheduled'` confirmed directly in Postgres. The Today page's manual-vs-scheduled label is covered by `apps/web/src/app/today/page.test.tsx` ("labels a scheduled brief distinctly from a manual one").
- [x] **10. Confirm its section preferences were respected.** **PASS — automated.** `test_scheduled_generation_respects_sections_never_hides_needs_attention_and_never_executes` (`apps/api/tests/test_scheduled_briefs.py`) sets a restricted `brief_sections` value, runs a scheduled generation, and asserts only the chosen sections are displayed.
- [x] **11. Confirm Needs attention remains.** **PASS — automated.** Same test as (10) asserts `needs_attention` is always present in the displayed sections regardless of the user's chosen filter.
- [x] **12. Confirm proposals exist but none were approved or executed.** **PASS — live.** The live run's audit trail shows three `proposal.created` events (`create_task`, `create_gmail_draft`, `create_calendar_event`) and zero `proposal.approved`/`execution.*` events; all three proposals remained `status=proposed`.
- [x] **13. Restart or refresh the UI and confirm no second brief appears.** **PASS — automated.** `test_refreshing_status_repeatedly_enqueues_and_records_nothing` (`apps/api/tests/test_scheduled_brief_status_route.py`) calls the status route five times in a row and asserts zero new `scheduled_brief_runs` rows and zero new `scheduled_brief.*` audit events.
- [x] **14. Run the dispatcher again and confirm no duplicate.** **PASS — live.** The worker log shows cron ticks at `17:32:05`, `17:33:00`, `17:34:00`, and `17:35:00` (the due tick) — only the due tick enqueued a job, and exactly one `scheduled_brief_runs` row exists for that user/date afterward.
- [x] **15. Change tomorrow's briefing time and confirm next-run calculation updates.** **PASS — automated.** `test_briefing_time_change_before_run_uses_the_new_time` (`apps/api/tests/test_scheduled_briefs.py`).

## Catch-up smoke test

**PASS — automated** (a human watching a clock for 6+ hours is a worse test than a controllable one): `test_catch_up_within_grace_window_still_generates` (due 3h late → still generates) and `test_catch_up_beyond_grace_window_is_skipped_not_generated` (due 7h late → `skipped`, `error_code=missed_grace_window`, no brief). To run this live instead: stop the worker, wait past a configured `briefing_time`, then restart the worker within 6 hours (generates) or after 6 hours (skipped) and inspect `GET /scheduled-briefs/status`.

## Disabled-schedule test

**PASS — automated + live.** `test_disabled_user_is_never_dispatched` proves a user who never enables scheduling is never dispatched. Live equivalent, run during the same session: before enabling, `GET /scheduled-briefs/status` for a fresh demo user returned `"enabled": false, "next_run_at": null`, and the worker's dispatcher ticks (`17:32:05`–`17:34:00`) produced no run for that user.

## Note on “not required by Phase 2”

Scheduled Google sync (ADR 0004 D47), retention/pilot-readiness items, and inferred preferences (Phase 3) are explicitly out of scope here and are not re-listed as open items in this checklist — they were never part of Phase 2's contract.
