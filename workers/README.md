# workers

Background job entry points. Per ADR 0001 D2, no business logic lives here — everything is a thin wrapper around domain services in `apps/api`.

- `scheduler_worker.py` — Stage 8 Phase 2 (ADR 0004 D48): the scheduled-brief worker. Runs `arq` against `lifeflow_api.worker_app.WorkerSettings`; all dispatch/DST/catch-up/generation logic lives in `apps/api/src/lifeflow_api/scheduled_briefs.py`, covered by `apps/api/tests/test_scheduled_briefs*.py`.

  ```bash
  # from anywhere:
  python workers/scheduler_worker.py
  # equivalently, from apps/api:
  uv run arq lifeflow_api.worker_app.WorkerSettings
  ```

  Requires Redis (`docker compose up -d redis`) and a running PostgreSQL. Optional for demo/CI — nothing else in the app depends on it.

- Retention (data-deletion jobs) — still open, tracked for Stage 8/9.
