#!/usr/bin/env bash
# End-to-end tests: prepare the database, then run Playwright.
# Playwright itself starts (or reuses) the API and web dev servers.
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose up -d db --wait
(cd apps/api && uv run alembic upgrade head)
pnpm --filter @lifeflow/web test:e2e "$@"
