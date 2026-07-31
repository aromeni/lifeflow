#!/usr/bin/env bash
# Stage 11A Phase 2 (docs/delivery/stage-11a-phase-2-plan.md), scenario
# S11A-P2-027: a local packaging/rollback rehearsal. No production
# deployment or image-versioning infrastructure exists yet (confirmed
# absent during Phase 2 research) — this rehearsal is explicitly scoped as
# local-only, proving the *shape* of a safe rollback (explicit, truthfully
# observed failure, then an explicit, verified recovery), not a real
# blue/green or container-image rollback.
#
# The "deliberately failing candidate configuration" is a genuine existing
# startup guard already in the product (main.py::_session_secret): a
# production-mode boot with no SESSION_SECRET refuses to start. This is not
# a contrived failure — it is real code, exercised here for the first time
# in a rollback-rehearsal context.
#
# Usage (from the repository root):
#   ./scripts/stage11a-phase2-rollback-rehearsal.sh [cycles]
set -euo pipefail
cd "$(dirname "$0")/.."

CYCLES="${1:-3}"
PORT=8026
BASE_URL="http://127.0.0.1:${PORT}"
GOOD_SHA="$(git rev-parse HEAD)"
PGREP_PATTERN="uvicorn --app-dir src lifeflow_api.main:app --port ${PORT}"

echo "Known-good version under rehearsal: ${GOOD_SHA}"

# `uv run uvicorn ...` may fork rather than exec, so a tracked $! can outlive
# its own kill — pattern-matching cleanup is the only reliable teardown, run
# both after every phase and unconditionally on script exit.
cleanup() {
  pkill -f "$PGREP_PATTERN" 2>/dev/null || true
}
trap cleanup EXIT

wait_for() {
  local url="$1" tries=0
  until curl -fsS "$url" >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "$tries" -gt 40 ]; then
      return 1
    fi
    sleep 0.25
  done
  return 0
}

run_one_cycle() {
  local cycle="$1"
  local t0 t_good_up t_fail_confirmed t_rolled_back

  t0=$(date +%s.%N)

  # 1. Current known-good configuration deployed.
  (cd apps/api && uv run uvicorn --app-dir src lifeflow_api.main:app \
    --port "$PORT" --forwarded-allow-ips="" >/tmp/phase2-rollback-good.log 2>&1) &
  if ! wait_for "${BASE_URL}/health"; then
    echo "cycle ${cycle}: FAIL — known-good configuration did not become healthy"
    cleanup
    return 1
  fi
  t_good_up=$(date +%s.%N)
  cleanup
  sleep 0.5

  # 2. Deliberately failing candidate configuration: production mode with no
  #    SESSION_SECRET must refuse to start (main.py's own guard) — never a
  #    false success.
  set +e
  (cd apps/api && ENVIRONMENT=production SESSION_SECRET= TOKEN_KEY_ID=prod-1 \
    uv run uvicorn --app-dir src lifeflow_api.main:app --port "$PORT" \
    --forwarded-allow-ips="" >/tmp/phase2-rollback-bad.log 2>&1)
  BAD_EXIT=$?
  set -e
  if [ "$BAD_EXIT" -eq 0 ]; then
    echo "cycle ${cycle}: FAIL — the deliberately broken configuration must not start successfully"
    return 1
  fi
  if ! grep -q "SESSION_SECRET must be set in production" /tmp/phase2-rollback-bad.log; then
    echo "cycle ${cycle}: FAIL — expected the app's own documented startup guard message"
    return 1
  fi
  t_fail_confirmed=$(date +%s.%N)
  cleanup
  sleep 0.5

  # 3. Explicit rollback: restart the known-good configuration.
  (cd apps/api && uv run uvicorn --app-dir src lifeflow_api.main:app \
    --port "$PORT" --forwarded-allow-ips="" >/tmp/phase2-rollback-restored.log 2>&1) &
  if ! wait_for "${BASE_URL}/health"; then
    echo "cycle ${cycle}: FAIL — rollback did not restore a healthy service"
    cleanup
    return 1
  fi

  # 4. Post-rollback smoke test: /ready must also be truthful (DB is up).
  if ! curl -fsS "${BASE_URL}/ready" | grep -q '"status"'; then
    echo "cycle ${cycle}: FAIL — /ready did not respond truthfully after rollback"
    cleanup
    return 1
  fi
  t_rolled_back=$(date +%s.%N)
  cleanup
  sleep 0.5

  # 5. Exact version identifiable, unchanged by this rehearsal.
  CURRENT_SHA="$(git rev-parse HEAD)"
  if [ "$CURRENT_SHA" != "$GOOD_SHA" ]; then
    echo "cycle ${cycle}: FAIL — HEAD moved during the rehearsal (${GOOD_SHA} -> ${CURRENT_SHA})"
    return 1
  fi

  python3 -c "
t0, t1, t2, t3 = $t0, $t_good_up, $t_fail_confirmed, $t_rolled_back
print(f'cycle ${cycle}: good_up={t1-t0:.2f}s failure_confirmed={t2-t1:.2f}s rollback_total={t3-t2:.2f}s')
"
}

for i in $(seq 0 $((CYCLES - 1))); do
  run_one_cycle "$i"
done

echo "All ${CYCLES} rollback rehearsal cycles passed. Version under rehearsal never changed: ${GOOD_SHA}"
