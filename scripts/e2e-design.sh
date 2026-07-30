#!/usr/bin/env bash
# Stage 10 design/accessibility/responsive/visual-regression Playwright suite
# (`apps/web/e2e-design/`). A separate script and discovery boundary from
# scripts/e2e.sh (the original 10 functional journeys) and
# scripts/e2e-resilience.sh (the 4 outage journeys), so none of the three
# suites' test counts is silently inflated by another's — see
# docs/delivery/reports/stage-10.md. This suite needs no ARQ worker (nothing
# in it confirms a destructive deletion) and no fake-Google/GOOGLE_OAUTH_ENABLED
# setup (nothing in it exercises a real-Google code path) — it runs against
# the same plain demo stack as scripts/e2e.sh (port 8010/3000), which is why
# it must not run at the same time as scripts/e2e.sh: both would otherwise
# start/reuse the same dev server pair.
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose up -d db --wait

(cd apps/api && uv run alembic upgrade head)

pnpm --filter @lifeflow/web exec playwright test --config=playwright.design.config.ts "$@"
