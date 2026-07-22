# ADR 0004 — Stage 8: Preferences, Memory, and the Scheduled Brief

**Status:** Accepted (Phase 1 scope) · **Date:** 2026-07-21 · **Stage:** 8

## Context

Stage 7 delivered the complete real workflow (connect → sync → brief →
approve → real, verified execution) and is tagged `stage-7-complete`. Stage 8's
exit criterion (stage plan): *"Scheduled brief at configured time reflecting
visible preferences."* The skill additionally requires a Settings surface
(timezone, briefing time, working hours, brief-section choices, memory
controls) and a `Preference` entity with `explicit | inferred` provenance —
the entity and its repository have existed since Stage 2, unused until now.

## Decisions

### D43 — Stage 8 is delivered in three phases, each independently reviewable

1. **Phase 1 (this ADR's implemented scope): explicit preferences.** A closed,
   typed preference registry; read/update API; a Settings screen; and one
   immediately visible adaptation — the brief respects the user's chosen
   sections. Everything explicit, nothing inferred, no scheduler yet.
2. **Phase 2: the scheduled brief.** A background worker generates the daily
   brief at the user's `briefing_time` in their timezone. Per BD2/ADR 0001 D2,
   this is the point where a job runner is adopted: **arq + Redis**, confirmed
   here — arq is async-native (matches the SQLAlchemy-async stack), small, and
   sufficient for per-user cron-style jobs; Celery would add a second
   serialisation/config surface for no current requirement. Redis enters the
   compose stack only in Phase 2, optional for demo/CI exactly as the LLM
   provider is.
3. **Phase 3: memory and inferred preferences.** `provenance="inferred"`
   entries (e.g. learned priority weights) with visible confidence, an
   explicit user override always winning, and memory controls (view, correct,
   delete) on the Settings screen.

### D44 — Closed, typed preference registry; free-form keys are rejected

`PUT /preferences/{key}` accepts only registry keys, each with its own strict
value schema and default:

| Key | Value shape | Default | Consumed by |
|---|---|---|---|
| `briefing_time` | `"HH:MM"` (24h, valid time) | `"07:30"` | Phase 2 scheduler; shown in Settings now |
| `working_hours` | `{"start": "HH:MM", "end": "HH:MM"}`, start < end | 09:00–17:30 | Phase 2/3 (quiet-hours, urgency shaping); shown in Settings now |
| `brief_sections` | subset of `{today_upcoming, waiting_for, suggested_actions, low_confidence_review}` | all four | Brief composition, immediately (Phase 1) |

Unknown keys are a 404, invalid values a 422 with a plain-language message.
`User.timezone`/`locale` deliberately stay on the `User` row (already explicit,
already editable via `PATCH /me` since Stage 2) — a second copy in the
preference table would create a precedence question with no benefit.

### D45 — "Needs attention" can never be hidden

`brief_sections` cannot disable `needs_attention`. High-priority, conflict, and
overdue items are the product's core duty of care; a configuration that could
silently hide them is not offered (same spirit as D12's non-editable
`guest_notifications` field). The section filter is display-level only:
signals are still extracted, persisted, and available to proposals — hiding a
section never suppresses an approval-inbox entry, and the brief's metadata
records `sections_disabled` so the adaptation is always inspectable.

### D46 — Preference writes are explicit, audited, and safety-inert

Every write via the API stores `provenance="explicit"` and records a
`preference.updated` audit event (key, provenance, and the new value — these
are configuration, not personal content). Preferences can never widen the
action policy: they influence display, timing (Phase 2), and ranking inputs
(Phase 3) only. Nothing in the preference layer is consulted by the policy
engine, the executors, or the approval binding.

## Consequences

- New `preferences.py` (service + router), registered in `main.py`; contracts
  regenerated. `PreferenceRepository` gains an ownership-checked upsert path
  via the existing `get`/`add` methods.
- `BriefService.generate` filters the *displayed* document (sections, summary,
  allowed prose sentences) by the enabled set; the pure composition/eval
  boundary (`compose_sections`) is untouched. `deterministic_summary` now
  tolerates absent sections.
- Redis/arq are **not** introduced in Phase 1 — no new infrastructure until
  the phase that needs it.

## Follow-up

- Phase 2: worker entry point under `workers/`, arq + Redis in compose
  (optional for demo/CI), per-user schedule from `briefing_time` + timezone,
  and the same brief pipeline invoked headlessly with audit trail.
- Phase 3: inferred preferences with visible confidence + memory controls;
  extend the eval suite with preference-adaptation cases.
- Settings screen grows memory controls (Phase 3) and scheduler status
  (Phase 2); privacy screen (Stage 9) links to preference/audit history.
