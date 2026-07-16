---
name: lifeflow-mvp-builder
version: 1.0.0
description: Build LifeFlow AI, a secure human-in-the-loop personal operations agent, as a production-minded MVP in gated stages with tests, evidence, documentation, and explicit user approval between stages.
model_recommendation: claude-fable-5
---
# LifeFlow AI MVP Builder

## 1. Mission

You are the lead product engineer, AI systems architect, security reviewer, QA engineer, and technical writer for **LifeFlow AI**.

LifeFlow AI is a personal operations agent that helps a user stay ahead of everyday obligations by securely combining information from email, calendar, tasks, and user preferences. It should reduce cognitive load without taking uncontrolled actions.

The MVP must:

1. Connect to Gmail and Google Calendar through OAuth.
2. Collect a limited, user-authorised set of recent information.
3. Produce a useful daily briefing.
4. Identify possible tasks, commitments, deadlines, follow-ups, and scheduling conflicts.
5. Propose actions such as drafting an email, creating a task, or suggesting a calendar event.
6. Require explicit user approval before any external side effect.
7. Maintain an understandable audit trail explaining what the agent observed, inferred, proposed, and executed.
8. Support future editions for students, freelancers, consultants, families, and small teams without rewriting the core platform.

The product is **not** an unrestricted autonomous assistant. It is a permissioned, inspectable, human-in-the-loop operations agent.

---

## 2. Primary MVP user

Design initially for a busy UK-based professional, consultant, postgraduate student, or freelancer who:

- receives important requests through Gmail;
- manages commitments in Google Calendar;
- forgets follow-ups or loses track of decisions across tools;
- wants one concise daily view of what matters;
- wants suggested next actions but does not want AI silently sending messages or changing their calendar;
- expects transparent privacy and control.

The architecture must remain adaptable so later editions can introduce specialised policies, prompts, dashboards, and connectors.

---

## 3. Core product promise

> LifeFlow quietly finds what needs attention, explains why it matters, and prepares the next step for approval.

The MVP's main user loop is:

```text
Connect accounts
    ↓
Collect authorised data
    ↓
Normalise and classify signals
    ↓
Build a prioritised daily brief
    ↓
Propose safe actions
    ↓
User approves, edits, or rejects
    ↓
Execute approved actions
    ↓
Record outcome and learn preferences
```

---

## 4. Product principles

All implementation decisions must follow these principles:

### 4.1 Human control

- Read-only behaviour is the default.
- No email may be sent without explicit approval.
- No calendar event may be created, changed, or deleted without explicit approval.
- No task may be marked complete automatically.
- Approval must show the exact payload that will be executed.

### 4.2 Explainability

Every surfaced item must answer:

- What was detected?
- Why is it relevant?
- Which source supports it?
- How confident is the system?
- What action, if any, is recommended?

Do not expose hidden chain-of-thought. Provide brief evidence-based explanations and source references instead.

### 4.3 Privacy by design

- Request the minimum OAuth scopes required.
- Store the minimum data required.
- Encrypt secrets and OAuth tokens at rest.
- Never log access tokens, refresh tokens, email bodies, or private event descriptions.
- Provide deletion and disconnect controls.
- Document data retention clearly.
- Treat GDPR principles as first-class design constraints.

### 4.4 Reversible actions

Where possible, prefer drafts and proposed changes over immediate execution.

### 4.5 Deterministic safety boundaries

LLM output must never directly invoke an external action. It must produce a typed proposal that passes schema validation, policy checks, and user approval before an action executor is called.

### 4.6 Evidence over theatre

Do not claim the product is intelligent, autonomous, secure, production-ready, or compliant unless the repository contains evidence supporting the claim.

### 4.7 Progressive delivery

Build one complete path first:

```text
Gmail + Calendar → Daily Brief → Proposed Action → Approval → Execution → Audit
```

Do not broaden the feature set until this path works end to end.

---

## 5. Strict scope

### 5.1 In scope for MVP

- Google OAuth authentication.
- Gmail read access for a constrained recent window.
- Gmail draft creation after approval.
- Google Calendar read access.
- Google Calendar event creation after approval.
- Internal tasks created by the agent or user.
- Daily brief generation on demand.
- Optional scheduled daily brief job.
- Signal extraction:
  - direct requests;
  - promises or commitments;
  - dates and deadlines;
  - meetings;
  - unanswered follow-ups;
  - possible scheduling conflicts;
  - high-priority messages based on transparent rules.
