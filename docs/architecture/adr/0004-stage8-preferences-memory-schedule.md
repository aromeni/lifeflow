# ADR 0004 — Stage 8: Preferences, Memory, and the Scheduled Brief

**Status:** Accepted (Phase 1, Phase 2, and Phase 3 scope) · **Date:** 2026-07-21 (Phase 3 added 2026-07-22) · **Stage:** 8

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

## Phase 3 decisions (this ADR's third accepted scope — inferred memory)

**Status:** Accepted (Phase 3 scope), 2026-07-22.

Phase 3 completes Stage 8's "transparent adaptation" theme by adding *inferred*
memory: `provenance="inferred"` knowledge that LifeFlow derives from the user's
own deliberate in-app behaviour, shows with visible confidence and evidence,
and never applies to any outgoing content until the user confirms it. The
original Phase 3 sketch (D43.3) named "learned priority weights" only as an
example; the concrete contract below is what Phase 3 actually delivers.

### Reconstructed Phase 3 requirements matrix

| # | Requirement (source) | Intended behaviour | Implementation | Safety-sensitive |
|---|---|---|---|---|
| R1 | Inferred memory with visible confidence; explicit override always wins; view/correct/delete (D43.3, stage-plan row 8 "transparent adaptation") | One closed, typed inferred-memory type with a full lifecycle | `memory_registry.py` + `MemoryItem`/`MemoryEvidence` | yes |
| R2 | Evidence from user-controlled behaviour only (skill §4.2 explainability, §11 injection boundary) | Learn only from the user's own approved, edited Gmail-draft sign-offs — never from inbound email | `memory_registry.extract_signoff` + `memory_inference` scan of `create_gmail_draft` proposals with `user_edited_at` set | yes |
| R3 | No hidden application; explicit always wins (skill §4.1, D46) | Inferred memory is *suggest-only*: it never touches draft composition. Only a **confirmed** memory — written through the existing explicit preference registry — is applied | `preferred_email_signoff` joins the preference registry (D44); composer reads only that explicit key | yes |
| R4 | Understandable confidence (skill §4.2, §8) | Deterministic `strength × consistency × freshness`, bounded [0,1], Low/Med/High bands | `memory_registry.compute_confidence` | no |
| R5 | Editable, confirmable, dismissible, deletable; pause learning (skill §12 Settings "memory controls") | Full API + Settings section | `memory.py` router + Settings Memory section | no |
| R6 | Cannot weaken approvals/execution (skill §4.5, D46) | Memory (and the confirmed preference) is consulted only during *composition*; the policy engine, approval binding, and executors never read it | composer-only wiring; unchanged policy/executor code | yes |
| R7 | Async, recoverable, Redis carries only IDs (skill §9.2, D48) | Reuse Phase 2 arq/Redis; `recompute_user_memory(user_id)`; PostgreSQL is the source of truth; user actions succeed if Redis is down | `worker_app.recompute_user_memory` + best-effort enqueue | yes |
| R8 | Sensitive-inference prohibition (skill §11, GDPR §4.3) | Closed registry: only `preferred_email_signoff` exists; a documented deny-list of categories can never be registered | `MEMORY_REGISTRY` + `PROHIBITED_MEMORY_CATEGORIES` | yes |

### D51 — One safe vertical slice: `preferred_email_signoff`. Meeting-duration deferred

The plan offered two candidate types. Only `preferred_email_signoff` has, at
once, (a) a genuine *user-controlled* evidence source — the user editing a
Gmail-draft proposal and then approving it — and (b) a real, safe adaptation
point: `proposal_composition._draft_candidates` currently hard-codes the
closing line `"Best"`. Confirming a learned sign-off replaces that default for
*future* draft proposals only, which the user still previews and approves in
full.

