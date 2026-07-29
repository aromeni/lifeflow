# ADR 0005 — Stage 9: privacy, deletion, retention, audit UX, resilience

**Status:** accepted (planning gate approved 2026-07-22); Delivery Phase 1 implemented 2026-07-22; Delivery Phase 2 implemented 2026-07-23; Delivery Phase 3 committed and pushed 2026-07-24 (`origin/stage-9-audit-history` at `a50cf06`, D75–D80); Delivery Phase 4 (rate limiting, D81) remotely finalised 2026-07-27 (`origin/stage-9-rate-limiting` at `481a67b`); Delivery Phase 5 (resilience and telemetry, D82–D95) remotely finalised 2026-07-29 (`origin/stage-9-resilience-telemetry` at `5a2ca516`). Stage 9 final integration (all five Delivery Phases plus CI resilience-suite coverage and documentation closure) is in progress on `stage-9-final-integration`, not yet merged to `main`, not tagged.
**Context:** Stage 8 is complete and merged to `main` (`c5b60b1`). Stage 9's
exit theme is *"trust features operational — users control their data; the
product fails safely in outages."* This ADR records the ratified Stage 9
policy decisions and the phase split. Delivery Phase 1 (the Privacy &
Connections Control Centre) is built against these decisions but is strictly
non-destructive; the destructive engine, retention enforcement, audit
timeline, rate limiting, and resilience hardening are later Delivery Phases.

## Terminology (D59)

- The completed architecture/discovery exercise is the **Stage 9 Planning Gate**.
- The implementation phases are **Stage 9 Delivery Phase 1..5**. "Phase 1" in
  documentation always means *Delivery* Phase 1 (the Privacy Centre), never
  the planning gate.

## Delivery phase split (D60)

1. **Delivery Phase 1 — Privacy & Connections Control Centre** (this ADR's
   implementation): one consolidated, read-only surface. No destructive delete.
2. **Delivery Phase 2 — imported-data deletion, retention enforcement, account
   deletion** (shared durable deletion engine).
3. **Delivery Phase 3 — audit history** (read projection over the existing
   append-only `AuditEvent`; no new capture model).
4. **Delivery Phase 4 — rate limiting.**
5. **Delivery Phase 5 — outage resilience + logging/telemetry PII review.**

## Ratified decisions

### D61 — Account deletion is anonymise-and-minimise (not blind hard delete)

When account deletion ships (Delivery Phase 2) it will: revoke provider access;
erase tokens and sign-in identifiers (including the Google subject); remove
personal product data; permanently disable the account; and retain only
**content-free** audit and execution *tombstones* required for system
integrity and uncertain-outcome reconciliation. A random, non-reversible
deletion subject identifier replaces the user identity. A tombstone never
retains email, Google subject, message content, proposal payload, recipients,
attendees, memory values, or OAuth details. Account deletion uses the **same**
durable deletion engine as imported-data deletion. (Not implemented in Delivery
Phase 1.) This resolves the `AuditEvent.user_id` CASCADE tension raised at the
planning gate in favour of anonymisation over cascade-erasure.

### D62 — Retention is globally configured env settings, not a table

For the pilot, retention horizons are validated environment settings
(`config.Settings`, positive integers), not a `DataRetentionPolicy` table.
Provisional **product** defaults (not legal mandates):

| Category | Default |
|---|---|
| SourceItems | 30 days |
| Signals | follow their SourceItem's lifecycle (no fixed horizon) |
| Brief versions | 90 days |
| Rejected / expired / unapproved proposals | 90 days |
| Approved proposals & terminal executions | 365 days |
| Pending / uncertain executions | never auto-deleted before reconciliation |
| ScheduledBriefRun | 90 days |
| Expired / dismissed memory evidence | 90 days |
| Audit tombstones | 365 days |
| Operational logs | 30 days |
| Aggregated metrics | 90 days |

Enforcement (a job) is Delivery Phase 2; Delivery Phase 1 only *surfaces* these
read-only and states plainly they are not yet enforced.

### D63 — Derived-data deletion rules (future policy, recorded now)

When deletion ships: delete Signals only when all supporting evidence is
deleted; recompute mixed-source derived data; delete unapproved orphaned
proposals; preserve approved/executed proposal history in minimised form;
always preserve pending/uncertain execution evidence; recompute inferred memory
after evidence deletion; never delete confirmed explicit preferences merely
because inference evidence was removed.

### D64 — Rate-limiting architecture (thresholds deferred to Delivery Phase 4)

Authenticated key = user id; anonymous key = securely resolved client IP.
`X-Forwarded-For` is ignored unless the immediate peer belongs to an explicit
trusted-proxy CIDR allowlist (`TRUSTED_PROXY_CIDRS`); an empty allowlist (the
default) trusts no forwarded headers. Redis-backed limits never replace database
idempotency or concurrency guards. Numeric thresholds and enforcement land in
Delivery Phase 4; Delivery Phase 1 adds only the `trusted_proxy_cidrs` setting.

## Delivery Phase 1 design (D65)

- **Canonical surface:** the existing `/connections` route is **expanded** into
  the "Privacy & Connections" Control Centre (one page, no competing surface),
  reusing the existing connect/disconnect/sync routes and their semantics. The
  Stage 7 e2e continues to pass (the `Connections` heading is a substring of
  `Privacy & Connections`).