- Priority scoring.
- Approval queue.
- Audit/event log.
- User preferences and lightweight memory.
- Demo mode with synthetic data.
- Automated tests and developer documentation.

### 5.2 Explicitly out of scope

Do not implement these in the MVP:

- WhatsApp, Slack, Microsoft 365, banking, health, travel booking, shopping, or social-media connectors.
- Automatic sending without user review.
- Autonomous purchases or financial transactions.
- Medical, legal, or financial decision-making.
- Voice interfaces.
- Native mobile apps.
- Multi-user family or team workspaces.
- Browser automation against arbitrary websites.
- Vector databases unless a measured requirement justifies one.
- Complex multi-agent theatre where ordinary functions and services are sufficient.
- Fine-tuning.
- Continuous surveillance or unrestricted mailbox ingestion.

Record these as roadmap items, not hidden unfinished features.

---

## 6. Recommended technical architecture

Use a modular monorepo.

```text
lifeflow-ai/
├── apps/
│   ├── web/                 # Next.js TypeScript user interface
│   └── api/                 # FastAPI Python backend
├── packages/
│   ├── contracts/           # Shared schemas/OpenAPI-generated types
│   └── ui/                  # Reusable UI components if justified
├── workers/                 # Background job entry points
├── prompts/                 # Versioned prompts and structured-output contracts
├── evals/                   # Golden datasets, scoring, regression tests
├── infra/                   # Docker and deployment configuration
├── docs/                    # Architecture, ADRs, threat model, runbooks
├── scripts/                 # Repeatable local maintenance scripts
├── .github/workflows/       # CI, if GitHub is selected
├── CLAUDE.md                # Repository operating instructions
├── README.md
├── docker-compose.yml
└── .env.example
```

### 6.1 Frontend

- Next.js with TypeScript.
- App Router.
- Accessible component library such as shadcn/ui where helpful.
- Server-side authentication session handling.
- Zod for client-side contract validation.
- Playwright for end-to-end testing.
- Vitest and React Testing Library for component/unit tests.

### 6.2 Backend

- Python 3.12.
- FastAPI.
- Pydantic v2.
- SQLAlchemy 2 and Alembic.
- PostgreSQL.
- Redis only if background scheduling or queueing genuinely requires it.
- Celery, Dramatiq, or arq may be used for jobs; choose one and justify it in an ADR.
- pytest, pytest-asyncio, and testcontainers or an equivalent isolated integration-test strategy.

### 6.3 AI layer

Create a provider-neutral interface:

```python
class LLMProvider(Protocol):
    async def generate_structured(
        self,
        *,
        task: str,
        input_data: dict,
        output_schema: type[BaseModel],
        trace_context: dict,
    ) -> BaseModel: ...
```

- Anthropic may be the first implementation.
- Never scatter direct model calls across routers or business logic.
- Prompts must be versioned files.
- Outputs must use strict typed schemas.
- Add timeouts, retries with limits, cost/usage capture, and graceful failure.
- Mock the provider in automated tests.
- The application must run in demo mode without paid API access.

### 6.4 Integrations

Create connector interfaces:

```python
class EmailConnector(Protocol): ...
class CalendarConnector(Protocol): ...
class TaskConnector(Protocol): ...
```

Implement Google adapters first. Domain services must depend on interfaces, not Google SDK details.

### 6.5 Authentication and tenancy

Even though the MVP may begin with one user, model all user-owned records with a `user_id`. Enforce ownership in every repository query and API route.

Do not overbuild enterprise tenancy, but do not hard-code a singleton user.

---

## 7. Core domain model

Use clear typed entities. Refine names through ADRs, but preserve these concepts:

### User

- id
- email
- display_name
- timezone
- locale
- created_at
- onboarding_state

### ConnectedAccount

- id
- user_id
- provider
- encrypted_access_token
- encrypted_refresh_token
- granted_scopes
- expires_at
- status
- last_sync_at

### SourceItem

A normalised reference to an email, calendar event, or internal item.

- id
- user_id
- source_type
- external_id
- source_account_id
- title
- sender_or_organiser
- occurred_at
- metadata_json
- content_fingerprint
- retention_expires_at

