# ADR 0005 — Stage 9: privacy, deletion, retention, audit UX, resilience

**Status:** accepted (planning gate approved 2026-07-22); Delivery Phase 1 implemented 2026-07-22; Delivery Phase 2 implemented 2026-07-23; Delivery Phase 3 committed and pushed 2026-07-24 (`origin/stage-9-audit-history` at `a50cf06`, D75–D80); Delivery Phase 4 (rate limiting, D81) is implemented, verified, and committed locally as six commits on `stage-9-rate-limiting` from the approved parent `a50cf06`, awaiting remote finalisation (not pushed, not tagged, not merged).
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
of — every existing database guard. Resilience/telemetry remains Delivery
Phase 5. See
`docs/delivery/reports/stage-09-phase-1.md` and
`docs/delivery/reports/stage-09-phase-2.md` and
`docs/delivery/reports/stage-09-phase-3.md` and
`docs/delivery/reports/stage-09-phase-4.md`.
