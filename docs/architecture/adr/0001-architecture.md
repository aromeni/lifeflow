# ADR 0001 — MVP Architecture

**Status:** Accepted · **Date:** 2026-07-15 · **Stage:** 0

## Context

LifeFlow AI must deliver a trustworthy human-in-the-loop personal operations agent as an MVP, buildable by a small team, runnable in demo mode without external credentials, and extensible into editions without rewriting the core. The full option analysis and reversibility notes live in [../../delivery/assumptions-and-decisions.md](../../delivery/assumptions-and-decisions.md); this ADR records the accepted decisions.

## Decisions

### D1 — Modular monorepo with Next.js frontend and FastAPI backend

`apps/web` (Next.js, TypeScript, App Router) + `apps/api` (FastAPI, Python 3.12, Pydantic v2, SQLAlchemy 2, Alembic) + `packages/contracts` (OpenAPI-generated types) + `prompts/`, `evals/`, `workers/`, `infra/`, `docs/`, `scripts/`.

**Why:** one repo keeps contracts, prompts, evals, and docs versioned together; Python has the strongest ecosystem for the extraction/eval layer; Next.js gives accessible SSR UI with server-side session handling. **Consequence:** two toolchains; mitigated by contract generation and a single compose file.

### D2 — PostgreSQL as the only datastore initially; Redis deferred to Stage 8

No Redis, queue, or vector database until a measured need exists. On-demand brief generation runs in-request/in-process first. When scheduled briefs arrive (Stage 8), adopt **arq** (async, Redis-based, minimal) rather than Celery/Dramatiq — it matches the async FastAPI stack and small job volume. A fresh ADR will confirm or revise this at Stage 8.

### D3 — Application sign-in via Google Sign-In (OpenID Connect), separate from connector grants

Users authenticate to LifeFlow with Google Sign-In (`openid email profile` only). Gmail/Calendar scopes are requested **separately and incrementally** on the Connections screen, so signing in never implies mailbox access. Demo mode uses a development-seeded local session (no Google). All records carry `user_id`; ownership is enforced in every repository query and API route from Stage 2 — no singleton user, no enterprise tenancy.

**Why:** avoids a password store, matches the audience (Gmail users), and keeps consent granular. **Reversible:** an email/magic-link provider can be added later behind the same session layer.

### D4 — Provider-neutral LLM layer; mock provider is the default

```python
class LLMProvider(Protocol):
    async def generate_structured(
        self, *, task: str, input_data: dict,
        output_schema: type[BaseModel], trace_context: dict,
    ) -> BaseModel: ...
```

Mock provider first (demo mode and all CI); Anthropic as the first real implementation. Prompts are versioned files in `prompts/`; outputs are strict Pydantic schemas; timeouts, bounded retries, and cost/usage capture are mandatory. No direct model calls in routers or business logic. Deterministic detectors run **before and independently of** the LLM, so a degraded brief always exists.

### D5 — Deterministic safety pipeline around the LLM

LLM output never invokes actions. The only path to a side effect is: typed `ActionProposal` → schema validation → deterministic policy engine (ownership, state, expiry, scope, payload-hash match, idempotency, risk level) → explicit human approval → idempotent executor → audit event. High-risk actions (send email, delete event, purchase) are not representable as action types — prohibition by construction, not by prompt.

**Stage 6 implementation note:** approval is an immutable snapshot of the closed action type, canonical complete payload, proposal version, and their binding hash. Every executor field is required and shown before approval; editing atomically clears the snapshot and increments the version. Proposal generation is change-aware through a stable origin fingerprint, and execution is one-record-per-proposal with replay returning the original result. Stage 6 executors are synthetic only.

### D6 — Connector interfaces with synthetic adapters first

`EmailConnector` / `CalendarConnector` / `TaskConnector` protocols; synthetic adapters + fictional UK dataset (Stage 3) precede Google adapters (Stage 7). Domain services never import Google SDK types. Google adapters use minimal scopes (`gmail.readonly`, `gmail.compose` for drafts, `calendar.readonly`, `calendar.events`), OAuth state + PKCE, bounded pagination, and sync cursors.

**Stage 7 implementation note:** `GoogleEmailConnector`/`GoogleCalendarConnector` implement these protocols unchanged behind a new `google/` package (narrow, closed-method transport clients — see [ADR 0003](0003-stage7-google-integration.md) D13). Cursor-based incremental sync (Gmail `historyId`, Calendar `syncToken`) falls back to a full bounded resync on expiry (HTTP 404 / 410 respectively).

### D7 — Token encryption via application-level envelope with a KMS-ready interface

OAuth refresh/access tokens are encrypted (AES-GCM via a `TokenCipher` interface) before database storage. Development uses an environment-managed key; the interface is designed for a managed KMS in production. Key-rotation assumptions documented in the threat model.

**Stage 7 implementation note:** a token refresh that omits a new `refresh_token` (Google's normal behaviour outside the initial `access_type=offline` grant) never clears the previously stored encrypted refresh token — see [ADR 0003](0003-stage7-google-integration.md) D18. Refreshes are row-locked per account to avoid racing writes (D19).

### D8 — Hosting decision deferred to Stage 11; UK/EU data residency as a constraint

Local Docker Compose covers Stages 1–10. Production hosting (UK/EU region, GDPR-aligned processor terms) is selected in a Stage 11 ADR. Nothing before Stage 11 depends on a hosting provider.

### D9 — Tooling

- Python: **uv** for dependency management; **ruff** (format + lint); **mypy**; **pytest**/pytest-asyncio.
- TypeScript: **pnpm** workspaces; ESLint + Prettier; **Vitest** + React Testing Library; **Playwright** for E2E; **Zod** at the client boundary.
- No Turborepo/Nx until build times justify it.

## Consequences

- Demo mode is a first-class product path, not a stub — every stage gate runs without credentials.
- Two languages require contract discipline: `packages/contracts` is generated from the FastAPI OpenAPI schema and is the only way web talks to api.
- Deferring Redis/queues keeps Stage 1–7 operationally simple at the cost of revisiting job architecture at Stage 8 (accepted; scoped ADR planned).

## Follow-up ADRs planned

- 0002 (Stage 4): evaluation acceptance targets after deterministic baseline. **Filed.**
- 0003 (Stage 7): Google OAuth, durable execution outcomes, and transport-client design. **Filed** — [0003-stage7-google-integration.md](0003-stage7-google-integration.md).
- 0004 (Stage 8): job runner confirmation (arq) and scheduling design.
- 0005 (Stage 11): production deployment architecture and hosting provider.
