# scripts

Repeatable local maintenance scripts. Each script must be idempotent and documented here.

| Script | Purpose |
|---|---|
| `demo.sh` | One-command demo mode: starts PostgreSQL, applies migrations, launches the API (8010) and web app (3000). Ctrl-C stops the servers. |
| `generate-contracts.sh` | Regenerates `packages/contracts` (openapi.json + index.d.ts) from the FastAPI schema. Run after changing API routes or schemas. |
| `metrics.py` | Regenerates the repository metrics dashboard at `docs/delivery/metrics.md` (file counts, tests, coverage, stage progress). Run from the repo root: `python3 scripts/metrics.py`. Start the dev database first for full test numbers. |
