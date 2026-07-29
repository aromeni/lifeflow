#!/usr/bin/env bash
# End-to-end tests: prepare the database + queue, start a real ARQ worker, then
# run Playwright (which starts/reuses the API and web dev servers itself). The
# worker is required by the Stage 9 Delivery Phase 2 destructive journeys and is
# harmless for the other specs.
#
# Safety: this script starts exactly one process it owns — the ARQ worker — and
# its EXIT trap kills only that worker's own process group. It never kills a
# pre-existing Redis, API, web server or worker (no name-based pkill), and it
# leaves no orphan behind on repeated runs. The destructive seed/verify support
# script additionally refuses any non-local / non-test database.
set -euo pipefail
set -m  # own process group per background job, so we can kill only ours
cd "$(dirname "$0")/.."

docker compose up -d db redis --wait

# Explicit Redis readiness (belt-and-braces alongside compose --wait).
for i in $(seq 1 30); do
  if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then break; fi
  if [ "$i" -eq 30 ]; then echo "e2e: Redis did not become ready" >&2; exit 1; fi
  sleep 1
done

(cd apps/api && uv run alembic upgrade head)

# The support script that seeds/reads fixtures requires this marker AND a
# local/test database, so it can never touch production or staging.
export LIFEFLOW_E2E=1

# Start the real ARQ worker (own process group). PYTHONPATH=src mirrors the
# API's `--app-dir src`. Log to a temp file so a startup failure is visible.
WORKER_LOG="$(mktemp -t lifeflow-e2e-worker.XXXXXX)"
(cd apps/api && PYTHONPATH=src exec uv run arq lifeflow_api.worker_app.WorkerSettings) \
  >"$WORKER_LOG" 2>&1 &
WORKER_PID=$!

cleanup() {
  # Kill only the worker's own process group (never anything by name).
  kill -TERM -"$WORKER_PID" 2>/dev/null || kill -TERM "$WORKER_PID" 2>/dev/null || true
  wait "$WORKER_PID" 2>/dev/null || true
  rm -f "$WORKER_LOG"
}
trap cleanup EXIT INT TERM

# Worker readiness: wait for arq's startup line, and fail fast (with safe logs)
# if the worker process exits first.
for i in $(seq 1 40); do
  if grep -q "Starting worker for" "$WORKER_LOG" 2>/dev/null; then break; fi
  if ! kill -0 "$WORKER_PID" 2>/dev/null; then
    echo "e2e: ARQ worker failed to start:" >&2; cat "$WORKER_LOG" >&2; exit 1
  fi
  if [ "$i" -eq 40 ]; then
    echo "e2e: ARQ worker not ready in time:" >&2; cat "$WORKER_LOG" >&2; exit 1
  fi
  sleep 1
done
echo "e2e: ARQ worker ready (pid $WORKER_PID)"

pnpm --filter @lifeflow/web test:e2e "$@"
