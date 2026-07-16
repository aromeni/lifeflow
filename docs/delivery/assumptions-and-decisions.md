# Assumptions and Decisions Log

**Status:** Stage 0 · **Date:** 2026-07-15

Per the operating protocol, no more than five genuinely architecture/scope-blocking decisions were identified. Each has a recommendation adopted as a **documented, reversible assumption** so Stage 0 could proceed without blocking on the user. Accepted outcomes are formalised in [../architecture/adr/0001-architecture.md](../architecture/adr/0001-architecture.md).

## The five blocking decisions

### BD1 — Application sign-in model

**Question:** How do users authenticate to LifeFlow itself (separate from Gmail/Calendar grants)?
**Recommendation (adopted, ADR D3):** Google Sign-In (OIDC, `openid email profile` only), with connector scopes requested incrementally later; demo mode uses a dev-seeded local session.
**Why:** target users are Gmail users; avoids operating a password store; keeps consent granular.
**Reversibility:** high — email/magic-link can be added behind the same server-side session layer.

### BD2 — Background job architecture

**Question:** Celery, Dramatiq, or arq — and when does Redis enter?
**Recommendation (adopted, ADR D2):** no queue or Redis until Stage 8; on-demand generation runs in-process first; adopt **arq** when scheduled briefs arrive, confirmed by ADR 0003 at that point.
**Why:** avoids operating infrastructure with no current requirement; arq fits the async stack and small job volumes.
**Reversibility:** high — job entry points live in `workers/` and call domain services; the runner is swappable.

### BD3 — LLM provider strategy

**Question:** Which provider first, and how hard is the abstraction boundary?
**Recommendation (adopted, ADR D4):** provider-neutral `LLMProvider` protocol; **mock provider is the default** (demo mode + all CI); Anthropic is the first real implementation.
**Why:** required by the skill's AI-layer rules; keeps every stage gate credential-free.
**Reversibility:** high by construction.

### BD4 — Hosting and data residency

**Question:** Where will production run, given a UK-based user base and GDPR constraints?
**Recommendation (adopted, ADR D8):** defer provider choice to Stage 11 (ADR 0004) with **UK/EU data residency as a binding constraint**; Docker Compose covers Stages 1–10.
**Why:** nothing before Stage 11 depends on hosting; deciding now would be speculation.
**Reversibility:** total until Stage 11.

### BD5 — Gmail ingestion window and scope set

**Question:** How much mailbox history may the MVP read, with which exact scopes?
**Recommendation (adopted, ADR D6 / threat model T20):** default window of the **last 14 days** of messages (bounded pagination, sync cursors thereafter); scopes fixed at `gmail.readonly`, `gmail.compose` (draft creation only), `calendar.readonly`, `calendar.events`.
**Why:** minimum-scope, minimum-retention principle; 14 days covers stale-follow-up detection (5+ days) with margin.
**Reversibility:** high — the window is a configuration value surfaced in the privacy screen.

## Working assumptions (reversible, not decision-blocking)

| ID | Assumption | Basis | Where recorded |
|---|---|---|---|
| A1 | Single developer + Claude Code as delivery team; GitHub for hosting/CI when a remote is created | Repo context | stage plan |
| A2 | Primary locale `en-GB`, default timezone `Europe/London`; UTC storage everywhere | Primary persona | personas, ADR |
| A3 | Repo will be initialised as a git repository at Stage 1 (it is not one today); no commit without explicit request | Skill protocol | stage plan |
| A4 | Demo dataset is authored fiction (UK-flavoured names/companies), never derived from real mail | Skill §13 | mvp-scope |
| A5 | Stale follow-up threshold defaults to 5 days; deadline-proximity boost begins at 72h | Skill §8 examples | to be tested in Stage 4 |
| A6 | Retention default: imported source items expire 30 days after last sync unless referenced by an approved action; user-configurable later | Privacy-by-design | threat model T15 |
| A7 | Proposal expiry default: 7 days after creation | Policy engine needs a bound | mvp-scope risk table |
| A8 | Priority formula starts at the skill's suggested weights (0.30 urgency, 0.25 importance, 0.20 explicit request, 0.15 deadline proximity, 0.10 relationship/context), normalised [0,1], with reason codes; tuned only via eval evidence | Skill §8 | Stage 4 |
| A9 | English-language email content is the MVP target; non-English content is surfaced but marked low confidence | Persona | Stage 4 |
| A10 | "LifeFlow Chief of Staff Suite" (directory name) is the working umbrella; product name in-app is **LifeFlow AI** | Skill mission | vision |
| A11 | Sessions are server-signed cookies (Starlette SessionMiddleware, httpOnly, SameSite=Lax, Secure in production, 8h expiry); no session table until a revocation requirement appears | Simplicity (Stage 2) | main.py, stage-02 report |
| A12 | CSRF defence is the custom-header pattern (`X-LifeFlow-CSRF: 1` required on all state-changing requests) plus SameSite=Lax — appropriate for a JSON-only API; revisit if form posts ever appear | Threat model T7 (Stage 2) | security/csrf.py |
| A13 | Tests run against a dedicated `lifeflow_test` database on the dev Postgres container, recreated each session, so development data is never touched | Testing safety (Stage 2) | tests/conftest.py |
| A14 | Demo sign-in reuses dev-login, so demo mode currently requires ENVIRONMENT=development; an anonymous demo-session path for deployed environments is deferred until a deployment exists (Stage 10/11) | Simplicity (Stage 3) | stage-03 report |
| A15 | Web↔API is cross-origin in dev (3000→8010) protected by CORS pinned to the web origin, credentialed fetch, and the custom CSRF header; demo dataset dates are day-offsets materialised against a "today" anchor in the user's timezone | Stage 3 design | main.py, connectors/synthetic.py |

## Open questions deliberately deferred (with owner stage)

- ~~Evaluation acceptance targets~~ — **ratified 2026-07-16 in [ADR 0002](../architecture/adr/0002-evaluation-targets.md)** after the deterministic baseline; real-model metrics still pending an Anthropic key (before the Stage 10 gate).
- Job runner confirmation — ADR 0003 at Stage 8.
- Production hosting provider + deployment shape — ADR 0004 at Stage 11.
- Google OAuth app verification timeline — begins during Stage 7; pilot can run on test users meanwhile.
- Entitlements/billing model — interfaces only, Stage 11; no billing implementation without explicit request.

Nothing in this log weakens the safety invariants: approval-gated side effects, prohibited high-risk actions, minimum scopes, and audit coverage are not assumptions — they are fixed requirements.
