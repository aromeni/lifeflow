# Stage 11A Phase 2 — Worker and Scheduler Results

**Status:** Complete · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) (S11A-P2-005 to 012)

## Web-process restart (S11A-P2-005)

| Screen | Result | Evidence |
|---|---|---|
| Today / Approvals / Connections / Audit History / Settings | PASS — safe error/unavailable state, no blank or false-success state, reload recovers, pending approvals durable, no action executed merely by reconnecting, no duplicate mutation from hydration/refetch | Manual owner walkthrough (`manual-walkthrough.md`) driving `pnpm dev` restart against each screen; `stage10-outage-notice-fixture.spec.ts`/`stage10-uncertain-execution-fixture.spec.ts` re-run for the notice-rendering half of this claim |

## Worker crash (S11A-P2-006 to 011)

| Scenario | Repetitions | Result | Evidence |
|---|---|---|---|
| Crash before claiming a job | 3 | PASS — job remains claimable, no loss (no worker started at all is the strictest form of this case) | `journey-c-worker-outage-recovery.spec.ts` re-run 3× |
| Two competing workers | 3 | PASS — atomic `claim_operation` UPDATE prevents duplicate ownership, operation completes exactly once | `journey-c-worker-outage-recovery.spec.ts` (spawns 2 real worker processes) re-run 3× |
| Crash after durable pending execution / after provider write | 10 per action type | PASS — uncertain, never replayed (shares the process-agnostic durability checkpoint proven in api-restart-results.md) | `test_stage11a_phase2_uncertain_write_repeatability.py` |
| Crash during deletion batching | 3 | PASS — resumes from `resume_cursor_json`, not from scratch | `test_stage11a_phase1_reset_repeatability.py` (10 full cycles through the real worker body) re-run 3× this phase |
| Crash during scheduled brief generation | 3 | PASS — no duplicate brief (`Brief` unique `(user_id, local_brief_date)` constraint + deterministic job id, ADR 0004 D48/D49) | `test_scheduled_briefs_enqueue_resilience.py` re-run 3× |
| Worker restart drains backlog | 3 | PASS — no job silently lost | `test_execution_recovery_sweep.py` re-run 3× |

## Scheduler interruption (S11A-P2-012)

PASS. The arq cron loop's own in-progress-key TTL self-heal (`worker.py::_start_job`, `in_progress_key_prefix + job_id` where `job_id = f'{name}:{next_run_ms}'`) was independently re-read and confirmed against the installed `arq==0.28.0` source this phase, byte-for-byte consistent with `docs/delivery/runbooks/worker-recovery.md`'s existing description — not re-tested as a new unit test, since it is third-party library behaviour LifeFlow does not own (see defect-register.md's non-defects section for the full reasoning). LifeFlow's own duplicate-prevention layer on top of it (DB unique constraint + deterministic job id) is application code and was re-run 3× each: `test_scheduled_briefs_enqueue_resilience.py`, `test_deletion_engine_enqueue_resilience.py`, `test_execution_recovery_sweep.py`.

## Concurrency evidence

`journey-c-worker-outage-recovery.spec.ts`'s two-competing-workers case is the concurrency proof this section requires: two real, independently-spawned worker processes racing to claim the same durable deletion operation, verified via the atomic `UPDATE ... WHERE state='pending' RETURNING id` in `deletion.py::claim_operation` — the loser always receives `None`, confirmed by the operation completing exactly once across all 3 re-runs.
