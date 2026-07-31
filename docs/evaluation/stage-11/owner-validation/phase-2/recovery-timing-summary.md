# Stage 11A Phase 2 — Recovery Timing Summary

**Status:** Complete · **Date:** 2026-07-31

**These are descriptive local-machine measurements only — not a production SLA, not an availability claim, not a certification.** Measured on one developer laptop (macOS, Docker Desktop, dev-compose Postgres/Redis), single-threaded, with no concurrent production load. Real production recovery times depend entirely on the eventual hosting environment (Stage 12+), which does not exist yet.

| Scenario | Median | Slowest observed | Repetitions | Environment | Limitation |
|---|---|---|---|---|---|
| API cold start (uvicorn boot to `/health` 200) | 1.67s | 2.26s | 3 | Local `uv run uvicorn`, no reverse proxy | Includes Python/dependency import time, not representative of a warm production process pool |
| API "rollback" (deliberately-broken config → confirmed failure → restored) | 2.13s (failure confirm) / 2.02s (rollback restore) | 2.23s / 2.31s | 3 | Same as above | Local packaging rehearsal only — see rollback-results.md |
| Worker crash + competing-worker recovery (Journey C) | ~9.4s | 9.5s | 5 (via full resilience-suite re-runs) | Real arq worker processes, real PostgreSQL | Includes Playwright's own navigation/assertion overhead, not a pure worker metric |
| Redis + PostgreSQL stop/start recovery (Journey D) | ~9.6s | 10.6s | 5 | Real `docker compose stop/start db redis` | Container stop/start time dominates; a managed cloud database's failover profile will differ substantially |
| Backup: seed → dump → restore → verify (full cycle) | 1.89s | 1.97s | 3 | Local dev-compose Postgres via `docker compose exec db pg_dump/pg_restore` | Trivially small synthetic dataset (one user's full reference graph); does not extrapolate to a real database's size |
| 10-cycle reset/repeatability (full demo import → brief → approve → execute → delete, per cycle) | ~1.0–1.5s/cycle | N/A | 10 (Phase 1 harness, re-run this phase) | In-process ASGI transport, no network hop | Not comparable to a real end-user request over HTTP/TLS |
| Uncertain-write repeatability (propose → approve → execute → uncertain → replay-check), per cycle | <0.1s | N/A | 20 (10 × 2 action types) | In-process, no real Google network latency | Deliberately excludes real provider latency — proves the durability mechanism, not wall-clock write time |

## What this does not measure

- Real Google API latency (all provider calls in this phase are either stubbed or routed through the local fake-Google server).
- Behaviour under concurrent production load.
- Recovery time in any actual hosting environment (none is provisioned yet — Stage 12+).
- Cold-start time for a containerised/orchestrated deployment (this project has no container image build yet).
