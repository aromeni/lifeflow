# LifeFlow AI — Product Vision

**Status:** Stage 0 draft · **Date:** 2026-07-15 · **Owner:** Product/engineering (single-founder MVP)

## One-page explanation

LifeFlow AI is a **permissioned, inspectable, human-in-the-loop personal operations agent**. It securely connects to a user's Gmail and Google Calendar, gathers a limited and explicitly authorised window of recent information, and turns it into one concise daily briefing: what needs attention, what is coming up, what the user is waiting on, and what to do next.

For every item it surfaces, LifeFlow explains **what was detected, why it matters, which source supports it, and how confident it is**. It proposes safe next steps — drafting an email, creating a task, suggesting a calendar event — but **never executes an external side effect without explicit user approval of the exact payload**. Every observation, inference, proposal, and execution is recorded in an understandable audit trail.

> **Core promise:** LifeFlow quietly finds what needs attention, explains why it matters, and prepares the next step for approval.

## What LifeFlow is not

- Not an unrestricted autonomous assistant. It does not send email, change calendars, or complete tasks on its own.
- Not a surveillance tool. It reads a constrained, user-authorised recent window, stores the minimum, and offers disconnect and deletion controls.
- Not a black box. Rankings use an explainable hybrid score with reason codes; the LLM never directly invokes actions.

## The core user loop

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

## Who it serves first

A busy UK-based professional, consultant, postgraduate student, or freelancer who receives important requests through Gmail, manages commitments in Google Calendar, and loses track of follow-ups across tools. See [personas.md](personas.md).

## Why it will be trusted

1. **Human control** — read-only by default; approval required for every side effect, with the exact payload shown.
2. **Explainability** — every surfaced item carries evidence references, reason codes, and a confidence level.
3. **Privacy by design** — minimum OAuth scopes, minimum retention, encrypted tokens, deletion and disconnect controls, GDPR principles as design constraints.
4. **Deterministic safety boundaries** — LLM output is a typed proposal that must pass schema validation, a deterministic policy engine, and user approval before any executor runs.
5. **Evidence over theatre** — no claim of intelligence, security, or readiness without repository evidence (tests, evals, audit records).

## Success in one sentence

A demo user (and later a pilot user with a real Google account) can understand what matters today in under two minutes, inspect the basis of each recommendation, and approve a prepared next step — with zero unapproved external side effects, ever.

## Where it can grow

The core platform is edition-neutral. Later edition packs (Student, Freelancer, Consultant, Family) and life-domain packs add taxonomies, prompts, priority rules, and connectors through configuration and adapters — not forks. See [mvp-scope.md](mvp-scope.md) for the strict MVP boundary, [../delivery/stage-plan.md](../delivery/stage-plan.md) for the staged route there, and [../project/project-foundation.md](../project/project-foundation.md) — the project's North Star — for the long-term evolution roadmap, permanent engineering principles, and architectural guard rails.
