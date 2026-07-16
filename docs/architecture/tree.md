# Repository Tree — Where Things Go

**Purpose:** the one-page answer to "where should this file go?". Update it whenever a top-level directory is added or repurposed. Deeper structure is documented in each directory's own README. What to *call* the file once placed: [naming-conventions.md](naming-conventions.md).

```text
lifeflow-ai/
├── apps/
│   ├── web/                 # Next.js frontend: all screens, routes, and UI components.
│   │                        # Client code only — no business logic; talks to the API via generated contracts.
│   └── api/                 # FastAPI backend: domain models, services, policy engine, executors, audit.
│                            # ALL business logic lives here, behind connector/LLM interfaces.
├── packages/
│   └── contracts/           # OpenAPI-generated TypeScript types shared between web and api.
│                            # Generated output only — never hand-edit; regenerate from the API schema.
├── prompts/                 # Versioned prompt files and structured-output contracts for the LLM layer.
│                            # One file per prompt per version; referenced by name+version, never inlined in code.
├── evals/                   # Golden datasets, scoring, and regression tests for extraction and briefs.
│                            # Safety and quality metrics live here — not in the unit-test suites.
├── workers/                 # Background job entry points (scheduled briefs, retention, sync).
│                            # Thin wrappers only — jobs call domain services in apps/api, no logic of their own.
├── infra/                   # Deployment configuration beyond local Docker Compose (Stage 11+).
│                            # Environment-specific config, IaC, and observability setup.
├── scripts/                 # Repeatable local maintenance scripts (idempotent, documented).
│                            # Nothing here is required for the app to run — conveniences only.
├── docs/
│   ├── project/             # North Star: project-foundation.md (vision, principles, guard rails).
│   ├── product/             # Vision, personas, journeys, MVP scope, wireframes.
│   ├── architecture/        # System context, this tree, and adr/ (numbered decision records).
│   ├── security/            # Threat model and security reviews.
│   └── delivery/            # Stage plan, assumptions/decisions log.
├── .github/workflows/       # CI pipelines — mirror the local commands exactly, never diverge.
├── docker-compose.yml       # Local development stack (PostgreSQL now; Redis when Stage 8 needs it).
├── CLAUDE.md                # Repository operating instructions for AI sessions: commands, boundaries, rules.
└── README.md                # Human setup guide: exact clone-to-running instructions.
```

## Placement rules of thumb

- Business rule, domain entity, policy, or executor → `apps/api` (never in `apps/web` or `workers/`).
- New connector or adapter → `apps/api` behind the existing connector interfaces; synthetic variant beside it.
- Anything an LLM reads or must return → a versioned file in `prompts/`, with its schema.
- "Is the system still good?" checks (precision, safety, injection resistance) → `evals/`.
- Type shared across the web/api boundary → regenerate `packages/contracts`; don't hand-write it twice.
- If a new top-level directory seems needed, record why in an ADR first.
