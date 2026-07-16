# LifeFlow AI

A permissioned, inspectable, human-in-the-loop personal operations agent. LifeFlow quietly finds what needs attention in your Gmail and Google Calendar, explains why it matters, and prepares the next step — for your explicit approval. It never sends email, changes your calendar, or completes tasks on its own.

- Product North Star: [docs/project/project-foundation.md](docs/project/project-foundation.md)
- MVP scope and success criteria: [docs/product/mvp-scope.md](docs/product/mvp-scope.md)
- Delivery plan (stage-gated): [docs/delivery/stage-plan.md](docs/delivery/stage-plan.md)
- Architecture: [docs/architecture/system-context.md](docs/architecture/system-context.md) · [ADR 0001](docs/architecture/adr/0001-architecture.md) · [repository tree](docs/architecture/tree.md) · [naming conventions](docs/architecture/naming-conventions.md)
- Threat model: [docs/security/threat-model.md](docs/security/threat-model.md)
- Metrics dashboard: [docs/delivery/metrics.md](docs/delivery/metrics.md) (regenerate with `python3 scripts/metrics.py`) · Stage reports: [docs/delivery/reports/](docs/delivery/reports/)

**Status:** Stage 3 — demo mode with synthetic connectors. A fictional UK dataset flows through the real ingestion pipeline into a Today dashboard shell. Signals, priorities, and the daily brief arrive in Stages 4–5.

## Demo mode (one command)

```bash
./scripts/demo.sh
```

Then open http://localhost:3000 and press **Try demo** — no Google or Anthropic credentials needed. The demo signs in a development user, imports 24 fictional emails and 12 events through the synthetic connectors, and shows them on the Today dashboard (raw normalised records live under `/debug/source-items`).

## Repository layout

```text
apps/web            Next.js frontend (TypeScript, App Router, Tailwind)
apps/api            FastAPI backend (Python 3.12, SQLAlchemy 2, Alembic)
packages/contracts  OpenAPI-generated shared types (populated from Stage 2)
workers/            Background job entry points (Stage 8)
prompts/            Versioned prompts and output contracts (Stage 4)
evals/              Golden datasets and scoring (Stage 4)
infra/              Deployment configuration (Stage 11)
docs/               Product, architecture, security, and delivery docs
```

## Prerequisites

- Docker (Compose v2)
- [uv](https://docs.astral.sh/uv/) ≥ 0.5 — manages Python 3.12 automatically
- Node 22+ and pnpm 10 (`corepack enable` or `npm i -g pnpm`)

## Setup (fresh clone)

```bash
cp .env.example .env              # local config; never commit .env
docker compose up -d db --wait    # PostgreSQL 16 on localhost:5433

# Backend
cd apps/api
uv sync                           # installs Python 3.12 + dependencies
uv run alembic upgrade head       # apply migrations (works from empty state)
uv run uvicorn --app-dir src lifeflow_api.main:app --reload --port 8010
# → http://localhost:8010/health  (liveness)
# → http://localhost:8010/ready   (readiness: checks the database)
# → http://localhost:8010/docs    (OpenAPI UI, development only)
# Port 8010 by default: 8000 is commonly taken by other local apps.

# Frontend (new terminal, from repo root)
pnpm install
pnpm web:dev
# → http://localhost:3000         (placeholder page)
# → http://localhost:3000/health  (liveness)

# Git hooks (once per clone)
uvx pre-commit install
```

## Tests and checks

```bash
# Backend (from apps/api)
uv run pytest                     # all tests; integration tests need the db container
uv run pytest -m "not integration"
uv run ruff format --check . && uv run ruff check . && uv run mypy

# Frontend (from repo root)
pnpm web:test && pnpm web:lint && pnpm web:typecheck && pnpm web:build

# Secret scanning
uvx detect-secrets scan --baseline .secrets.baseline
```

CI (GitHub Actions, [.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the same lint, type, test, migration, build, and secret-scanning steps on every push and pull request.

## Stopping

```bash
docker compose down       # stop PostgreSQL (data persists in the named volume)
docker compose down -v    # stop and delete development data
```

## Troubleshooting

**`ModuleNotFoundError: No module named 'lifeflow_api'` on macOS** — file-sync tools (e.g. iCloud when the repo lives under Desktop/Documents) can set the hidden flag on the editable-install `.pth` file, which Python 3.12+ then ignores. Fix with:

```bash
chflags nohidden apps/api/.venv/lib/python3.12/site-packages/*.pth
```

Keeping the repository outside synced folders avoids this entirely.

## Error responses and correlation IDs

Every API error uses one shape: `{"error": {"code", "message", "correlation_id"}}`. Requests may supply `X-Correlation-ID`; otherwise one is generated. The ID is echoed in the response and attached to every structured log line.

## Contributing safely

Read [CLAUDE.md](CLAUDE.md) for architecture boundaries and safe-development rules, and the guard rails in the [Project Foundation](docs/project/project-foundation.md). The build is stage-gated: features outside the active stage are not implemented, and no external side effect ever bypasses the approval workflow.
