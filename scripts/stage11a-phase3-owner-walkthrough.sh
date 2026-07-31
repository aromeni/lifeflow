#!/usr/bin/env bash
# Stage 11A Phase 3 (docs/delivery/stage-11a-phase-3-plan.md), scenario
# S11A-P3-025/044: the owner-operated browser-privacy walkthrough. Uses the
# same plain demo stack as scripts/e2e.sh (no dedicated resilience API or
# fake Google server needed — this walkthrough inspects browser storage/
# console/network on ordinary demo-mode screens, not failure states), kept
# as its own script so this manual/owner-labelled evidence run never
# inflates the functional suite's own journey count, matching the existing
# convention documented in scripts/e2e-design.sh and
# scripts/stage11a-phase2-owner-walkthrough.sh.
set -euo pipefail
set -m
cd "$(dirname "$0")/.."

docker compose up -d db redis --wait

for i in $(seq 1 30); do
  if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then break; fi
  if [ "$i" -eq 30 ]; then echo "phase3-owner-walkthrough: Redis did not become ready" >&2; exit 1; fi
  sleep 1
done

(cd apps/api && uv run alembic upgrade head)

pnpm --filter @lifeflow/web exec playwright test \
  --config=playwright.owner-validation-privacy.config.ts "$@"
