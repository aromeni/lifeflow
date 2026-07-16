# Project Foundation

**Status:** North Star — planning and governance document only · **Date:** 2026-07-15

This document preserves long-term architectural and product consistency for LifeFlow AI. It does **not** expand the implementation scope of the MVP and introduces no code. Whenever it is unclear whether a feature belongs in the MVP, or whether a design decision aligns with the long-term vision, this document is the single source of truth. It is read alongside the stage-gated protocol in [../delivery/stage-plan.md](../delivery/stage-plan.md) and the strict scope in [../product/mvp-scope.md](../product/mvp-scope.md).

---

## 1. Vision

**Long-term mission.** LifeFlow AI becomes a modular personal operations platform: one calm, trustworthy place where a person's authorised digital life — email, calendar, tasks, and later further life domains — is watched quietly, understood, and turned into clear, evidence-backed next steps that the user approves.

**The problem.** Everyday obligations are scattered across tools. Important requests arrive buried in email; promises made in passing are forgotten; follow-ups go stale silently; calendars conflict without warning. The cost is not just missed items — it is the continuous background anxiety of *not knowing whether something has been missed*.

**Why the product exists.** Existing tools either store information passively (inboxes, calendars) or act autonomously in ways users cannot trust (assistants that send messages or change schedules on their own). LifeFlow exists to occupy the trustworthy middle: it finds what needs attention, explains why, and prepares — but never performs — the next step.

**Who it is for.** First, a busy UK-based professional, consultant, postgraduate student, or freelancer (see [../product/personas.md](../product/personas.md)). Later, students, freelancers, consultants, families, and small teams through edition packs built on the same core.

**How it differs from a traditional chatbot.** A chatbot waits for questions and answers them conversationally, with no memory of obligations and no safety architecture around actions. LifeFlow is not a conversation. It is a permissioned, inspectable pipeline: authorised data in → normalised signals → explainable priorities → typed action proposals → deterministic policy checks → explicit human approval → audited execution. The LLM is a bounded interpretation component inside that pipeline, never the pipeline itself.

**How AI reduces cognitive load without replacing judgement.** AI does the gathering, classifying, and drafting — the work that consumes attention but not wisdom. The human keeps every decision that matters: what to prioritise differently, what to approve, what to reject, what the system may remember. Confidence levels and evidence keep the human calibrated rather than deferential.

> LifeFlow quietly watches authorised parts of a user's digital life, identifies what genuinely requires attention, explains why it matters, and prepares safe next actions for explicit user approval.

---

## 2. Product Evolution Roadmap

This roadmap describes how the product evolves. It does **not** change the current MVP scope; phases beyond Phase 1 are recorded intent, not scheduled work.

### Phase 1 — MVP (current)

Current scope only, as defined in [../product/mvp-scope.md](../product/mvp-scope.md):

- Google OAuth
- Gmail
- Google Calendar
- Daily Brief
- Signal Extraction
- Priority Engine
- Approval Inbox
- Gmail Draft Creation
- Calendar Event Creation
- Audit Trail
- Preferences
- Demo Mode

> No additional functionality should be implemented unless explicitly scheduled.

### Phase 2 — Pilot

A small group of real, consenting users. Possible additions — all refinements of the existing loop, not new domains:

- notifications
- improved prioritisation
- better brief generation
- onboarding improvements
- performance optimisation
- connector reliability

No expansion into shopping or finance.

### Phase 3 — Version 1

Expand the platform on the proven core:

- Microsoft 365
- Slack
- todo systems
- better scheduling
- richer memory
- configurable workflows
- notification engine

### Phase 4 — Professional Edition

Introduce additional Life Domains, each entering through the connector and edition-pack extension points:

**Finance**

- subscription monitoring
- bill reminders
- unusual-transaction indicators
- recurring payment summaries

**Shopping**

- recurring shopping lists
- inventory tracking
- receipt processing
- low-stock detection
- reorder proposals

**Travel**

- itinerary organisation
- passport reminders
- booking summaries

**Health**

- appointments
- medication reminders
- wellbeing tracking

All external actions continue to require explicit approval, in every domain, in every phase.

### Phase 5 — Enterprise

Future possibilities only:

- teams
- shared workspaces
- enterprise policy engine
- RBAC
- audit dashboards
- compliance reporting
- organisation connectors

These features are outside the MVP.

---

## 3. Permanent Engineering Principles

These principles are never violated, in any phase, by any contributor — human or AI agent.

### Human in the Loop

External actions always require explicit approval.

### Deterministic Safety

LLMs never execute actions directly. All actions pass through deterministic policy validation.

### Evidence First

Every recommendation must provide supporting evidence.

### Explainability

The user must understand: what happened, why it matters, and why the recommendation exists.

### Privacy by Design

Collect the minimum amount of data. Request the minimum OAuth scopes. Protect personal information.

### Auditability

Every external action is recorded. Every proposal is traceable. Nothing happens silently.

### Provider Neutrality

Business logic never depends on a single LLM provider. AI providers remain replaceable.

### Modular Connectors

Every connector implements common interfaces. Connectors remain independent.

### Demo First

Every feature should work using synthetic data before requiring external accounts.

### Progressive Delivery

Complete one fully-working workflow before expanding functionality. Avoid partially finished features.

### Security First

Assume external content is untrusted. Prompt injection, malicious emails, and hostile inputs must always be considered (see [../security/threat-model.md](../security/threat-model.md)).

### Simplicity

Prefer straightforward solutions over unnecessary complexity. Avoid premature optimisation.

### Testability

Every important behaviour should have automated tests. Critical paths should include end-to-end tests.

### Extensibility

Future editions should be added through configuration and plugins, not by rewriting the platform.

---

## 4. Architectural Guard Rails

The following rules apply throughout the project, at every stage and in every phase:

- Never bypass approval workflows.
- Never allow LLM output to directly execute tools.
- Never couple business logic to Google APIs.
- Never hard-code AI providers.
- Never store secrets in plaintext.
- Never expose prompt internals.
- Never bypass audit logging.
- Never silently ignore failures.
- Never implement features outside the current stage.

An AI coding agent that finds itself about to break one of these rules must stop and surface the conflict rather than proceed.

---

## 5. Definition of Success

The MVP succeeds if a user can:

```text
Connect Gmail and Calendar
        ↓
Generate a useful Daily Brief
        ↓
Understand why each recommendation exists
        ↓
Approve a proposed action
        ↓
See that action safely executed
        ↓
Review a complete audit trail
```

**without losing trust in the system.**

Measurable criteria backing this definition live in [../product/mvp-scope.md](../product/mvp-scope.md) (safety criteria S1–S8, quality criteria Q1–Q7, engineering criteria E1–E4).

---

## 6. Future Vision

LifeFlow AI is intended to become a modular personal operations platform capable of supporting multiple life domains — communication, scheduling, finance, shopping, travel, learning, consulting, and family management. Each domain will arrive as a connector or edition pack plugged into the same core: the same typed proposals, the same deterministic policy engine, the same approval inbox, the same audit trail.

Every future capability must be built on the same trusted foundation established by the MVP. The foundation is not a starting point to be outgrown; it is the platform's identity.

---

## 7. Success Metrics

LifeFlow AI will be considered successful if it achieves the following over the first twelve months after MVP completion. Several of these correspond to MVP stage-gate criteria in [../product/mvp-scope.md](../product/mvp-scope.md) (zero unauthorised actions = S1, zero cross-user leakage = S6, brief read in under 2 minutes = Q6); the rest are pilot-era outcomes measured after launch. The brief-generation latency target feeds the Stage 10 performance-profiling checklist.

### Technical

- >99% successful connector synchronisations
- Zero unauthorised external actions
- Zero cross-user data leakage
- Complete audit coverage
- Average Daily Brief generation under 15 seconds

### User Experience

- Users read the Daily Brief in under 2 minutes
- Users approve at least 70% of proposed actions
- Less than 5% of proposals are considered irrelevant
- Average user trust rating >4.5/5

### Business

- First 10 pilot users
- First paying customer
- First reusable edition pack
- Positive user retention after 90 days

Success is measured by trust, usefulness and adoption — not by the number of AI features implemented.

> **Build one trustworthy workflow, validate it with real users, then expand deliberately. Long-term success depends on maintaining simplicity, safety, transparency, and user trust at every stage.**
