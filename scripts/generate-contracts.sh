#!/usr/bin/env bash
# Regenerate packages/contracts from the FastAPI OpenAPI schema.
# Idempotent; run from the repository root after changing API routes/schemas.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Exporting OpenAPI schema from apps/api..."
# PYTHONPATH=src keeps this immune to the macOS hidden-.pth issue (see README).
(cd apps/api && PYTHONPATH=src uv run python -m lifeflow_api.export_openapi) > packages/contracts/openapi.json

echo "Generating TypeScript types..."
pnpm --filter @lifeflow/contracts generate

echo "Done: packages/contracts/index.d.ts"
