# Personas

**Status:** Stage 0 draft · **Date:** 2026-07-15

All personas are fictional. No real personal data appears in this repository.

## Primary MVP persona — "Amara", independent consultant (UK)

| Attribute | Detail |
|---|---|
| Age / location | 38, Manchester, UK (Europe/London timezone, GMT/BST daylight-saving shifts matter) |
| Work | Independent management consultant with 3–5 concurrent clients |
| Tools | Gmail (single account), Google Calendar, ad-hoc notes and task lists |
| Volume | 40–80 emails/day, 3–6 meetings/day, frequent reschedules |

### Pains

- Important client requests arrive buried among newsletters and CC-noise.
- Promises made in email ("I'll send the deck by Friday") get forgotten.
- Follow-ups she is owed go stale silently — no one reminds her that a client hasn't replied in five days.
- Double-bookings and travel-time conflicts appear only when it's too late.
- Existing "AI assistants" feel risky: she will not let software send email or move meetings on her behalf.

### Goals

- One concise, trustworthy daily view of what actually matters.
- Suggested next actions that are *prepared*, not *performed* — she stays the decision-maker.
- Clear visibility of what the product read, stored, and did, with a way to disconnect and delete.

### Trust requirements (non-negotiable)

- Explicit approval before any email draft, calendar event, or task side effect.
- Plain-language explanation and source link for every surfaced item.
- Minimal scopes, visible retention policy, one-click disconnect.

## Secondary MVP-compatible personas (same core loop, no special build)

### "Tobi", postgraduate researcher (UK)

Supervisor emails contain implicit deadlines; seminar and teaching commitments live in Calendar; needs deadline extraction and follow-up nudges. Uses the identical MVP feature set.

### "Priya", freelance designer (UK)

Client briefs, proposal follow-ups, and delivery commitments arrive by email; needs "waiting for" tracking and prepared reply drafts. Uses the identical MVP feature set.

## Future edition personas (out of MVP scope — roadmap only)

Recorded here so the architecture stays adaptable; see [mvp-scope.md](mvp-scope.md) §Out of scope and the extension architecture in [../delivery/stage-plan.md](../delivery/stage-plan.md).

- **Student edition** — assignment deadlines, seminar preparation, reading plans, supervisor follow-ups.
- **Freelancer edition** — client requests, proposal follow-ups, invoice reminders, delivery commitments.
- **Consultant edition** — client action registers, meeting follow-ups, proposal/contract milestones.
- **Family edition** — shared commitments, school events, household reminders, permission-aware shared views.

Edition packs will differ in signal taxonomy, prompts, priority rules, dashboard sections, and onboarding copy — delivered through configuration, not forks of the core workflow.