- **One new read-only endpoint:** `GET /privacy/summary`
  (`lifeflow_api.privacy`) returns: per-account connection summary (status,
  granted scopes with human labels, last sync, freshness band, ever-synced,
  can-disconnect/can-reconnect); owner-scoped inventory counts for all 12
  categories; and the retention classes with `enforced=False` +
  not-yet-enforced notes.
- **Safety by construction:** the response carries no token/ciphertext, no sync
  cursor, no `authorisation_revision`, no provider message/event id, no
  proposal payload/hash, and no audit `safe_metadata` internals — only counts,
  statuses, scope labels, and freshness bands. Depends only on PostgreSQL, never
  Redis (proven by a test against an unreachable Redis).
- **Scope labels** reuse `google_scopes.py`; unrecognised scopes render as a
  neutral "Other access" and requested-but-not-granted scopes never appear.
- **Four distinct controls** are explained separately: disconnect (active),
  delete-imported-data (described, not actionable), delete learned preferences
  (links to existing memory controls), delete account (described, not
  actionable). No destructive button beyond the existing disconnect exists.

## Delivery Phase 2 implementation decisions (D66–D72)

Implemented 2026-07-23. The destructive engine behind imported-data deletion,
retention enforcement, and account deletion. See
`docs/delivery/reports/stage-09-phase-2.md`.

### D66 — One durable operation model + one planner

`DataDeletionOperation` (migration `0011`) is the single durable, content-free
record for all three operation types (closed `operation_type`/`state` enums; no
free-form values). A partial unique index
(`uq_data_deletion_operations_active_scope` on `(user_id, operation_type,
scope_key)` `WHERE state IN (previewed,pending,running)`) guarantees **at most
one active operation per (user, type, scope)** — so two equivalent
preview/confirm requests can never create two concurrent destructive
operations. `deletion_planner.apply_derived_decisions` is the *single* place the
delete/preserve/recompute/minimise rules live; imported-data deletion (account
scope) and retention (age scope) both call it, so they cannot diverge.

### D67 — Retained-user anonymisation (not a hard delete)

Account deletion keeps a terminal, anonymised `users` row and clears
`google_subject`/`email`/`display_name`, sets `account_state='deleted'`,
`deleted_at`, and a random `deletion_subject_id`. This preserves the
content-free audit/execution tombstones `AuditEvent.user_id` references under ON
DELETE CASCADE — the retained-user approach the planning gate preferred, so
`AuditEvent.user_id` stays NOT NULL. `get_current_user` rejects a `deleted`
account (session invalidation); the same Google identity can create a genuinely
new account later without reviving the anonymised one.

### D68 — Snapshot boundary via `SourceItem.created_at`