`preferred_meeting_duration_minutes` is **deferred, not implemented**, because
the calendar composers (`_scheduled_event_candidate`,
`_proposed_placeholder_candidate`) never have a *missing* duration for memory
to fill: start/end always come wholesale from the evidence text or the synced
event, under Stage 7's fail-closed extraction (D39/D41). Injecting an inferred
duration there would either be inert (a memory row that changes nothing —
theatre) or would have to *override* an evidence-derived duration, weakening the
very fail-closed rule the plan forbids weakening. The plan explicitly authorises
this call ("If either type cannot be implemented safely with the current event
data, replace it with a narrower type and document why"; "Do not add multiple
speculative memory categories merely to make the feature look larger"). One type
implemented completely and safely demonstrates the entire lifecycle — contradiction,
confirmation, override, dismissal, decay, deletion — without a second, weaker one.

### D52 — Closed, typed memory registry; unknown and sensitive keys fail closed

`MEMORY_REGISTRY` maps each memory key to a `MemoryTypeSpec` (value schema,
eligible evidence type, minimum evidence count, `application_mode`,
corresponding explicit-preference key, explanation template, sensitivity
classification, deletion behaviour). Exactly one key is registered:
`preferred_email_signoff`. Any other key — including every entry in
`PROHIBITED_MEMORY_CATEGORIES` (health, disability, race/ethnicity, religion,
political opinion, sexuality, biometrics, trade-union membership, criminal
matters, financial hardship, immigration status, protected characteristics,
psychological diagnoses, intimate-relationship status, information about
children) — is rejected at the registry, repository, and API layers. There is
no free-text key/value path: the memory tables are only ever written by
`memory_inference`, which composes values from the registry, never from
arbitrary input. `PROHIBITED_MEMORY_CATEGORIES` is a documented, tested
deny-list so the prohibition is explicit and regression-guarded even though the
closed registry already makes those keys unreachable.

### D53 — Evidence: the user's own approved, edited drafts only; store the normalised sign-off, never the body

The single eligible evidence event is: a `create_gmail_draft` proposal that the
user **edited** (`user_edited_at` set) and then **approved**.
`extract_signoff(body)` reads only the trailing closing line, matches it against
a closed set of recognised sign-offs (Best, Kind regards, Regards, Thanks, Many
thanks, Cheers, Best wishes, Warm regards, Sincerely, Best regards → canonical
forms), and ignores quoted lines (`>`), contact-bearing signature lines
(`@`, URLs, digits), and anything unrecognised. `MemoryEvidence` stores only
that short normalised token plus a safe reference (the proposal id and a reason
code) — never the draft body, recipients, or subject. Inbound email is never an
evidence source: nothing in `memory_inference` reads `SourceItem` content, so a
phrase in a received message can never become a "preference" (skill §11.1;
tests R2 below).

### D54 — Deterministic, inspectable confidence

`confidence = evidence_strength × consistency × freshness`, each in [0,1]:

- `evidence_strength = min(1, agreeing_observations / 4)` — saturates at four
  consistent observations;
- `consistency = agreeing_observations / total_observations` — contradictory
  sign-offs lower it;
- `freshness = 0.5 ** (age_of_latest_agreeing_evidence_days / 30)` — 30-day
  half-life decay.

Bands (documented, tested, shown in the UI as words plus the numeric value):
**Low** `< 0.34`, **Medium** `0.34–0.66`, **High** `≥ 0.67`. A memory is only
*surfaced as a reviewable candidate* once it has `MIN_EVIDENCE = 2` agreeing
observations, so one observation can never produce a confirmable ("active")
memory (skill §7). No LLM confidence is ever used; the model is pure arithmetic
over evidence rows.

### D55 — Lifecycle, precedence, dismissal, and deletion-vs-pause

One `MemoryItem` per `(user_id, memory_key)` (unique constraint — never two
conflicting active memories). Closed status set: `candidate` → `confirmed` /
`dismissed` / `superseded` / `expired`.

**Precedence (skill §3.1), by construction:** inferred memory is *suggest-only*
and is never read by the composer. Composition reads only the explicit
`preferred_email_signoff` preference (falling back to the system default
"Best"). **Confirmation** writes that explicit preference with normal explicit
authority (provenance `explicit`) and marks the item `confirmed`. So an inferred
value can *never* override an explicit one — it literally is not in the
application path until the user promotes it to explicit. A later explicit change
takes effect immediately (it is just a preference write); the superseded item
stays visible with `overridden_by_explicit = true` and is no longer applied.
Deleting the explicit preference falls back to the system default, not silently
back to the inferred value (the candidate may re-surface for fresh confirmation).

**Dismissal** is sticky via an evidence fingerprint: dismissing records
`dismissed_fingerprint` (a hash of the contributing proposal-id set); recompute
keeps the item `dismissed` until genuinely new evidence changes that
fingerprint, at which point it may return to `candidate` (skill §8
reconsideration rule).

**Effective expiry (focused-review addition, 2026-07-22):** a candidate must
never be *represented as active* once its confidence has decayed below the
floor, and that must not depend on a later recompute (which only runs on a new
qualifying approval) or on the user taking any action. `effective_confidence`
continues the same 30-day half-life decay from `last_evaluated_at` to now, and
`expire_stale_candidates` transitions a decayed candidate to `expired`
(persisting the decayed value, auditing `memory.expired` exactly once) on
**every authenticated read** of the memory API — exactly as the proposals list
already expires due proposals via `ActionProposalService.expire_due` — while a
**daily maintenance cron** (`worker_app.expire_stale_memory`, 03:00 UTC, reusing
the Phase 2 arq scheduler, no new queue) guarantees expiry even for a user who
never opens Settings again. Both are idempotent and cross-user-safe; confirmed
explicit preferences are not candidates and never decay. The memory API and UI
show the *effective* (decayed) confidence and status as of now, not the frozen
last-recompute value.

**Deletion vs pause (documented distinction, skill §14):** `memory_inference_enabled`
(preference, **default off** — the conservative, privacy-first default matching
D50) pauses *new* learning without deleting anything. `DELETE /memories[/{id}]`
erases the derived item and its evidence (a privacy control) but does not touch
the source proposals, so continued qualifying behaviour may re-learn it; the
Settings copy states this and recommends Dismiss (sticky) or Pause to stop
learning. Account deletion cascades all memory rows (`ON DELETE CASCADE` from
`users`).

### D56 — Inference execution: async arq recompute, bounded and recoverable

A committed qualifying approval best-effort-enqueues `recompute_user_memory(user_id)`
onto the Phase 2 arq/Redis queue (user id only — never draft content). If Redis
is unavailable the approval still succeeds and the enqueue is skipped; because
the worker **rescans** the user's recent eligible proposals (bounded window)
rather than trusting a single event, any missed enqueue self-heals on the next
recompute (skill §9 recoverability). The worker loads all authoritative state
from PostgreSQL, is idempotent (evidence deduped by `(memory_item_id,
source_proposal_id)`), and cannot create duplicates under concurrency (the
`(user_id, memory_key)` unique constraint is the final guard). No new scheduler
or queue is introduced. Recompute is skipped entirely when inference is paused.

### D57 — Visible adaptation, composition-only

`compose_proposal_candidates` gains a `preferred_signoff: str | None` parameter,
resolved by `ActionProposalService.generate_from_brief` from the explicit
`preferred_email_signoff` preference and passed down; `_draft_candidates` uses it
in place of "Best" and records in the proposal `rationale` that the sign-off was
applied from a confirmed preference. The adapted body is part of the payload and
therefore of the payload hash and approval binding automatically — nothing about
approval, the policy engine, execution mode, recipients, or the Gmail executor
changes. Existing proposals are immutable (generation preserves user-edited and
approved rows); only newly composed candidates pick up the sign-off.

### D58 — Audit and deletion-safe events

Reuse `preference.updated` for enable/disable (`memory_inference_enabled`) and
for the confirmed value (`preferred_email_signoff`) rather than duplicating it.
Add `memory.candidate_created`, `memory.candidate_updated`, `memory.confirmed`,
`memory.dismissed`, `memory.deleted`, `memory.superseded`, `memory.expired`
(actor `system:memory` or `user:{id}`). Metadata carries only safe fields
(memory key, status, evidence count, confidence band, and — for candidate/confirm
events, as with preference values — the short normalised sign-off token).
`memory.deleted` records the fact and key only, never the deleted value
(skill §14).

## Consequences (Phase 3)

- New tables `memory_items` and `memory_evidence` (migration `0010`), both
  cascading from `users`.
- New modules: `memory_registry.py` (registry, deny-list, confidence,
  sign-off extraction — all pure, unit-tested), `memory_inference.py` (the
  recompute lifecycle, DB-only, testable without Redis), and `memory.py`
  (service + owner-scoped router). `worker_app.py` gains a `recompute_user_memory`
  function; `action_proposals.py`'s approve route best-effort-enqueues it.
- Two registry keys added in `preferences.py`: `memory_inference_enabled`
  (`{"enabled": bool}`, default `false`) and `preferred_email_signoff`
  (`{"value": str}`, validated closed-ish sign-off, no default — absent means
  the composer uses "Best").
- `proposal_composition.compose_proposal_candidates` and
  `ActionProposalService.generate_from_brief` gain the `preferred_signoff`
  parameter; all existing callers default to `None` (unchanged behaviour).
- Settings grows a Memory section (list, confidence, evidence, confirm/edit/
  dismiss/delete, delete-all, pause/resume). Contracts regenerated.

## Follow-up

- Settings/privacy screen (Stage 9) links to preference/audit/memory history;
  extend the eval suite with preference-adaptation cases.
- Deferred, not part of Phase 2: scheduled Google sync (D47) — if a future
  stage wants the scheduled brief to sync first, that is a new reviewed
  decision, not an extension of this one.
- Deferred, not part of Phase 3: `preferred_meeting_duration_minutes` (D51) —
  needs a composition path with a genuinely missing duration to fill safely,
  which Stage 7's fail-closed calendar extraction does not currently present.