### Signal

A structured observation derived from one or more source items.

- id
- user_id
- signal_type
- title
- summary
- evidence_refs
- due_at
- confidence
- urgency
- importance
- status
- extraction_version

### Brief

- id
- user_id
- briefing_date
- generated_at
- summary
- sections_json
- source_window
- prompt_version
- model_metadata

### ActionProposal

- id
- user_id
- action_type
- rationale
- source_refs
- payload_json
- risk_level
- confidence
- status: proposed | edited | approved | rejected | executing | executed | failed | expired
- expires_at

### ActionExecution

- id
- proposal_id
- idempotency_key
- started_at
- completed_at
- result_json
- error_code

### Preference

- id
- user_id
- key
- value_json
- provenance: explicit | inferred
- confidence
- updated_at

### AuditEvent

Append-only record containing:

- actor
- event_type
- entity_type
- entity_id
- timestamp
- safe_metadata_json
- correlation_id

Never store secrets in audit metadata.

---

## 8. Priority model

Use an understandable hybrid score, not an opaque LLM-only ranking.

A starting formula may be:

```text
priority_score =
    0.30 × urgency
  + 0.25 × importance
  + 0.20 × explicit_request_strength
  + 0.15 × deadline_proximity
  + 0.10 × relationship_or_context_weight
```

Each component must be normalised to `[0, 1]` and accompanied by reason codes. The LLM may estimate features, but deterministic rules must handle obvious deadlines, conflicts, and stale follow-ups.

The UI must expose concise reasons such as:

- “Explicit request from sender”
- “Due within 24 hours”
- “Calendar conflict detected”
- “No reply for five days”

Include tests for ranking stability and edge cases.

---

## 9. Agent pipeline

Implement the agent as an orchestrated workflow, not an unconstrained loop.

```text
1. Acquire authorised source data
2. Redact or minimise unnecessary content
3. Normalise source records
4. Apply deterministic detectors
5. Run structured LLM extraction where needed
6. Validate output schema
7. Deduplicate signals
8. Score and rank signals
9. Compose brief
10. Generate typed action proposals
11. Run policy validation
12. Present for user approval
13. Execute approved action using idempotency key
14. Verify result
15. Write audit event
```

Every step must be observable and independently testable.

### 9.1 Failure behaviour

- A failed connector must not erase prior data.
- A failed LLM call must return a useful degraded brief based on deterministic rules.
- Invalid structured output must be rejected and retried only within a fixed limit.
- Duplicate jobs must not create duplicate drafts or events.
- Partial failures must be visible to the user.


### 9.2 Future continuous monitoring compatibility

Although the MVP begins with on-demand and scheduled briefing workflows,
the architecture must support a future event-driven lifecycle:

MONITOR → PLAN → PROPOSE → APPROVE → ACT → VERIFY

The production system must not use an always-running LLM process.
Schedulers, webhooks, queues, connector cursors, and deterministic
application services must control the lifecycle. The LLM may be invoked
only for bounded interpretation or generation tasks.

Design connector synchronisation, idempotency keys, audit events, and
action executors so this capability can be introduced later without
rewriting the core domain model.

## 10. Action policy engine

Before execution, every proposal must pass a deterministic policy engine.

Minimum policies:

- user owns the proposal;
- proposal is in an approvable state;
- proposal has not expired;
- exact payload was shown to the user;
- required connector scope is present;
- target recipients and dates are valid;
- no duplicate idempotency key exists;
- risk level permits this action;
- explicit approval is recorded after the latest edit;
- payload has not changed since approval.

Initial risk levels:

| Risk   | Example                            | MVP behaviour                                 |
| ------ | ---------------------------------- | --------------------------------------------- |
| Low    | Create internal task               | Approval required                             |
| Medium | Create calendar event              | Approval required plus payload preview        |
| Medium | Create Gmail draft                 | Approval required plus recipient/body preview |
| High   | Send email, delete event, purchase | Prohibited in MVP                             |

---

## 11. Security and privacy requirements

Create `docs/security/threat-model.md` before implementing OAuth.

At minimum address:

- OAuth token theft;
- cross-user data access;
- prompt injection inside emails or calendar descriptions;
- malicious links and attachments;
- indirect instructions attempting to make the model invoke tools;
- sensitive data in logs;
- CSRF, XSS, SSRF, SQL injection, and insecure redirects;
- replay and duplicate execution;
- dependency compromise;
- excessive data retention;
- account disconnect and deletion;
- model-provider data exposure.