`SourceItem` gains a `created_at` import timestamp (distinct from `occurred_at`,
the email/event's own date). Imported-data scope is
`source_account_id = A AND created_at <= snapshot_cutoff`, so provider data
synced **after** an operation begins is never swept into it. Chosen §7 rule:
later imports are allowed but fall outside the captured snapshot (we do not hard-
block sync during a deletion; the snapshot boundary is the guard).

### D69 — Bounded, resumable, idempotent worker

`run_operation` claims the operation atomically (conditional `UPDATE … RETURNING`
pending→running, bumping `attempt_count`), then processes bounded batches
(`DELETION_BATCH_SIZE`), committing each and updating `resume_cursor_json` +
`deleted_counts_json`. A crash leaves it `running`; the per-minute cron recovers
stale operations (heartbeat older than `DELETION_HEARTBEAT_TIMEOUT_MINUTES`) back
to `pending` for re-enqueue, or to `partially_failed` after
`DELETION_MAX_ATTEMPTS`. Re-running a completed operation is a no-op (claim only
matches `pending`); re-minimising yields the identical tombstone.

### D70 — Drain-only enqueue (Redis-outage-safe API)

The API never enqueues directly: `confirm` persists the operation as `pending`,
and the worker cron **drains** pending operations (enqueued_at NULL) onto Redis.
So preview/confirm stay available with Redis down (the operation truthfully
reports `pending`), and the queue payload is only the operation id — never
scope, counts, confirmation text, or personal data.

### D71 — Confirmation, cancellation, and mutation guards

Typed phrases: `DELETE IMPORTED DATA`, `DELETE MY LIFEFLOW ACCOUNT` (never
stored). Confirm requires the exact phrase (422 on mismatch), the expected
version (409 stale), and a non-expired preview (409); it is idempotent.
Cancellation is allowed only while `previewed`/`pending` (409 once running).
A `deletion_pending`/`deleted` account is blocked from sync, brief generation,
and proposal edit/approve/execute via the `require_active_account` guard.

### D72 — Retention enforcement is opt-in and bounded

The daily scan (`scan_and_create_retention_operations`) runs only when
`RETENTION_ENFORCEMENT_ENABLED=true`, creates at most one operation per user per
day (scope key `retention:<date>`), is capped at
`RETENTION_MAX_OPERATIONS_PER_TICK`, uses a controllable clock, and never deletes
a pending/uncertain execution or a confirmed explicit preference. The Privacy
Centre's retention disclosure only flips to "enforced" when this is genuinely on.

### D73 — Confirmation is bound to the reviewed plan (content-free fingerprint)

`snapshot_cutoff` fixes the SourceItem time boundary, but proposal/execution and
derived-data states can change between preview and confirm and alter what is
deleted/minimised/preserved. Each preview now persists a `plan_fingerprint` (a
sha256 of the affected record **ids and their planned dispositions**, plus a
`plan_policy_version`, type, scope, and snapshot) — content-free by construction
(record ids and disposition labels only; provider ids appear solely inside a
nested digest; the persisted value is a bare hex digest). At confirmation the
operation row is locked `FOR UPDATE`, the plan is recomputed against the original
snapshot, and its fingerprint is compared: unchanged → previewed→pending;
changed (or policy bumped) → the preview is **refreshed** (new counts,
fingerprint, version, expiry, still `previewed`) and a **409 `preview_changed`**
is returned carrying the refreshed preview, requiring a fresh confirmation.
Invalidating changes include: a proposal becoming approved, an execution becoming
pending/uncertain, a retained dependency added/removed, and a mixed-evidence
signal becoming fully unsupported. A later out-of-snapshot SourceItem that alters
no listed disposition does **not** invalidate. The row lock serialises racers so
two confirmers can never confirm two different plan versions.

### D74 — Real production provider revocation is wired at the worker root

Account deletion's best-effort revoker is now injected by the **worker
composition root** (`worker_app.on_startup`), reusing the same
`GoogleOAuthClient.revoke_token` the disconnect path uses
(`google_wiring.build_account_revoker`): it decrypts the stored refresh token
in-process and revokes it remotely. It is wired only when Google is configured;
demo/CI inject `None` (or a fake adapter in tests). Revocation is attempted for
each account before local records are removed and recorded as a safe
`provider_revocations` count; a remote failure never blocks local credential
erasure and yields a truthful `partially_failed` with safe code
`provider_revoke_failed`; the credentials phase never re-runs on resume (no
double revoke); and no token, provider response, or raw exception ever enters
logs, audits, operation state, or API responses.

## Delivery Phase 3 implementation decisions (D75–D78)

Committed locally 2026-07-24 as five commits from approved preparatory HEAD
`eedd69d`. See
`docs/delivery/reports/stage-09-phase-3.md`.

### D75 — Public audit history is a closed presentation registry

`AuditEvent` remains the append-only internal safety record; it is not exposed
as an API schema. `audit_history_registry.AUDIT_EVENT_PRESENTATIONS` explicitly maps each
privacy-reviewed event type to a fixed title, fixed summary, closed category,
and closed tone. Unknown/new internal events stay invisible until deliberately
registered. The renderer may derive only the closed actor label (`you` or
`lifeflow`) from the internal actor; it never interpolates metadata, entity ids,
correlation ids, action payloads, provider ids, reasons, values, counts, or raw
error details. This is a read projection, so no new capture model or migration
is required.

### D76 — One owner-scoped, read-only endpoint

`GET /audit-history` is the sole public history endpoint. It uses
`CurrentUser` and `AuditEventRepository(user.id)`; every database branch filters
by the owner and by the presentation registry's event-type allowlist. The
response contains only event id, occurrence time, closed category/actor/tone,
and the fixed rendered title/summary. There are no audit create, update, or
delete routes, and the repository still exposes no audit mutation or deletion.
The existing `(user_id, timestamp)` index supports this bounded pilot read; no
schema change is justified.

### D77 — Stable, filter-bound keyset pagination

Pages order by `(timestamp DESC, id DESC)`, query `limit + 1`, and use the final
displayed pair as the next keyset. The first page fixes an `as_of` timestamp;
later pages keep that upper bound, so concurrent inserts cannot shift or
duplicate the traversed window. The opaque URL-safe cursor carries only the
version, `as_of`, last timestamp/id, and the selected closed filters. Decoding
is strict, size-bounded, and rejects filter mismatches with 422. A cursor is
navigation state, never authority: the authenticated owner filter is reapplied
on every request.

### D78 — Canonical UI and closed filters

The canonical frontend is `/audit-history`, linked from the existing Privacy &
Connections centre and back to it. Activity is the closed set `all`, `actions`,
`briefs`, `connections`, `privacy`, `preferences`, `account`; time is `7d`,
`30d`, `90d`, or `all`. Filter changes start a new cursor window, “Load more”
appends a keyset page, and timestamps render in the user's configured timezone.
The page is a semantic ordered list with explicit actor/category/outcome text,
honest empty/error/authentication states, and no write control.

### D79 — Typed detail projection: safe action type and reason (2026-07-24)

A post-commit completeness review found that every proposal/execution/approval
audit write already carries a closed 3-value `action_type`
(`create_task`/`create_gmail_draft`/`create_calendar_event`), and several
failure-path writes carry a closed reason/error code
(`action_policy.PolicyViolationError`'s 7 codes, a small number of codes
raised directly in `action_proposal_service.py`/`action_executors.py`'s
`FinalExecutionError`, and `deletion_ops.py`'s 5 deletion/retention/
account-deletion codes) — none of it rendered. This was a presentation-layer
gap, not a missing-data problem, so `audit_history_registry.py` gained two
closed lookup functions, `safe_action_type_label`/`safe_reason_label`, and
`Presentation` gained two declaration flags, `show_action_type`/`show_reason`,
naming exactly which metadata key an event type may project and through which
closed label table. Both functions return `None` — never the raw value — for
anything absent, wrong-typed, or not in the closed table, so unregistered
future codes and historical rows written before this change (which may lack
`reason_code`/`error_code` entirely) both degrade to the same safe, silent
omission. One code (`google_client_error_{status}`) is validated structurally
rather than as a literal, since the interpolated part is a bounded HTTP status
integer, never a message body.

At this point, record counts (deleted/preserved/failed) were deliberately
**not** added: they were never written to `AuditEvent.safe_metadata_json` in
the first place — the shared `deletion.py`/`account_deletion.py`/`retention.py`
`_audit()` helper recorded only `operation_type`, `state`, and the error code
when present, while the actual counts lived solely on
`DataDeletionOperation.deleted_counts_json`/`preserved_counts_json`/
`preview_counts_json`. Projecting them would require changing that Phase 2
writer (already committed and pushed on `origin/stage-9-deletion-retention`),
which was out of this review's authority without explicit approval.

### D80 — Safe aggregate audit counts (2026-07-24, explicitly authorised)

Explicit authorisation was given to add counts to the audit writer, narrowly
scoped to the audit trail only — no change to deletion planning, batching,
preservation rules, retention eligibility, account anonymisation, or operation
state transitions. `deletion.py` gained one small helper,
`safe_aggregate_counts(operation)`, called only from the shared `_audit()`
helper and only for the three terminal suffixes where deletion actually ran
(`completed`, `partially_failed`, `failed` — never `previewed`/`requested`/
`cancelled`/`started`, which cannot yet have produced any result). It sums each
of `deleted_counts_json`/`preserved_counts_json`'s per-category values into one
flat, bounded, non-negative integer per field; a single malformed category
entry invalidates the whole total rather than under-counting. Only the two
flat totals — `deleted_count`/`preserved_count` — are ever written to the audit
event; the raw per-category JSON, with its category-name keys, is never
copied.

There is no per-record failure count anywhere in this engine — a batch either
deletes an item or defers it to a later batch, so `failed_count` is never
produced by any writer today; "failure" is an operation-level state, already
surfaced through the existing `reason` field. Separately, `retention.py` has
never populated `preserved_counts_json` at all (a pre-existing Phase 2
characteristic, not something this correction changes), so `preserved_count`
is correctly and permanently absent on retention events specifically, while
present on imported-data and account-deletion events.

On the presentation side, `Presentation` gained a third flag, `show_counts`,
set on the nine terminal deletion/retention/account-deletion event types.
`audit_history_registry.py` gained `safe_counts(metadata)`, which reads only
the three approved keys (`deleted_count`/`preserved_count`/`failed_count`),
independently re-validates each as a plain non-negative bounded integer
(rejecting booleans explicitly, since `bool` subclasses `int` in Python),
ignores every other key however it is spelled, and omits — never guesses —
anything malformed or absent. This mirrors the writer's own validation rather
than trusting it, so a future writer bug cannot leak an unbounded or malformed
value through the API. The frontend renders each present count as a plain
sentence ("36 records deleted", "1 record preserved for reconciliation") with
correct singular/plural wording, omits zero-value counts as noise, and never
implies a preserved record was also deleted.

## Delivery Phase 4 implementation decisions (D81)

Implemented on `stage-9-rate-limiting` (base: the final Phase 3 tip
`a50cf06`), verified in the working tree 2026-07-24, pending review and
commit. See `docs/delivery/reports/stage-09-phase-4.md`.

### D81 — Layered, privacy-conscious rate limiting (thresholds from D64, now enforced)

D64's architecture (authenticated key = user id, anonymous key = securely
resolved client IP, `TRUSTED_PROXY_CIDRS`-gated forwarded-header trust,
Redis-backed limits that never replace database guards) is now implemented
and enforced, closing threat model T21.

