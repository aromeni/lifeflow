# LifeFlow AI

A permissioned, inspectable, human-in-the-loop personal operations agent. LifeFlow quietly finds what needs attention in your Gmail and Google Calendar, explains why it matters, and prepares the next step. External side effects — a Gmail draft, a calendar event — always require your review and explicit approval; LifeFlow never sends, deletes, or purchases anything, and nothing it prepares runs on its own.

- Product North Star: [docs/project/project-foundation.md](docs/project/project-foundation.md)
- MVP scope and success criteria: [docs/product/mvp-scope.md](docs/product/mvp-scope.md)
- Delivery plan (stage-gated): [docs/delivery/stage-plan.md](docs/delivery/stage-plan.md)
- Architecture: [docs/architecture/system-context.md](docs/architecture/system-context.md) · [ADR 0001](docs/architecture/adr/0001-architecture.md) · [ADR 0003 (Google integration)](docs/architecture/adr/0003-stage7-google-integration.md) · [repository tree](docs/architecture/tree.md) · [naming conventions](docs/architecture/naming-conventions.md)
- Threat model: [docs/security/threat-model.md](docs/security/threat-model.md)
- Metrics dashboard: [docs/delivery/metrics.md](docs/delivery/metrics.md) (regenerate with `python3 scripts/metrics.py`) · Stage reports: [docs/delivery/reports/](docs/delivery/reports/)

**Status:** Stage 7 (real Google integration) is **complete**, tagged `stage-7-complete` — both the Gmail and Calendar paths are verified live end-to-end against a real sandbox account (see [docs/delivery/reports/stage-07.md](docs/delivery/reports/stage-07.md) and [docs/delivery/stage-07-manual-checklist.md](docs/delivery/stage-07-manual-checklist.md)). Stage 8 (preferences, memory, schedule) is in progress: Phase 1 (explicit preferences), Phase 2 (the scheduled daily brief, arq+Redis), and Phase 3 (transparent inferred memory) are complete and verified; the Stage 8 completion report awaits human review.

## Demo mode (one command)

```bash
./scripts/demo.sh
```

Then open http://localhost:3000 and press **Try demo** — no Google or Anthropic credentials needed. The demo signs in a development user and runs the full pipeline end to end on a fictional UK dataset (24 emails, 12 events) through the synthetic connectors:

- **Ingestion** — emails and events are normalised into `SourceItem` records (raw normalised records are visible at `/debug/source-items`).
- **Signal extraction** — deterministic detectors (and, if enabled, an allow-listed LLM pass) pull requests, commitments, deadlines, follow-ups, and conflicts out of the source items, each one evidence-linked back to where it came from.
- **Priority scoring** — signals are ranked and banded so the most time-sensitive items surface first.
- **Daily brief** — the Today dashboard renders a versioned, persisted brief organised into "Needs attention", "Today & upcoming", "Waiting for", and "Suggested actions", with an evidence drawer on every item.
- **Action proposals** — the brief can propose a typed action (e.g. draft a reply, create a calendar event) for a signal; nothing is ever auto-generated as a fait accompli.
- **Approval, rejection, and editing** — the Approvals screen lets you review each proposal's exact payload, edit it before deciding, approve it, or reject it with a reason; the policy engine enforces what's allowed regardless of what the UI shows.
- **Simulated execution** — in demo mode every action executes against a simulated in-memory connector, never a real mailbox or calendar. The result is labelled plainly ("Simulation result") so it's never confused with a real side effect.
- **Audit trail** — every proposal, decision, and execution attempt is recorded as an audit event and shown inline on the proposal (`Audit trail (N events)`), including outcomes classified as succeeded, failed, or uncertain.

## Repository layout

```text
apps/web            Next.js frontend (TypeScript, App Router, Tailwind)
apps/api            FastAPI backend (Python 3.12, SQLAlchemy 2, Alembic)
packages/contracts  OpenAPI-generated shared types, consumed by apps/web
prompts/            Versioned prompts and output contracts for LLM-assisted extraction and brief composition
evals/              Golden datasets and scoring for signals, briefs, and actions
workers/            Background job entry points (scheduled-brief worker live, Stage 8 Phase 2; retention still Stage 8/9)
infra/              Deployment configuration beyond local Docker Compose — Stage 11, not yet populated
docs/               Product, architecture, security, and delivery docs
```

