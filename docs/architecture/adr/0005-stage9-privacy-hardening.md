# ADR 0005 — Stage 9: privacy, deletion, retention, audit UX, resilience

**Status:** accepted (planning gate approved 2026-07-22); Delivery Phase 1 implemented 2026-07-22.
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

## Consequences

Delivery Phase 1 gives the user a truthful, consolidated view and keeps every
destructive capability out until its engine and previews exist. The retention
values and deletion semantics are fixed here so Delivery Phase 2 implements a
pre-agreed contract. See `docs/delivery/reports/stage-09-phase-1.md`.