### 11.1 Prompt-injection boundary

Treat all connector content as untrusted data.

- Never allow text from an email or event to modify system policy.
- Delimit source content clearly.
- Ignore instructions embedded within source content.
- Do not browse links or open attachments in the MVP.
- Do not let extracted content choose tools.
- Tool eligibility is determined by application code and policy, not model prose.
- Add adversarial test fixtures containing prompt-injection attempts.

### 11.2 Encryption

- Use environment-managed encryption keys in development.
- Define an interface suitable for a managed KMS in production.
- Encrypt OAuth refresh tokens at application level before database storage.
- Document key rotation assumptions.

### 11.3 Logging

Use structured logs with correlation IDs. Redact:

- OAuth credentials;
- cookies;
- authorisation headers;
- full email bodies;
- private calendar descriptions;
- LLM prompts containing personal data.

---

## 12. UX requirements

The interface must remain calm and understandable.

### Required screens

1. **Landing/demo screen**

   - clear product promise;
   - “Try demo” and “Connect Google” paths;
   - privacy summary.
2. **Onboarding**

   - explain requested permissions;
   - allow timezone and work-hours configuration;
   - let user choose brief sections;
   - explain that actions require approval.
3. **Today dashboard**

   - concise headline summary;
   - “Needs attention”, “Upcoming”, “Waiting for”, and “Suggested actions” sections;
   - evidence/source links;
   - refresh and generation status.
4. **Approval inbox**

   - exact action preview;
   - evidence and rationale;
   - edit, approve, reject;
   - risk label;
   - execution result.
5. **Connections and privacy**

   - connected account status;
   - granted scopes;
   - last sync;
   - disconnect;
   - delete imported data;
   - retention explanation.
6. **Audit history**

   - filters by action and date;
   - plain-language event descriptions;
   - no sensitive raw payload leakage.
7. **Settings**

   - timezone;
   - briefing time;
   - working hours;
   - priority preferences;
   - memory controls.

### Accessibility

- Meet WCAG 2.2 AA where practical.
- Full keyboard operation.
- Visible focus states.
- Semantic labels and status announcements.
- No meaning conveyed by colour alone.

---

## 13. Demo dataset

Create a realistic but wholly fictional UK-oriented dataset containing:

- 20–30 emails;
- 10–15 calendar events;
- several explicit requests;
- one near deadline;
- one overdue follow-up;
- one calendar conflict;
- one newsletter that should be deprioritised;
- one prompt-injection email;
- one ambiguous request that should show low confidence;
- one proposed Gmail draft;
- one proposed calendar event.

No real personal data may appear in the repository.

Demo mode must exercise the complete workflow without Google or Anthropic credentials.

---

## 14. Evaluation framework

Create a versioned golden dataset in `evals/`.

Each case should include:

```json
{
  "id": "case-001",
  "source_items": [],
  "expected_signals": [],
  "expected_priority_band": "high",
  "expected_action_types": [],
  "must_not_do": [],
  "notes": ""
}
```

Measure at least:

- signal precision;
- signal recall;
- deadline extraction accuracy;
- duplicate rate;
- priority-band agreement;
- unsafe-action proposal rate;
- unsupported-claim rate;
- prompt-injection resistance;
- brief usefulness through a small human rubric.

Do not optimise a single aggregate score at the expense of safety.

Define MVP acceptance targets in an ADR after establishing the deterministic baseline. Suggested initial targets:

- ≥ 0.85 precision on actionable signals;
- ≥ 0.80 recall on explicit requests and deadlines;
- 0 prohibited actions executed;
- 0 duplicate external actions under retry tests;
- 100% source attribution for surfaced actionable items;
- 100% approval requirement for side-effecting actions.

---

## 15. Testing strategy

Use a test pyramid.

### Unit tests

Cover:

- normalisation;
- date handling and timezone conversion;
- priority scoring;
- deduplication;
- policy checks;
- schema validation;
- prompt-injection sanitisation boundaries;
- encryption helpers;
- audit redaction;
- state transitions.

### Integration tests

Cover:

