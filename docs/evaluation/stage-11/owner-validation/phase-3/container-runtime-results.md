# Stage 11A Phase 3 — Container and Runtime Hardening Results (S11A-P3-040)

**Status:** Complete · **Date:** 2026-07-31

Companion: [../../../../delivery/stage-11a-phase-3-plan.md](../../../../delivery/stage-11a-phase-3-plan.md) · [defect-register.md](defect-register.md)

`docker-compose.yml` is a **local development and CI convenience file**, not a production deployment manifest — production hosting/deployment shape is an explicitly deferred future ADR (Stage 12/13, per `docs/delivery/stage-plan.md`). This review is scoped accordingly: a local hardening assessment, never production-deployment work, and it introduces no paid-cloud infrastructure.

## Findings and fixes applied this phase

- **Port binding (fixed).** Both `db` and `redis` services used the short `"host:container"` port syntax, which Docker binds to every host network interface (`0.0.0.0`) by default — not just loopback. Since both services use well-known, intentionally weak/absent credentials (`lifeflow`/`lifeflow` for Postgres, no auth at all for Redis), any other device on the same local network (e.g. a shared Wi-Fi network, a coworking space, a conference room) could previously have reached them. **Fixed**: both mappings now use `"127.0.0.1:${PORT}:<container-port>"`, restricting access to the local machine only. Verified via `docker port` (now reports `127.0.0.1:5433`/`127.0.0.1:6380`, previously `0.0.0.0:...`) and a full re-run of `test_stage11a_phase3_owner_scoping.py` confirming `localhost`-based connectivity (which every test and dev workflow in this repo already uses) is unaffected.

## Current posture (documented, not changed this phase)

- **Root vs non-root execution.** No explicit `user:` directive is set in `docker-compose.yml`. Both official images already drop privileges internally before running the actual database/cache process (`postgres:16-alpine`'s entrypoint execs the server via `gosu postgres` after root-only `initdb` setup; `redis:7-alpine`'s Dockerfile ends with `USER redis`), so the running server process is not root in either container despite the compose file not saying so explicitly. Adding an explicit `user:` directive for Postgres specifically would break its entrypoint (it needs root briefly for `initdb`), so this is left as-is — the images' own defaults already provide the real protection here.
- **Writable filesystem scope.** Neither service uses `read_only: true`. This is not tightened this phase: Postgres and Redis both need to write to their data directories, and a `tmpfs`/`read_only` + explicit writable-volume split is a genuine production-hardening technique that would need care to avoid breaking local developer ergonomics (e.g. `docker compose down -v` resets, log file locations). **Deferred, documented as a future production consideration**, not a current exploitable gap for a loopback-only local service.
- **Exposed ports.** Now loopback-only (see above). Container-internal ports (5432, 6379) are unchanged — that's normal and required for the app container(s) that will eventually join the same Docker network in a real deployment.
- **Secret injection.** Postgres's password is a plaintext `POSTGRES_PASSWORD` environment variable with an explicit inline comment stating it is development-only; `.env.example`/`scripts/check_env_example_secrets.py` already prevent a real secret from ever occupying this or any other tracked variable. No change needed.
- **Debug mode / development servers.** Postgres/Redis have no "debug mode" concept; the application's own `environment=development`-gated behaviours (dev-login, fake-Google server, demo-clock override) are already covered by `test_e2e_test_controls.py`'s production-refusal suite (§ Test-control isolation below), not by this compose file.
- **Health checks.** Both services already have `healthcheck` blocks (`pg_isready`, `redis-cli ping`) with sensible intervals/timeouts/retries — no gap.
- **Readiness checks.** The application's own `/ready` route (not this compose file) already reports truthful per-dependency readiness (Stage 9 Phase 5) — no gap.
- **Dependency ordering.** Neither service depends on the other; the application layer (not in this compose file) is responsible for its own startup ordering against both, and already handles both being unavailable gracefully (Stage 9 Phase 5, Stage 11A Phase 2).
- **Restart policies.** No `restart:` policy is set. For a local dev/CI compose file (not a long-running production service), this is intentional — a crashed dev database should surface immediately to the developer, not silently restart and mask a real problem. **Not changed.**
- **Volume permissions.** The `lifeflow-db-data` named volume uses Docker's own default ownership handling for `postgres:16-alpine`; no custom permission scheme is configured or needed for a single-developer local volume.
- **Database/Redis exposure.** Now loopback-only (fixed above); previously the only exposure gap this review found.
- **Network segmentation.** Both services share the default compose network with no segmentation — appropriate for a two-service local dev stack where the API/worker (run outside Docker, directly via `uv run uvicorn`/`arq`) need to reach both.
- **Unnecessary packages / shell availability.** Both images are `-alpine` variants (minimal base, `sh` present for entrypoint scripts only) — already a reasonably minimal choice; no unnecessary packages were found installed beyond each image's own standard entrypoint tooling.

## Classification

Per the governing P0–P3 framework: the port-binding finding was **P2** (excessive-but-bounded local exposure, no cross-user or credential data actually observed to have leaked — this is a local development posture gap, not an active compromise) and has been **fixed this phase**. The remaining documented-but-unchanged items are appropriate for a local dev/CI compose file and are explicitly deferred to the future production-deployment ADR (Stage 12/13) rather than treated as current defects.
