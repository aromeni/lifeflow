# ADR 0004 — Stage 8: Preferences, Memory, and the Scheduled Brief

**Status:** Accepted (Phase 1 and Phase 2 scope) · **Date:** 2026-07-21 · **Stage:** 8

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

## Phase 2 decisions (this ADR's second accepted scope)

### D47 — Scheduled generation never triggers Google sync; it uses the most recently synced evidence

`connected_accounts.py` establishes, as a Stage 7 decision already in force,
that `POST /connected-accounts/google/sync` is "user-triggered, on-demand...
never automatic on page load" and "the one route that turns a connected
account into real, persisted `SourceItem` rows." Phase 2 does not change
this: the scheduled job calls the *existing* `BriefService.generate`, which
has never synced and still does not. Introducing an automatic background
sync would be a new, unreviewed side effect (network calls to Google on a
timer, on behalf of a user who is not present) and was never part of either
the original Phase 2 follow-up note above ("the same brief pipeline invoked
headlessly") or the stage-plan exit criterion. Settings therefore shows each
connected account's `last_sync_at` next to the scheduled-brief status, and
the brief's existing `source_partial` notice already discloses when a
configured source is unavailable — so the user always knows how fresh the
evidence behind a scheduled brief is, without LifeFlow silently reaching out
to Google unattended. A future stage may revisit scheduled sync as its own
reviewed decision; it is not smuggled in here.

### D48 — One static per-minute cron dispatcher; database-owned schedule, timezone-aware, DST via Python's fold semantics

A single arq cron job (`dispatch_scheduled_briefs`) runs once a minute in
UTC — not one cron entry per user (schedules are mutable row data, read
fresh every tick). Each tick:

1. loads every user with `scheduled_briefs_enabled.enabled == true`
   (`lifeflow_api.scheduled_briefs.list_enabled_schedules` — a deliberate,
   documented exception to the per-user-repository convention, since
   dispatch is inherently a cross-user system operation; every operation it
   triggers afterwards immediately becomes user-scoped again);
2. resolves each user's timezone (`User.timezone`) and `briefing_time`
   (resolved preference) and computes today's local date;
3. skips a user who already has a `ScheduledBriefRun` for that local date
   (any status) — one row per user per local date, full stop;
4. computes the target UTC instant for `briefing_time` in that timezone via
   `scheduled_briefs.resolve_local_schedule_instant` (revised during Stage 8
   Phase 2 focused remediation — see below), then `.astimezone(UTC)`.
   - **Spring-forward (nonexistent local time):** the resolver builds both
     PEP 495 fold candidates, round-trips each through UTC and back to
     local time, and finds that *neither* round-trips — the requested
     wall-clock time was skipped. It then advances in bounded, fine-grained
     (1-minute) steps to the first wall-clock instant that actually exists,
     e.g. a configured 01:30 during Europe/London's 01:00→02:00
     spring-forward resolves to 02:00:00 BST (the true first instant after
     the gap) — the run fires once, at the next real opportunity, never
     skipped and never double-counted.
   - **Fall-back (ambiguous local time):** both fold candidates round-trip
     successfully but to two different UTC instants — the resolver picks
     the earlier (pre-transition) one, so the run fires once, at the
     earlier of the two wall-clock instants, exactly per the recommended
     policy above.

   **Correction (Stage 8 Phase 2 focused remediation, 2026-07-21):** the
   original implementation used `datetime.combine(...).replace(tzinfo=...)`
   with Python's default `fold=0` directly, unclassified and unverified,
   and its own comment here claimed this "lands at the first valid
   wall-clock moment after the gap." That claim was checked against actual
   zoneinfo transition data and found to be wrong: unvalidated `fold=0` on a
   nonexistent time instead lands at *requested time + gap size*
   (02:30 BST for a requested 01:30), which is a plausible-looking but
   arithmetically different answer from "the first valid instant" (02:00
   BST). The gap went unnoticed because the original test asserted whatever
   the implementation happened to produce rather than an independently
   derived expected value. `resolve_local_schedule_instant` (with an
   explicit `valid`/`ambiguous`/`nonexistent` classification, round-trip
   verification, and a bounded forward search with no hard-coded offset
   size — verified against both Europe/London's 60-minute and Australia/Lord
   Howe's 30-minute transitions) replaces it; `compute_target_utc` is now a
   thin wrapper over the resolver, so dispatch eligibility, catch-up
   comparisons, and the `next_expected_run` display all agree by
   construction.
   - **Timezone or briefing-time changes:** since nothing is precomputed,
     the very next tick recalculates the target instant from the user's
     current settings. A change affects only the next not-yet-created run;
     a local date that already has a `ScheduledBriefRun` row is never
     recomputed or re-run, so a change after a successful run never
     produces a second brief that day, and a change to an earlier,
     already-passed time is governed by the same catch-up window as any
     other missed run (D49).
5. if due and within the catch-up window, creates a `pending`
   `ScheduledBriefRun` row and enqueues the generation job with a
   deterministic id `scheduled-brief:{user_id}:{local_date}:{attempt}` via
   `_job_id` — a second, independent duplicate guard on top of the database
   `UniqueConstraint(user_id, local_brief_date)`, which remains the final
   guard regardless of what the queue does.

Redis is transport only: job payloads carry `run_id` alone (a UUID string,
never user content), and the worker reloads all authoritative state —
enablement, timezone, briefing time, the run record — from PostgreSQL before
acting. arq's default job (de)serializer is `pickle`; Phase 2 overrides it to
`json` (`lifeflow_api.scheduled_briefs._job_serializer`/`_job_deserializer`)
so no job payload is ever pickle-deserialized, even though the only argument
passed is an internal identifier.

### D49 — Bounded catch-up window; bounded stale-run recovery; no multi-day backfill

- **Catch-up:** if a dispatcher/worker outage means a user's target instant
  has already passed when the next tick runs, the brief is still generated
  if the tick occurs within **6 hours** of the target instant. Beyond 6
  hours, the run is recorded `skipped` (`error_code=missed_grace_window`)
  and never generated — a stale "good morning" brief arriving mid-afternoon
  is worse than none. Exactly one `ScheduledBriefRun` row is ever created
  per user per local date (skipped or otherwise), so a skip never blocks the
  next day's run and never triggers a multi-day backfill; the user can
  always generate manually in the meantime.
- **Stale `running` recovery:** a tick also recovers any run stuck `running`
  for more than 10 minutes (a crashed worker never resolved it). Below
  `MAX_ATTEMPTS` (3) it is requeued with an incremented attempt count and a
  fresh deterministic job id (`...{attempt}`); at or beyond the limit it is
  marked `failed` (`error_code=worker_stale_timeout`) and left for manual
  generation. This is a documented recovery policy, not an indefinite hang.
- **Idempotent generation across worker crashes:** `Brief.scheduled_run_id`
  is a unique, nullable FK. If a worker crashes after committing the brief
  but before marking the run `succeeded`, the retried attempt looks up the
  brief by `scheduled_run_id` first and finishes the run record rather than
  generating a duplicate — the database relationship is the guard, not a
  best-effort check.
- **Retry classification:** only transient failures (Redis/database
  unavailable, worker timeout) are retried, bounded by `MAX_ATTEMPTS`.
  Permanent/user-state failures (invalid timezone, user deleted, schedule
  disabled before the job ran) are recorded `skipped` or `failed` once and
  never retried. No stack trace, prompt content, or brief prose is ever
  stored in `error_message` — only a short, safe, closed-vocabulary phrase.

### D50 — `scheduled_briefs_enabled` joins the closed preference registry; default off

A fourth registry key, `{"enabled": bool}`, default `false` — an existing
deployment must not suddenly start scheduling briefs for every user merely
because `briefing_time` already had a default. The same Phase 1 rules apply
unchanged: explicit provenance, `preference.updated` audit, 404/422 on
bad input, and safety-inert (the scheduler consults it to decide *whether to
enqueue*, exactly like `briefing_time`/timezone decide *when* — never to
widen the action policy, approval, or executors, which never read any
preference).

## Consequences (Phase 2)

- New table `scheduled_brief_runs` (migration `0009`) and two new columns on
  `briefs`: `generation_trigger` (`"manual"` | `"scheduled"`, default
  `"manual"`) and `scheduled_run_id` (nullable, unique FK). Both are real
  columns, not metadata-only, so the worker's crash-recovery lookup and the
  frontend's manual/scheduled distinction are simple indexed queries, not
  JSON parsing.
- `BriefService.generate` gains optional `generation_trigger`/
  `scheduled_run_id` parameters; manual callers (the existing
  `/briefs/generate` route) are unaffected and keep defaulting to
  `"manual"`.
- New `lifeflow_api/scheduled_briefs.py`: DST-correct due-instant
  calculation, dispatch planning (pure DB logic, independently testable
  without Redis), catch-up/stale-recovery, the per-user generation entry
  point, and failure classification.
- New `lifeflow_api/worker_app.py` (arq `WorkerSettings`, cron + task
  wrappers) and a thin `workers/scheduler_worker.py` entry point, per the
  Phase 1 follow-up note — the arq/Redis glue is intentionally thin; all of
  the logic above lives in the ordinary, pytest-covered `lifeflow_api`
  package, not in the worker glue.
- Redis joins the compose stack, optional for demo/CI exactly as planned —
  the web API stays fully usable (including manual brief generation,
  Google connection management, and approval/execution) when Redis or the
  worker is unavailable; only the new scheduled-brief status surface
  reports reduced capability.
- New read-only `GET /scheduled-briefs/status` (per-user: enabled, briefing
  time, timezone, next expected run, latest run outcome, linked brief id/
  version, and whether the scheduler is currently reachable). Settings
  replaces the Phase 1 "not yet in use" copy with this real status once the
  user enables scheduling, and states plainly that scheduled generation
  never approves or executes anything. Today labels each brief manual or
  scheduled.

## Follow-up

- Phase 3: inferred preferences with visible confidence + memory controls;
  extend the eval suite with preference-adaptation cases.
- Settings screen grows memory controls (Phase 3); privacy screen (Stage 9)
  links to preference/audit history.
- Deferred, not part of Phase 2: scheduled Google sync (D47) — if a future
  stage wants the scheduled brief to sync first, that is a new reviewed
  decision, not an extension of this one.