## Frontend routes

```text
/              Landing page — privacy summary and "Try demo"
/onboarding    Demo timezone/section setup, then redirects to /today
/today         Daily brief: sections, evidence drawer, links to Approvals and Connections
/approvals     Action proposal inbox — review, edit, approve, reject, and see execution results
/connections   Google account connection status, "Connect Google", and "Sync now"
```

## Prerequisites

- Docker (Compose v2)
- [uv](https://docs.astral.sh/uv/) ≥ 0.5 — manages Python 3.12 automatically
- Node 22+ and pnpm 10 (`corepack enable` or `npm i -g pnpm`)

## Setup (fresh clone)

```bash
cp .env.example .env                    # local config; never commit .env
docker compose up -d db redis --wait    # PostgreSQL 16 on 5433, Redis 7 on 6380
# Redis is optional: only the Stage 8 Phase 2 scheduled-brief worker needs
# it, exactly like the LLM provider — everything else works without it.

# Backend
cd apps/api
uv sync                           # installs Python 3.12 + dependencies
uv run alembic upgrade head       # apply migrations (works from empty state)
uv run uvicorn --app-dir src lifeflow_api.main:app --reload --port 8010
# → http://localhost:8010/health  (liveness)
# → http://localhost:8010/ready   (readiness: checks the database)
# → http://localhost:8010/docs    (OpenAPI UI, development only)
# Port 8010 by default: 8000 is commonly taken by other local apps.

# Scheduled-brief worker (new terminal; Stage 8 Phase 2, optional)
uv run arq lifeflow_api.worker_app.WorkerSettings
# or, from anywhere: python workers/scheduler_worker.py
# Generates each opted-in user's brief at their configured briefing_time —
# see "Scheduled briefs" below.

# Frontend (new terminal, from repo root)
pnpm install
pnpm web:dev
# → http://localhost:3000         (landing page — press "Try demo")
# → http://localhost:3000/health  (liveness)

# Git hooks (once per clone)
uvx pre-commit install
```

## Google integration (Stage 7, disabled by default)

Real Google sign-in and data access are entirely opt-in and require explicit configuration; with no configuration set, demo mode, dev-login, and the synthetic connectors work exactly as above.

- **Two separate OAuth flows, never one shared client** (ADR 0003 D10): an **OIDC client** signs users into LifeFlow itself (`/auth/google/login`, scopes `openid email profile` only — never mailbox or calendar access), and a **connector client** is requested only from the Connections screen (`/connected-accounts/google/*`) to grant data access.
- **Exact connector scopes** (`apps/api/src/lifeflow_api/google_scopes.py`): `gmail.readonly`, `gmail.compose` (drafts only, never send), `calendar.readonly`, `calendar.events`.
- **Disabled by default**: set `GOOGLE_OAUTH_ENABLED=true` in `.env` plus both client configs (`GOOGLE_OIDC_CLIENT_ID`/`SECRET`, `GOOGLE_CONNECTOR_CLIENT_ID`/`SECRET`) and a `TOKEN_KEY` to encrypt stored tokens — the app refuses to enable Google routes otherwise. See `.env.example` for the full variable list and generation commands.
- **Test-account requirement**: use a Google Cloud OAuth consent screen in **Testing** status with a **sandbox** Google account added as a test user. Never point this at a primary or production mailbox.
- **Restricted-scope verification caveat**: the Gmail and Calendar scopes above are Google-restricted scopes. Until Google's app verification (or continued "Testing" status with test users) is in place, only test users you've explicitly added can complete the connector consent flow.
- Before treating Stage 7 as pilot-ready, run the full **[manual sandbox-account checklist](docs/delivery/stage-07-manual-checklist.md)** against a real test account — it is currently unexecuted in this environment (no real Google credentials or network access here).

## Scheduled briefs (Stage 8 Phase 2, opt-in, off by default)

A background worker can generate each user's daily brief automatically at their configured `briefing_time`, in their timezone — the same brief pipeline the manual "Generate brief" button uses, tagged `generation_trigger: "scheduled"`. It never syncs Google (sync stays user-triggered only) and never approves or executes anything; any suggested actions still land in the ordinary approval inbox.

- **Off by default**: a user must explicitly enable it in Settings (`scheduled_briefs_enabled`) — an existing deployment never starts scheduling for everyone just because `briefing_time` has a default.
- **Requires**: Redis (`docker compose up -d redis`) and the worker process (`uv run arq lifeflow_api.worker_app.WorkerSettings`, or `python workers/scheduler_worker.py` from anywhere). Neither is required for anything else — with both absent, Settings truthfully reports the scheduler as unavailable and every other route is unaffected.
- **Durable and idempotent**: one `ScheduledBriefRun` row per user per local calendar date (`apps/api/src/lifeflow_api/models.py`); a missed run is generated if the worker resumes within 6 hours, otherwise recorded `skipped`, never backfilled; a crashed-and-retried worker finds an already-generated brief rather than duplicating it.
- **Details**: [ADR 0004](docs/architecture/adr/0004-stage8-preferences-memory-schedule.md) D47–D50; domain logic in `apps/api/src/lifeflow_api/scheduled_briefs.py`; manual checklist in [docs/delivery/stage-08-phase-2-manual-checklist.md](docs/delivery/stage-08-phase-2-manual-checklist.md).

### Inferred memory (Stage 8 Phase 3)

LifeFlow can learn one narrow, typed preference — your email **sign-off** — from your own deliberate actions here: editing a draft reply and then approving it. It is shown in Settings → *Learned preferences* with a plain-language explanation, a Low/Medium/High confidence, and the number of actions it is based on, so you can **confirm**, **edit & confirm**, **dismiss**, or **delete** it. Nothing is ever applied on its own.

- **Explicit always wins**: an inferred value is *suggest-only* and never touches draft composition. Confirming it writes an ordinary explicit `preferred_email_signoff` preference; only that explicit value is applied — to *future* draft proposals, which you still preview and approve in full. The adapted body is part of the approval hash; approval, recipients, and the Gmail executor are unchanged.
- **User-controlled evidence only**: it learns only from drafts you edited and approved — never from the content of emails you receive. Sensitive categories can never be inferred (a closed registry plus a documented deny-list).
- **Off by default**: enable it in Settings (`memory_inference_enabled`). Pausing stops new learning without deleting anything; deleting memory never touches Gmail or Calendar.
- **Uses the same worker** as the scheduled brief: a qualifying approval best-effort-enqueues `recompute_user_memory(user_id)` (user id only). If Redis is down the approval still succeeds and the job self-heals on the next recompute — PostgreSQL is the source of truth.
- **Details**: [ADR 0004](docs/architecture/adr/0004-stage8-preferences-memory-schedule.md) D51–D58; logic in `apps/api/src/lifeflow_api/memory_registry.py`, `memory_inference.py`, `memory.py`; manual checklist in [docs/delivery/stage-08-phase-3-manual-checklist.md](docs/delivery/stage-08-phase-3-manual-checklist.md).

## Tests and checks

```bash
# Backend (from apps/api)
uv run pytest                     # all tests; integration tests need the db container,
                                   # a few scheduled-brief tests also need redis (see below)
uv run pytest -m "not integration"
uv run ruff format --check . && uv run ruff check . && uv run mypy

# Frontend (from repo root)
pnpm web:test && pnpm web:lint && pnpm web:typecheck && pnpm web:build

# Playwright end-to-end (starts db, api, and web itself)
./scripts/e2e.sh

# Golden-dataset evals (all six modes)
./scripts/run-evals.sh det              # deterministic baseline only
./scripts/run-evals.sh det+mock         # + fixture-driven mock LLM
./scripts/run-evals.sh det+anthropic    # + real Anthropic pass (needs ANTHROPIC_API_KEY)
./scripts/run-evals.sh brief            # daily-brief composition, deterministic
./scripts/run-evals.sh brief+mock       # daily-brief composition, mock LLM
./scripts/run-evals.sh actions          # action-proposal generation

# Contracts freshness (fails if generated types are stale)
./scripts/generate-contracts.sh && git diff --exit-code packages/contracts

# Alembic schema drift (from apps/api)
uv run alembic check

# Secret scanning
uvx detect-secrets scan --baseline .secrets.baseline

# All pre-commit hooks (formatting, lint, secrets, large files, merge conflicts)
uvx pre-commit run --all-files
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
