# System Context

**Status:** Stage 0 draft · **Date:** 2026-07-15

Decisions behind this shape are recorded in [adr/0001-architecture.md](adr/0001-architecture.md). Threats and mitigations per component are in [../security/threat-model.md](../security/threat-model.md).

## Context diagram

```text
                        ┌────────────────────────────┐
                        │           User             │
                        │ (browser, UK timezone)     │
                        └─────────────┬──────────────┘
                                      │ HTTPS
                        ┌─────────────▼──────────────┐
                        │      apps/web (Next.js)    │
                        │  landing · onboarding ·    │
                        │  dashboard · approvals ·   │
                        │  privacy · audit · settings│
                        └─────────────┬──────────────┘
                                      │ OpenAPI (typed contracts)
   trust boundary ────────────────────┼──────────────────────────────
                        ┌─────────────▼──────────────┐
                        │      apps/api (FastAPI)    │
                        │ ┌────────────────────────┐ │
                        │ │ Domain services        │ │
                        │ │ ingestion · signals ·  │ │
                        │ │ brief · proposals ·    │ │
                        │ │ policy engine ·        │ │
                        │ │ executors · audit      │ │
                        │ └───┬───────┬───────┬────┘ │
                        └─────┼───────┼───────┼──────┘
             connector        │       │       │  LLMProvider
             interfaces       │       │       │  interface
        ┌─────────────────────▼─┐   ┌─▼─────┐ └───────────────┐
        │ Google adapters        │   │Postgres│   ┌────────────▼───────────┐
        │ (Gmail RO + drafts;    │   │(+ enc. │   │ Mock provider (demo/CI)│
        │  Calendar RO + create) │   │ tokens)│   │ Anthropic provider     │
        └───────────┬────────────┘   └───────┘   │ (structured output)    │
   trust boundary ──┼────────────────────────────└────────────┬───────────┘
        ┌───────────▼────────────┐              ┌─────────────▼───────────┐
        │ Google APIs (external) │              │ Anthropic API (external)│
        └────────────────────────┘              └─────────────────────────┘

        Synthetic adapters (demo mode) replace Google adapters and the
        real LLM provider entirely — no external calls, same interfaces.
        workers/ run scheduled jobs (later stages) through the same
        domain services; no separate business logic.
```

## Components

| Component | Responsibility | Stage |
|---|---|---|
| `apps/web` (Next.js, TypeScript, App Router) | All seven required screens; Zod contract validation; server-side session handling | 1, 3, 5, 6, 9 |
| `apps/api` (FastAPI, Python 3.12, Pydantic v2) | Domain services, policy engine, executors, audit; ownership enforced on every query/route | 1, 2+ |
| `packages/contracts` | OpenAPI-generated shared types between web and api | 1 |
| Connector interfaces (`EmailConnector`, `CalendarConnector`, `TaskConnector`) | Domain depends on interfaces, never on Google SDK details | 3 |
| Synthetic adapters + demo dataset | Full workflow without credentials; includes adversarial fixtures | 3 |
| Google adapters | OAuth (state+PKCE), Gmail read + draft-only creation, Calendar read + create; sync cursors, bounded pagination | 7 |
| `LLMProvider` interface | `generate_structured(...)` with typed schemas, timeouts, bounded retries, cost capture; mock first, Anthropic second | 4 |
| `prompts/` | Versioned prompt files + structured-output contracts | 4 |
| Deterministic detectors | Deadlines, conflicts, stale follow-ups — no LLM required | 4 |
| Priority engine | Explainable hybrid score + reason codes | 4 |
| Policy engine | Deterministic pre-execution checks; risk levels; prohibited actions unrepresentable | 6 |
| Action executors | Idempotent, simulated in demo mode; real draft/event creation in stage 7 | 6, 7 |
| Audit log | Append-only events with correlation IDs, redacted metadata | 2 |
| PostgreSQL | System of record; application-level encryption for OAuth tokens | 1, 2 |
| Redis + job runner | Only when scheduled briefs arrive (stage 8); deferred until needed | 8 |
| `evals/` | Golden dataset, deterministic baseline vs LLM-assisted metrics | 4, 10 |

## Trust boundaries

1. **Browser ↔ API** — authenticated session, CSRF protection, typed contracts.
2. **API ↔ Google/Anthropic** — outbound only; tokens encrypted at rest; minimal scopes; no secrets in logs.
3. **Ingested content ↔ reasoning** — *the critical boundary*: all connector content is untrusted data. It is delimited, never merged into system policy, cannot select tools. LLM output is a typed proposal that must pass schema validation → policy engine → human approval before any executor runs.
4. **Proposal ↔ execution** — only the policy engine invokes executors, keyed by idempotency keys; approval binds to an exact payload hash.

## Key data flows

**Brief generation (on demand):** authorised fetch (bounded window) → redact/minimise → normalise to `SourceItem` → deterministic detectors → structured LLM extraction (optional, schema-validated) → dedupe → score with reason codes → compose `Brief` → typed `ActionProposal`s → policy validation → present. Every step observable, independently testable, and audited.

**Approved action:** approval recorded against payload hash → policy engine re-validates (ownership, state, expiry, scope, payload match, idempotency, risk) → executor runs with idempotency key → result verified → `ActionExecution` + `AuditEvent` written.

**Degraded modes:** connector failure → prior data preserved, partial-failure notice; LLM failure → deterministic-rules brief with visible notice; invalid structured output → rejected, bounded retries only.

## Future compatibility

The domain model (sync cursors, idempotency keys, audit events, executors) is designed so a future event-driven MONITOR → PLAN → PROPOSE → APPROVE → ACT → VERIFY lifecycle can be added with schedulers/webhooks/queues — never an always-running LLM process. Edition packs plug in via configuration (taxonomy, prompts, priority rules, sections, copy), not forks.