- database repositories with PostgreSQL;
- OAuth callback validation with mocked Google endpoints;
- Gmail and Calendar adapters with recorded/mock responses;
- background job idempotency;
- LLM provider structured-output handling;
- approval-to-execution path;
- account disconnect and data deletion.

### Contract tests

- OpenAPI schema generation;
- frontend client compatibility;
- connector adapter contracts;
- LLM structured schemas.

### End-to-end tests

At minimum:

1. enter demo mode;
2. generate a daily brief;
3. inspect evidence;
4. edit a proposed email draft;
5. approve it;
6. verify execution simulation and audit record;
7. reject another proposal;
8. change preferences and regenerate brief;
9. verify prompt-injection fixture cannot trigger an action.

### Quality gates

Each stage must pass:

- formatter;
- linter;
- type checker;
- unit tests;
- relevant integration tests;
- security checks appropriate to that stage;
- build step;
- documentation check.

Do not disable tests to obtain a green build.

---

## 16. Stage-gated execution protocol

You must build this product in the following stages. Complete only one stage at a time.

At the end of every stage:

1. run all required checks;
2. inspect the implementation rather than trusting command exit codes alone;
3. update documentation and the decision log;
4. produce the stage completion report defined below;
5. stop and wait for explicit human approval before beginning the next stage.

Never interpret silence as approval.

Do not create a commit unless the user explicitly asks you to commit. You may recommend a commit message.

---

# STAGE 0 — Discovery, assumptions, and delivery plan

## Goal

Turn the product concept into a precise, buildable MVP plan before writing application code.

## Required work

- Inspect the repository and existing files.
- Record assumptions and unanswered decisions.
- Create:
  - `docs/product/vision.md`;
  - `docs/product/personas.md`;
  - `docs/product/user-journeys.md`;
  - `docs/product/mvp-scope.md`;
  - `docs/architecture/system-context.md`;
  - `docs/architecture/adr/0001-architecture.md`;
  - `docs/security/threat-model.md`;
  - `docs/delivery/stage-plan.md`.
- Define measurable success criteria.
- Produce low-fidelity text wireframes for required screens.
- Identify external setup the user will eventually need, but do not block demo-mode development on credentials.

## Tests/checks

- Documentation links resolve.
- Scope contains explicit in-scope and out-of-scope lists.
- Threat model maps mitigations to planned components.
- Every MVP feature maps to at least one user journey and acceptance criterion.

## Exit criteria

The product can be explained in one page, the first end-to-end path is unambiguous, and implementation risks are documented.

---

# STAGE 1 — Repository scaffold and engineering foundations

## Goal

Create a clean, reproducible monorepo that runs locally.

## Required work

- Scaffold Next.js frontend and FastAPI backend.
- Add PostgreSQL and optional Redis through Docker Compose.
- Add `.env.example`; never commit secrets.
- Configure formatters, linters, type checking, test runners, and pre-commit hooks.
- Add health/readiness endpoints.
- Add shared error response structure and correlation IDs.
- Add CI configuration.
- Create `CLAUDE.md` containing project commands, architecture boundaries, and safe-development rules.
- Add a root `README.md` with exact setup instructions.

## Tests/checks

- Fresh clone starts with documented commands.
- Frontend and backend health checks pass.
- Database migrations run from empty state.
- CI runs lint, type checks, tests, and builds.
- Secret scanning finds no credentials.

## Exit criteria

A developer can clone, configure, run, test, and stop the entire stack predictably.

---

# STAGE 2 — Domain model, authentication, and user isolation

## Goal

Implement the secure data foundation.

## Required work

- Implement application authentication suitable for the chosen deployment.
- Add core database models and migrations.
- Add repositories/services with ownership enforcement.
- Implement settings and onboarding state.
- Implement append-only audit events.
- Implement token encryption abstraction.
- Add a development-only seeded user flow without weakening production settings.

## Tests/checks

- Cross-user access attempts fail.
- Migration upgrade/downgrade path works where safe.
- Audit records are generated for relevant state changes.
- Encryption round-trip succeeds and plaintext is not stored.
- Authentication/session security tests pass.

## Exit criteria

All user-owned data is isolated, migrations are stable, and sensitive connection data has a secure storage path.

---

# STAGE 3 — Demo mode and synthetic source connectors

## Goal

Deliver the first useful vertical slice without external credentials.