- **Closed policy registry** (`rate_limit_policy.py`): sixteen named token-bucket
  policies (`capacity` = safe burst allowance and initial fill;
  `refill_amount`/`refill_window_seconds` = the steady-state rate), covering
  every state-changing route plus the two stronger read buckets
  (`authenticated_read`, `privacy_audit_read`). Unregistered codes raise at
  lookup; `RATE_LIMIT_POLICY_OVERRIDES_JSON` is validated once at startup
  (unknown policy, unknown field, non-positive or non-integer value all fail
  configuration validation, never apply silently).
- **Trusted-proxy client IP** (`rate_limit_ip.py`): the immediate socket peer
  is the sole trust anchor; `X-Forwarded-For` is consulted only when that peer
  is itself within `TRUSTED_PROXY_CIDRS` (empty, the default, trusts nothing).
  A trusted chain is walked right-to-left, skipping trusted hops, to the first
  untrusted address; a malformed or overlong chain (bounded by
  `RATE_LIMIT_MAX_FORWARDED_HOPS`) falls back to the immediate peer rather
  than granting a fresh identity. IPv4-mapped IPv6 normalises to IPv4.
- **The Uvicorn proxy-boundary defect (found, fixed, and now regression-tested).**
  This resolver only ever sees `request.client.host` — but Uvicorn's own
  `--proxy-headers`/`--forwarded-allow-ips` machinery runs *before* the ASGI
  app does, and its default trusts `X-Forwarded-For` from any loopback
  connection, rewriting `request.client` itself. The Phase 4 manual smoke
  test (not any automated test — `httpx.ASGITransport`, used by every other
  test in this suite, never runs Uvicorn's `ProxyHeadersMiddleware` at all)
  found this: with `TRUSTED_PROXY_CIDRS` empty, a spoofed
  `X-Forwarded-For: 9.9.9.9` from `127.0.0.1` was still honoured, because
  Uvicorn had already substituted it into `request.client` upstream of
  `rate_limit_ip.py`. **Fix:** every launch site now passes
  `--forwarded-allow-ips=""` (empty — Uvicorn itself trusts nothing;
  `TRUSTED_PROXY_CIDRS` inside the application is the only real trust
  boundary), enforced by `scripts/check_uvicorn_launch_safety.py` (wired into
  pre-commit and `secret-scan.yml`) and proven end-to-end by a real-Uvicorn
  regression, `test_rate_limit_uvicorn_regression.py` (not
  `ASGITransport`-based, so it actually exercises Uvicorn's header handling).
  **Deployment guidance:** a real deployment sitting behind a genuine
  reverse proxy (a load balancer, Cloud Run, nginx) must still launch Uvicorn
  with `--forwarded-allow-ips=""` — never rely on Uvicorn's own independent
  forwarded-header trust as the security boundary — and instead set
  `TRUSTED_PROXY_CIDRS` to the proxy's actual address/CIDR, so the
  application's own resolver (audited, tested, privacy-safe) is what decides
  whether a forwarded address is trusted, with Uvicorn itself always passing
  the unmodified real TCP peer through.
- **Privacy-safe Redis keys** (`rate_limiter.py`): a bucket key is
  `{prefix}:{policy_code}:{digest}`, where `digest` is
  `HMAC-SHA256(RATE_LIMIT_KEY_SECRET, "{subject_type}:{subject}")` — never a
  raw user id, IP, or path parameter. `RATE_LIMIT_KEY_SECRET` is independent
  of user data, never logged; production refuses to start with
  `RATE_LIMITING_ENABLED=true` and a secret under 32 characters, while
  development/test may leave it blank (an ephemeral secret is generated,
  exactly like `SESSION_SECRET`).
- **Atomic Redis token bucket**: one Lua script performs the entire
  read-refill-consume-write cycle inside a single Redis command (no
  read-then-write race), using Redis's own `TIME` command as the clock so
  every API instance agrees regardless of local clock skew. A bucket's TTL is
  bounded so an abandoned key always expires.
- **Fail-open on Redis failure**: any Redis error (timeout, connection
  failure, unexpected reply) allows the request and marks the decision
  `degraded`, never returning a misleading 429 and never touching any
  existing database guard (idempotency, approval binding, plan-fingerprint
  binding, active-operation uniqueness all stay fully authoritative
  regardless of limiter state).
- **One reusable dependency** (`rate_limit_deps.py`): `RateLimited(code)` is
  the only way a route declares a policy, evaluated once at route-declaration
  time against the closed registry. The one exception is the shared
  `POST /privacy/deletion-operations/{id}/confirm` route, which serves both
  ordinary and account-deletion confirmations through one path: it resolves
  `account_deletion_confirm` vs. `deletion_confirm_cancel` from a
  side-effect-free, owner-scoped read of the operation's type *before*
  charging exactly one policy, then proceeds to the unchanged, independently
  authoritative `confirm_operation` (its own `FOR UPDATE` lock and
  fingerprint/version validation are untouched).
- **Idempotent replays**: every policy documents (via
  `applies_to_idempotent_replays`) that a replay still consumes a token —
  broad request-volume control is a separate concern from database
  idempotency, which remains authoritative regardless of what the limiter
  allowed through. A blocked replay therefore never duplicates a record; an
  allowed replay returns the pre-existing result unchanged.
- **Safe 429 contract**: `errors.py` gained `RateLimitExceededError`, handled
  through the existing `{"error": {code, message, correlation_id}}` envelope
  (429 already mapped to `"rate_limited"`) plus one additional field,
  `retry_after_seconds` (bounded, non-negative), and a matching `Retry-After`
  header — never a policy code, bucket key, digest, or subject.
- **Frontend**: `RateLimitError` (a typed `ApiError` subclass carrying
  `retryAfterSeconds`) and a shared `RateLimitNotice`/`rateLimitMessage`
  helper render a rounded, accessible retry guidance message
  (`role="alert"`) on Today (brief generation), the approval panel (approve/
  execute), and the Connections deletion controls (sync, preview, confirm,
  cancel) — never shown as a provider failure or an uncertain execution
  outcome, never auto-resubmitted, and never clearing already-typed
  confirmation phrases or reviewed preview state.
- **Route coverage**: a test walks the live FastAPI route table and asserts
  every state-changing route carries a `rate_limit_deps` dependency or is on
  a short, justified exemption list (`/health`, `/ready`, `/config`, and
  FastAPI's own docs routes) — a new unclassified route fails the test.
- **Off by default**: `RATE_LIMITING_ENABLED` defaults to `false`, matching
  every other Stage 8/9 feature flag; the entire pre-existing test suite and
  every existing Playwright journey are unaffected. Playwright's own new
  throttling journeys (`rate-limiting.spec.ts`) enable it for the e2e API
  process only, with small, explicitly justified policy overrides scoped to
  exactly the policies those journeys exercise.

No migration was needed — rate-limit state lives entirely in Redis and
validated configuration, matching D64's original architecture note.

## Delivery Phase 5 implementation decisions (D82–D91)

### D82 — A closed operational failure taxonomy, not per-module ad hoc codes

`failure_taxonomy.py` defines one `FailureCode` enum and a `classify_exception`
function used everywhere a Google, Redis, database, or unknown exception needs
a safe code, message, retryability, and severity. Pre-existing untyped string
constants in `scheduled_briefs.py` (`ERROR_WORKER_STALE_TIMEOUT`,
`ERROR_DATABASE_UNAVAILABLE`, `ERROR_REDIS_UNAVAILABLE` → renamed internally to
the enum's `redis_unavailable`, `ERROR_GENERATION_FAILED`,
`ERROR_WORKER_TIMEOUT`) now alias the enum's values — byte-identical strings,
zero behaviour change, but a single source of truth going forward.
`deletion_ops.py` keeps its own literal constants unchanged: that module is
deliberately dependency-light (models only, to avoid an import cycle), so its
matching string values are consistent by construction rather than by import.

### D83 — Central, validated timeout policy; write timeout ≠ "didn't happen"

`timeouts.py` + new `Settings` fields (`GOOGLE_CONNECT_TIMEOUT_SECONDS`,
`GOOGLE_READ_TIMEOUT_SECONDS`, `GOOGLE_WRITE_TIMEOUT_SECONDS`,
`DATABASE_STATEMENT_TIMEOUT_SECONDS`, `WORKER_HEALTH_CHECK_TIMEOUT_SECONDS`,
all `Field(gt=0)`) replace the flat, hand-rolled `httpx.AsyncClient(timeout=10.0)`
at every construction site (`main.py`, `worker_app.py`) and the previously
unbounded PostgreSQL statement duration (`db.py::create_engine`, via asyncpg
`server_settings`). Gmail/Calendar writes (`create_draft`, `insert_event`) get
a longer, separately-configured read budget than the shared client's default —
a local timeout on a write must never be treated as proof the request never
reached Google; it is classified identically to a connection error
(`GoogleTransientError` → `uncertain`, never `failed`).

### D84 — Bounded retry with backoff/jitter, reads only, by construction

`retry.py::retry_read` wraps every idempotent Gmail/Calendar read
(`list_messages`, `get_message`, `list_history`, `get_current_history_id`,
`list_events`) and the two post-write verification reads (`get_draft`,
`get_event`), plus OAuth token refresh (idempotent under RFC 6749 §6). It is
never applied to `create_draft`, `insert_event`, or any other write. On
exhaustion it re-raises the *original* exception unchanged — never a wrapper
type — so every existing `except GoogleTransientError`/`GoogleHistoryExpiredError`/
`GoogleClientError` control-flow branch throughout the connectors and
executors is unaffected whether the underlying call succeeded on the first
attempt or the last. Proven negative: two dedicated tests
(`test_gmail_draft_create_is_never_automatically_retried`,
`test_calendar_event_insert_is_never_automatically_retried`) count actual
transport calls and assert exactly one POST per write attempt.

### D85 — Circuit breaker evaluated and deliberately omitted

No circuit breaker was added. Reasoning: (1) Google API concurrency here is
bounded by the number of concurrently active human users (pilot scale), not a
shared fan-out pool a breaker would protect; (2) the existing per-account
`ConnectedAccount.status` state machine (`active`/`revoked`) already
implements the one legitimate circuit-breaking case — a revoked grant stops
future calls to that account without ever reaching Google again until
reconnection — at the correct (per-account, not global) granularity a naive
shared breaker would get wrong (§9's own warning against "one user
permanently opening a circuit for everyone"); (3) bounded timeouts (D83),
bounded read retries (D84), and the pre-existing durable `uncertain` outcome
model together already deliver fast failure, backoff pressure relief, and
zero duplicate side effects — the three properties a breaker exists to
provide — without new shared mutable state or a new Redis-outage failure mode
of its own. Revisit if real pilot telemetry (D91) shows repeated storms a
timeout+retry combination isn't already absorbing.

### D86 — Proactive stale-pending-execution recovery sweep

`action_proposal_service.recover_stale_pending_executions` (new,
cross-user) + a new per-minute cron job (`worker_app.recover_stale_action_executions`)
close a gap the durable-execution model had relative to the deletion engine
and scheduled-brief subsystems: before this, an `ActionExecution` stuck
`pending` past `STALE_PENDING_AGE` (a worker crash between the pre-call
commit and the real executor call) was only ever durably resolved to
`uncertain` if that specific proposal happened to be acted on again, or
displayed as `uncertain` without being persisted. The sweep uses the same
audit event (`execution.uncertain`, `reason_code: stale_pending_attempt`)
`execute()`'s own re-entry guard already writes — an existing safe outcome,
now also reached proactively. No new terminal state, no new retry.

### D87 — Redis-enqueue failures fail open, matching the rest of the app

Two genuine gaps found by inventory: `deletion.py::_enqueue` (used by both
the stale-`running`→`pending` requeue and the pending-drain pass) and three
enqueue call sites in `scheduled_briefs.py` (`dispatch_tick`,
`recover_stale_running`, the transient-retry re-enqueue in
`run_scheduled_generation`) let an uncaught `redis.exceptions.*` propagate
out of the whole cron function — aborting recovery for every other
user/operation in the same tick, not just the one Redis-affected row. Both
now catch, log, and leave the row `pending`/`enqueued_at=None` for the next
tick's drain pass — the identical self-healing pattern the rate limiter and
`memory_inference.enqueue_recompute` already used. A new
`scheduled_briefs._recover_never_enqueued` pass (mirroring the deletion
engine's existing pending-drain) closes the matching gap for scheduled-brief
runs, which had no prior drain mechanism at all.

### D88 — `/ready` reports Redis degradation without blocking readiness

`GET /ready` now also best-effort pings Redis (`health.py::check_redis`,
timeout from D83's `WORKER_HEALTH_CHECK_TIMEOUT_SECONDS`) and reports
`degraded_dependencies: ["redis"]` in an otherwise-`200` response — never
`503` — since Redis absence does not compromise the API's core functions
(rate limiting is fail-open, D64; scheduled-brief/worker status has its own
dedicated, unaffected endpoint). `check_redis` replaces and is shared with
`scheduled_brief_status.py`'s previously duplicated local copy. `/health`
(liveness) is unchanged and remains provider- and Redis-agnostic by design.
`/metrics` (D90) joins `/health`/`/ready`/`/config` on the rate-limit
exemption list for the same never-throttle reasoning.

### D89 — Worker-scoped correlation IDs

`correlation.py::with_worker_correlation`, applied to all seven ARQ job/cron
entry points in `worker_app.py`, is the background-job analogue of
`CorrelationIdMiddleware`: an ARQ job has no inbound HTTP request to take a
correlation id from, so before this every job/cron log line carried the
middleware's `"-"` default. Each invocation now gets a fresh id for its
duration (never a reused/caller-supplied one — a job has no caller to honour
in that sense), readable via the same `get_correlation_id()` any nested
domain-service log call already uses.

### D90 — Bounded-cardinality metrics via `prometheus-client`

New minimal dependency (`prometheus-client`, no transitive dependencies of
its own) — a small exposition-format client library, not an observability
platform, chosen over hand-rolling Prometheus's text format. `metrics.py`
defines one process-local `CollectorRegistry` and a fixed set of
counters/histograms whose labels are always closed, small registries
(provider name, operation name, `FailureCode` value, registered rate-limit
policy code, job name) — never a user id, email, proposal id, exception
message, or IP address. Wired into: rate-limiter fail-opens, 429 rejections
by policy, `/ready`'s DB/Redis outcomes, Google write + verification-read
calls (`create_draft`, `get_draft`, `insert_event`, `get_event` — the
ingestion read path is intentionally not instrumented in this phase, see the
Phase 5 report's Known Limitations), worker job success/failure
(`with_worker_metrics`), and every stale-recovery sweep's recovered count.
Exposed at `GET /metrics` (Prometheus text exposition format).

### D91 — Safe API error contract gains `retryable`/`dependency`, additively

`ErrorBody` gains two new optional fields, both `None` unless a route has a
genuine closed-taxonomy answer: `retryable: bool | None` and
`dependency: str | None` (today, only ever `"google"`). Wired into the one
route where it adds real signal today — `POST /connected-accounts/google/sync`'s
generic `GoogleApiError` handler, via `classify_exception` — replacing one
undifferentiated `"Google sync could not complete."` message with a
transient/permanent distinction the frontend now surfaces as two visually
and textually distinct notices (`role="status"`, amber, "safe to try again"
for transient; `role="alert"`, red, "will not help — reconnect" for
permanent). Purely additive to the existing envelope shape — every other
route's error body is unchanged except for gaining these two `null`-valued
keys.

### D92 — Test-only provider-control boundary: a fake Google server, not a new production route

The four Playwright outage-simulation journeys (§20) need a way to make
Gmail/Calendar transport fail on demand. Rather than adding any control
surface to the production API, the fault injection lives entirely in a
separate standalone ASGI app (`lifeflow_api/testing/fake_google_server.py`)
that is never imported by `main.py` and refuses to start (`SystemExit` at
import time) unless `LIFEFLOW_E2E_FAKE_GOOGLE=1` is set. The real API is
redirected to it only via two settings — `e2e_test_controls_enabled` and
`google_api_origin_override` — both `false`/empty by default, both ignored
unless the flag is explicitly on, and `create_app` refuses to start
(`RuntimeError`) if the flag is ever `true` with `environment=production`.
`GmailDraftClient`/`CalendarEventClient` gained a `base_url` constructor
parameter (defaulting to the real Google host) so the override is plain
configuration, not a weakened abstraction. The fake server's own fault
vocabulary (`Scenario`: `healthy`, `transient_then_recover`,
`permanent_failure`, `auth_expired`, `hang_on_write`) and its targetable
operation vocabulary are both closed enums, validated on every
`POST /__control__/scenario` call (422 on anything else). It never accepts
or checks a real bearer token, never proxies to a real Google host, and
exposes only synthetic object/call counts via `GET /__control__/state`.

### D93 — Provider-read metrics extended to the full ingestion path; a dedicated timeout outcome

The scope initially left the bulk Gmail/Calendar ingestion reads
uninstrumented (only the write + verification-read call sites were
wrapped). Closing that: `list_messages`, `get_message`, `list_history`,
`get_current_history_id` (Gmail), `list_events` (Calendar), and
`refresh_access_token` (OAuth) are now all wrapped in
`observe_provider_call`. The outcome vocabulary grew from five values to
eight to keep it meaningful rather than dumping everything into
`unknown_error`: `history_expired` and `sync_token_expired` (routine resync
triggers, not failures) and `grant_invalid` (a revoked refresh token) each
get their own bucket. A `GoogleTransientError` whose `__cause__` is an
`httpx.TimeoutException` (set by the `raise ... from exc` every client's
`_get`/`_post` helper already used) is classified as the dedicated
`"timeout"` outcome and additionally increments
`lifeflow_provider_timeouts_total` — a deliberate double count (one counter
answers "what kind of outcome", the other "did this dependency time out"),
not an accidental one. An HTTP 429/5xx-derived `GoogleTransientError` (no
`__cause__`) keeps the ordinary `"transient_error"` outcome — a real
provider response, not a timeout.

### D94 — Worker structured logging was wired but never installed (fixed)

`with_worker_correlation` binds a fresh correlation id into a contextvar
for the duration of one job, and `logging_setup.JsonFormatter` reads that
contextvar into every log line's `correlation_id` field — but
`worker_app.py::on_startup` never called `configure_logging`, so the
worker process used Python's default plain-text logging the entire time,
silently dropping the correlation id this phase's other work had already
built. Found during Delivery Phase 5's own live manual verification (§21)
when a worker log inspection came back with no JSON at all. Fixed with a
single `configure_logging(settings.log_level)` call in `on_startup`,
identical to `main.py::create_app`'s own call — an ordinary wiring gap, not
a design change, closed with a regression test
(`test_on_startup_configures_structured_logging`).

### D95 — Outage journeys run on their own dedicated stack, never alongside the shared one

`apps/web/e2e-resilience/` and `scripts/e2e-resilience.sh` are a separate
Playwright config and stack (API on :8011, fake Google on :8098, web on
:3001), not a project bolted onto the existing `playwright.config.ts`.
Two reasons this had to be a separate stack: the fake-Google origin
override and `GOOGLE_OAUTH_ENABLED=true` must never be active for the
other 10 journeys (`connections.spec.ts` explicitly depends on Google OAuth
being unconfigured); and Journey D stops/starts the real Postgres/Redis
containers, which would break whichever of the other journeys happened to
be running concurrently against the same containers. The dedicated API
process (port 8011) is deliberately *not* a Playwright `webServer` entry —
Journey B kills and respawns it mid-test (a real OS-level process restart,
not a simulation) to prove an uncertain provider write is never retried
across an API restart, and Playwright's `webServer` supervision is not
designed to survive one of its own entries being killed out from under it.
A genuine bug surfaced building this: `lsof -ti:PORT` matches a socket by
port number on *either* end of a connection, not just the listener —
killing "whatever is on :8011" this way also matched the Playwright test
process's own outbound keep-alive connection to the API, SIGKILLing the
test runner itself. Fixed with `lsof -ti tcp:PORT -sTCP:LISTEN`, which
restricts the match to the actual listening socket.

No migration was needed for any Delivery Phase 5 decision — every mechanism
above lives in application code, Redis, or in-process state.

## Consequences

Delivery Phase 1 gives the user a truthful, consolidated view and keeps every
destructive capability out until its engine and previews exist. The retention
values and deletion semantics are fixed here so Delivery Phase 2 implements a
pre-agreed contract. Delivery Phase 2 ships that engine end-to-end with previews,
typed confirmation, durable bounded/resumable execution, retention enforcement,
and account anonymisation. Delivery Phase 3 adds the privacy-safe audit-history
read projection and canonical UI without changing capture or deletion
semantics. Delivery Phase 4 enforces the rate-limiting architecture D64
described, as defence-in-depth layered strictly on top of — never in place
of — every existing database guard. Delivery Phase 5 makes provider, queue,
and database failures bounded, classified, observable, and — where safe —
recoverable, without weakening any invariant the earlier four phases
established: writes are still never retried automatically, an uncertain
outcome is still never silently treated as success, and no new mechanism
(the failure taxonomy, timeout policy, retry helper, stale-execution sweep,
enqueue hardening, readiness reporting, correlation IDs, or metrics) stores
anything beyond a safe, closed-vocabulary code, count, or bounded internal
identifier. See
`docs/delivery/reports/stage-09-phase-1.md` and
`docs/delivery/reports/stage-09-phase-2.md` and
`docs/delivery/reports/stage-09-phase-3.md` and
`docs/delivery/reports/stage-09-phase-4.md` and
`docs/delivery/reports/stage-09-phase-5.md`.
