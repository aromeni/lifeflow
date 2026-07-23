# ADR 0005 — Stage 9: privacy, deletion, retention, audit UX, resilience

**Status:** accepted (planning gate approved 2026-07-22); Delivery Phase 1 implemented 2026-07-22; Delivery Phase 2 implemented 2026-07-23.
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

## Consequences

Delivery Phase 1 gives the user a truthful, consolidated view and keeps every
destructive capability out until its engine and previews exist. The retention
values and deletion semantics are fixed here so Delivery Phase 2 implements a
pre-agreed contract. Delivery Phase 2 ships that engine end-to-end with previews,
typed confirmation, durable bounded/resumable execution, retention enforcement,
and account anonymisation. Audit history is Delivery Phase 3, rate limiting
Delivery Phase 4, resilience/telemetry Delivery Phase 5. See
`docs/delivery/reports/stage-09-phase-1.md` and
`docs/delivery/reports/stage-09-phase-2.md`.