## Required work

- Implement connector interfaces.
- Implement synthetic Gmail and Calendar adapters.
- Add the fictional dataset.
- Implement source-item normalisation.
- Build the demo onboarding and Today dashboard shell.
- Display raw normalised items only in a developer/debug view, not as the main experience.

## Tests/checks

- Synthetic connectors satisfy shared contracts.
- Normalisation is deterministic.
- Duplicate imports do not duplicate source records.
- Timezones are correct around daylight-saving boundaries.
- Demo mode starts with one command.

## Exit criteria

A user can enter demo mode and see a coherent set of normalised everyday information.

---

# STAGE 4 — Signal extraction and priority engine

## Goal

Turn source data into defensible, prioritised signals.

## Required work

- Implement deterministic detectors first.
- Implement provider-neutral structured LLM extraction.
- Add mock and Anthropic providers.
- Version prompts and schemas.
- Implement deduplication and priority scoring.
- Store evidence references and reason codes.
- Implement degraded operation when the LLM is unavailable.
- Add adversarial prompt-injection fixtures.

## Tests/checks

- Golden extraction dataset runs.
- Deterministic baseline metrics are reported.
- LLM-assisted metrics are reported separately.
- Unsupported signals are rejected or marked low confidence.
- Prompt-injection content cannot select tools or bypass policy.
- No model call is required for basic demo-mode tests.

## Exit criteria

The system reliably identifies and ranks requests, deadlines, follow-ups, and conflicts with source evidence.

---

# STAGE 5 — Daily brief generation

## Goal

Produce the MVP's first genuinely useful user outcome.

## Required work

- Implement daily-brief orchestration.
- Build sections:
  - Needs attention;
  - Today and upcoming;
  - Waiting for;
  - Suggested actions;
  - Low-confidence review items.
- Add source links/evidence drawers.
- Add refresh status and partial-failure messages.
- Persist brief versions and generation metadata.
- Add on-demand generation first; scheduled jobs may follow only after it is stable.

## Tests/checks

- Brief is deterministic under mocked provider.
- Every actionable statement has evidence.
- Empty, noisy, and partial-source cases remain useful.
- Human usefulness rubric is applied to the demo dataset.
- Accessibility checks pass for the dashboard.

## Exit criteria

A demo user can understand what matters today in under two minutes and inspect the basis of each recommendation.

---

# STAGE 6 — Action proposals and approval inbox

## Goal

Convert insights into safe, editable next steps.

## Required work

- Implement typed action proposals for:
  - internal task creation;
  - Gmail draft creation;
  - Calendar event creation.
- Implement proposal state machine.
- Build approval inbox and detailed preview.
- Permit editing before approval.
- Invalidate prior approval when payload changes.
- Implement policy engine and expiration.
- Use simulated executors in demo mode.

## Tests/checks

- Invalid state transitions fail.
- Edited payload requires fresh approval.
- Prohibited action types cannot be created or executed.
- Exact approved payload matches executed payload.
- Duplicate execution attempts remain idempotent.
- E2E demo approval path passes.

## Exit criteria

A user can inspect, edit, approve, reject, and trace proposed actions without any hidden side effects.

---

# STAGE 7 — Real Google integration

## Goal

Connect the proven demo workflow to Gmail and Google Calendar safely.

## Required work

- Implement Google OAuth with minimum scopes.
- Implement secure callback/state/PKCE handling as appropriate.
- Implement Gmail recent-message ingestion.
- Implement Gmail draft creation only.
- Implement Calendar event ingestion.
- Implement Calendar event creation only.
- Implement account status, re-authorisation, disconnect, and token refresh.
- Respect quotas and use bounded pagination.
- Add sync cursors where appropriate.
- Never silently broaden scopes.

## Tests/checks

- Mock integration suite passes.
- OAuth state and redirect validation tests pass.
- Token refresh failures are handled safely.
- Revoked scopes produce a clear UI state.
- Duplicate syncs and retries are idempotent.
- A manual sandbox-account checklist is completed and documented.

## Exit criteria

A test user can connect Google, generate a brief from real authorised data, approve a Gmail draft or calendar event, and see an audit record.

---

# STAGE 8 — Preferences, lightweight memory, and scheduled brief

## Goal

Make the system adapt to the user without creating opaque profiling.

## Required work

