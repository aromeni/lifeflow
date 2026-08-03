#!/usr/bin/env bash
# Stage 9 Delivery Phase 5 (§20) outage/resilience Playwright journeys.
# A separate script from scripts/e2e.sh, not an addition to it: these four
# journeys need a dedicated API process (GOOGLE_OAUTH_ENABLED=true, redirected
# to the fake Google server) and Journey D stops/starts the real Postgres/Redis
# containers the whole stack depends on — running that alongside the other 10
# journeys' shared stack would break whichever of them happened to be running
# concurrently. Never run this at the same time as scripts/e2e.sh.
#
# Safety: this script starts exactly two processes it owns — the fake Google
# server and the dedicated API (port 8011) — and its EXIT trap stops both by
# port, not by a remembered PID, because Journey B deliberately kills and
# respawns the port-8011 process mid-test (to prove a real API restart never
# retries an uncertain provider write); a PID-based cleanup would silently
# miss that respawned process. It never touches a pre-existing Redis, web
# dev server, or worker (Journey C manages its own worker processes
# entirely within the spec).
set -euo pipefail
set -m
cd "$(dirname "$0")/.."

docker compose up -d db redis --wait

for i in $(seq 1 30); do
  if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then break; fi
  if [ "$i" -eq 30 ]; then echo "e2e-resilience: Redis did not become ready" >&2; exit 1; fi
  sleep 1
done

(cd apps/api && uv run alembic upgrade head)

export LIFEFLOW_E2E=1

# shellcheck disable=SC1091
source scripts/resilience-api-env.sh

API_LOG="$(mktemp -t lifeflow-e2e-resilience-api.XXXXXX)"
(
  cd apps/api
  # shellcheck disable=SC1091
  source ../../scripts/resilience-api-env.sh
  exec uv run uvicorn --app-dir src lifeflow_api.main:app --port 8011 --forwarded-allow-ips=""
) >"$API_LOG" 2>&1 &
API_PID=$!

cleanup() {
  # The suite seeds encrypted fake-provider credentials under a dedicated
  # fixed test key. Remove only those fixture accounts so a later real
  # preconnection gate cannot be contaminated by this test run.
  if ! (cd apps/api && uv run python scripts/e2e_google_support.py cleanup-accounts); then
    echo "e2e-resilience: WARNING — synthetic credential cleanup failed" >&2
  fi
  # Port-based, not PID-based: Journey B intentionally replaces this process
  # mid-suite, so the PID we started is not necessarily the one still
  # running by the time this script exits. `-sTCP:LISTEN` is essential, not
  # cosmetic: a plain `lsof -ti:8011` matches ANY socket naming port 8011 on
  # either end, including Playwright's own outbound connections to the API —
  # killing those would SIGKILL the test runner itself instead of just the
  # API. Restricting to the LISTEN-state socket targets only the server.
  lsof -ti tcp:8011 -sTCP:LISTEN | xargs -r kill -9 2>/dev/null || true
  wait "$API_PID" 2>/dev/null || true
  rm -f "$API_LOG"
}
trap cleanup EXIT INT TERM

for i in $(seq 1 40); do
  if curl -sf http://localhost:8011/health >/dev/null 2>&1; then break; fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "e2e-resilience: dedicated API failed to start:" >&2; cat "$API_LOG" >&2; exit 1
  fi
  if [ "$i" -eq 40 ]; then
    echo "e2e-resilience: dedicated API not ready in time:" >&2; cat "$API_LOG" >&2; exit 1
  fi
  sleep 1
done
echo "e2e-resilience: dedicated API ready (pid $API_PID, port 8011)"

pnpm --filter @lifeflow/web exec playwright test --config=playwright.resilience.config.ts "$@"
