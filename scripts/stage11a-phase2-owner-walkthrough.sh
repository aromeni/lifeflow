#!/usr/bin/env bash
# Stage 11A Phase 2 (docs/delivery/stage-11a-phase-2-plan.md), scenario
# S11A-P2-034: the owner-operated failure-state walkthrough. Bootstraps the
# exact same dedicated resilience stack scripts/e2e-resilience.sh uses (a
# GOOGLE_OAUTH_ENABLED API on :8011 redirected to the fake Google server on
# :8098), then runs the one new walkthrough spec against it — kept as its
# own script (not folded into e2e-resilience.sh) so this manual/owner-
# labelled evidence run never inflates that suite's own journey count,
# matching the existing convention documented in scripts/e2e-design.sh.
set -euo pipefail
set -m
cd "$(dirname "$0")/.."

docker compose up -d db redis --wait

for i in $(seq 1 30); do
  if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then break; fi
  if [ "$i" -eq 30 ]; then echo "phase2-owner-walkthrough: Redis did not become ready" >&2; exit 1; fi
  sleep 1
done

(cd apps/api && uv run alembic upgrade head)

export LIFEFLOW_E2E=1
export LIFEFLOW_E2E_FAKE_GOOGLE=1

FAKE_GOOGLE_LOG="$(mktemp -t lifeflow-phase2-fake-google.XXXXXX)"
(
  cd apps/api
  exec uv run uvicorn --app-dir src lifeflow_api.testing.fake_google_server:app --port 8098
) >"$FAKE_GOOGLE_LOG" 2>&1 &

API_LOG="$(mktemp -t lifeflow-phase2-owner-walkthrough-api.XXXXXX)"
(
  cd apps/api
  # shellcheck disable=SC1091
  source ../../scripts/resilience-api-env.sh
  exec uv run uvicorn --app-dir src lifeflow_api.main:app --port 8011 --forwarded-allow-ips=""
) >"$API_LOG" 2>&1 &
API_PID=$!

cleanup() {
  # Port-based, matching scripts/e2e-resilience.sh's own reasoning: never
  # assume the PID we started is still the process actually listening.
  lsof -ti tcp:8011 -sTCP:LISTEN | xargs -r kill -9 2>/dev/null || true
  lsof -ti tcp:8098 -sTCP:LISTEN | xargs -r kill -9 2>/dev/null || true
  wait "$API_PID" 2>/dev/null || true
  rm -f "$API_LOG" "$FAKE_GOOGLE_LOG"
}
trap cleanup EXIT INT TERM

for i in $(seq 1 40); do
  if curl -sf http://localhost:8098/__control__/state >/dev/null 2>&1; then break; fi
  if [ "$i" -eq 40 ]; then
    echo "phase2-owner-walkthrough: fake Google server not ready in time:" >&2
    cat "$FAKE_GOOGLE_LOG" >&2
    exit 1
  fi
  sleep 0.5
done

for i in $(seq 1 40); do
  if curl -sf http://localhost:8011/health >/dev/null 2>&1; then break; fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "phase2-owner-walkthrough: dedicated API failed to start:" >&2
    cat "$API_LOG" >&2
    exit 1
  fi
  if [ "$i" -eq 40 ]; then
    echo "phase2-owner-walkthrough: dedicated API not ready in time:" >&2
    cat "$API_LOG" >&2
    exit 1
  fi
  sleep 1
done
echo "phase2-owner-walkthrough: dedicated API ready (pid $API_PID, port 8011); fake Google ready (port 8098)"

pnpm --filter @lifeflow/web exec playwright test \
  --config=playwright.owner-validation-resilience.config.ts "$@"