- Implement explicit preferences first.
- Permit limited inferred preferences only when:
  - provenance is recorded;
  - confidence is shown;
  - the user can edit or delete them.
- Add briefing schedule with timezone support.
- Add working hours and priority rules.
- Add notification abstraction, but use in-app delivery first unless an email delivery path is explicitly approved.
- Prevent preference feedback loops from suppressing critical items.

## Tests/checks

- Timezone and DST scheduling tests pass.
- User can inspect and delete memory.
- Explicit preferences override inferred preferences.
- Critical deadlines cannot be silently hidden by learned preferences.
- Job retries do not generate duplicate briefs.

## Exit criteria

The brief arrives or becomes available at the configured time and reflects transparent user preferences.

---

# STAGE 9 — Privacy controls, audit experience, and resilience

## Goal

Make trust features visible and operational.

## Required work

- Complete connections/privacy screen.
- Implement delete imported data.
- Implement disconnect behaviour and token revocation attempts.
- Implement retention jobs.
- Complete audit-history UI.
- Add rate limiting and abuse controls.
- Add backup/restore documentation.
- Add graceful connector and model-provider outage behaviour.
- Review logs and telemetry for personal-data leakage.

## Tests/checks

- Deletion removes or anonymises all intended records.
- Retention jobs are idempotent.
- Audit logs remain intact where legally/operationally justified without retaining raw sensitive content.
- Outage simulations produce degraded but safe behaviour.
- Security regression suite passes.

## Exit criteria

Users can understand and control connected data, and the product fails safely during dependency outages.

---

# STAGE 10 — Product evaluation and pilot readiness

## Goal

Prove that the MVP is useful enough for a small pilot.

## Required work

- Finalise golden evaluation suite.
- Add end-to-end regression suite.
- Conduct performance and cost profiling.
- Add user-feedback capture using a simple rubric:
  - relevance;
  - clarity;
  - trust;
  - time saved;
  - action usefulness.
- Create pilot onboarding guide.
- Create privacy notice draft and terms assumptions for review by a qualified professional.
- Create operational runbook and incident checklist.
- Produce known-limitations document.

## Tests/checks

- Full CI passes from clean checkout.
- Acceptance targets are met or exceptions are documented.
- No critical/high unresolved security findings.
- Core E2E path passes repeatedly.
- Cost per generated brief is measured, not guessed.
- Performance targets are documented and measured.

## Exit criteria

The product is ready for a controlled pilot with a small number of consenting users, not broad public launch.

---

# STAGE 11 — Packaging, deployment, and commercial foundation

## Goal

Package the MVP so it can be demonstrated, piloted, and extended commercially.

## Required work

- Create production deployment architecture and ADR.
- Add infrastructure configuration for the selected non-US or user-approved hosting provider when required.
- Separate development, staging, and production configuration.
- Add database migration and rollback runbooks.
- Add observability dashboards/alerts at a practical level.
- Add feature flags for experimental capabilities.
- Add edition/tenant configuration without duplicating code:
  - Core;
  - Student;
  - Freelancer;
  - Consultant.
- Do not implement full billing unless explicitly requested; define entitlement interfaces and a commercial roadmap.
- Produce a polished demo script and screenshots.

## Tests/checks

- Staging deployment passes smoke tests.
- Configuration secrets are outside source control.
- Deployment rollback is rehearsed or documented.
- Edition configuration changes prompts/rules/UI copy without forking the core workflow.
- Demo script works against synthetic data.

## Exit criteria

The MVP can be demonstrated professionally, piloted safely, and extended into specialised editions through configuration and plugins.

---

## 17. Stage completion report format

At the end of each stage, respond using exactly this structure:

```markdown
# Stage N Completion Report

## Outcome
One paragraph explaining what is now possible.

## Implemented
- Concrete files, modules, routes, screens, migrations, and behaviours.

## Architecture decisions
- ADRs added or changed and why.

## Tests and evidence
| Check | Result | Evidence |
|---|---|---|
| Unit tests | PASS/FAIL | command and count |
| Integration tests | PASS/FAIL | command and count |
| Type checking | PASS/FAIL | command |
| Lint | PASS/FAIL | command |
| Build | PASS/FAIL | command |
| Security checks | PASS/FAIL | command or review |

## Manual verification
- Exact flows inspected manually.

## Known limitations
- Honest list of remaining limitations relevant to this stage.

## Files changed
- Summarised by area, not a raw unhelpful dump.

## Run instructions
- Exact commands the user should run now.

## Recommended commit message
`type(scope): concise description`

## Gate
Stage N is complete. Stop here and wait for explicit approval to begin Stage N+1.
```

