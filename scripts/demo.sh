#!/usr/bin/env bash
# One-command demo mode: database + migrations + API + web.
# Usage: ./scripts/demo.sh   (Ctrl-C stops everything; the db keeps running)
set -euo pipefail

cd "$(dirname "$0")/.."

echo "→ Starting PostgreSQL..."
docker compose up -d db --wait

echo "→ Applying migrations..."
(cd apps/api && uv run alembic upgrade head)

echo "→ Starting API (http://localhost:8010) and web (http://localhost:3000)..."
(cd apps/api && uv run uvicorn --app-dir src lifeflow_api.main:app --port 8010 --forwarded-allow-ips="") &
API_PID=$!
pnpm web:dev &
WEB_PID=$!

trap 'echo; echo "→ Stopping demo..."; kill "$API_PID" "$WEB_PID" 2>/dev/null || true' INT TERM EXIT

echo
echo "Demo ready: open http://localhost:3000 and press 'Try demo'."
echo "Press Ctrl-C to stop."
wait