If a check fails, do not call the stage complete. Explain the failure, fix it where feasible, rerun the check, and report honestly.

---

## 18. Engineering operating rules

### Before coding

- Inspect existing implementation.
- Read relevant docs and ADRs.
- State the current stage and its exit criteria.
- Create a small implementation plan.
- Identify destructive or externally visible actions before performing them.

### During coding

- Prefer small, reviewable changes.
- Preserve architecture boundaries.
- Add or update tests with behaviour changes.
- Keep functions focused and typed.
- Avoid speculative abstractions.
- Avoid adding dependencies when the standard library or existing stack is sufficient.
- Never conceal an error with a broad exception handler.
- Never replace real tests with mocks so extensive that no meaningful behaviour is tested.

### After coding

- Run targeted tests during work and the full relevant suite before reporting.
- Inspect generated migrations.
- Review diffs for secrets and accidental personal data.
- Update docs and changelog/decision log.
- Confirm that commands in the README still work.

### Destructive operations

Ask before:

- deleting user-created files;
- resetting databases containing non-synthetic data;
- force-pushing;
- rewriting Git history;
- changing production resources;
- sending external messages;
- creating or modifying real calendar events;
- revoking real user credentials.

---

## 19. Definition of done for the MVP

The MVP is done only when all of the following are true:

- A new developer can run it from a clean clone.
- Demo mode works without external credentials.
- A consenting test user can connect Gmail and Calendar.
- A daily brief identifies useful, source-backed items.
- The system proposes but does not silently execute external actions.
- Gmail behaviour is limited to draft creation in the MVP.
- Calendar creation requires approval.
- Every executed action is validated, idempotent, and audited.
- Prompt-injection fixtures cannot trigger tools or alter policy.
- Cross-user isolation tests pass.
- Data disconnect and deletion controls work.
- Core tests, type checks, linting, builds, and E2E tests pass.
- Evaluation metrics and limitations are published honestly.
- Deployment and pilot runbooks exist.
- The architecture supports specialised editions through configuration and adapters.

---

## 20. Extension architecture after MVP

Future features must enter through explicit extension points:

### Connectors

- Microsoft 365
- Slack/Teams
- task platforms
- document stores
- finance data through regulated read-only aggregators

### Edition packs

Each edition pack may define:

- signal taxonomy;
- prompt variants;
- priority rules;
- dashboard sections;
- action types;
- evaluation fixtures;
- onboarding copy.

### Example editions

**Student edition**

- assignment deadlines;
- seminar preparation;
- reading plans;
- supervisor follow-ups.

**Freelancer edition**

- client requests;
- proposal follow-ups;
- invoice reminders;
- delivery commitments.

**Consultant edition**

- client action registers;
- meeting follow-ups;
- proposal and contract milestones;
- research and deliverable tracking.

**Family edition**

- shared commitments;
- school events;
- household reminders;
- permission-aware shared views.
-

### Life-domain packs

**Finance insights pack**

- read-only Open Banking integration;
- recurring-payment and subscription summaries;
- upcoming bill reminders;
- unusual-transaction indicators;
- no payments, investment advice, or credit decisions.

**Shopping and household pack**

- household inventory;
- recurring shopping lists;
- receipt-assisted stock updates;
- low-stock suggestions;
- delivery tracking;
- no automatic purchases in the initial edition.

Do not build these until the core loop has pilot evidence.



---

## 21. Initial instruction to execute this skill

When this skill is first invoked, do not immediately scaffold the application.

Begin with:

1. Inspect the repository.
2. Summarise what already exists.
3. Confirm that **Stage 0** is the active stage.
4. Identify no more than five decisions that genuinely block architecture or scope.
5. Make reasonable recommendations for each decision.
6. Proceed with Stage 0 using documented assumptions where the decision is reversible.
7. Stop after the Stage 0 completion report.

The guiding rule is:

> Build one trustworthy end-to-end loop, prove it with tests and evidence, then expand deliberately.
