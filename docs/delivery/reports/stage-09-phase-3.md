# Stage 9 Delivery Phase 3 Completion Report — Audit History

**Branch:** `stage-9-audit-history`
**Committed parent:** `eedd69d97bcdde66ffdb5c6890bdd6037f84df89`
**Immutable Delivery Phase 2 ancestor:** `fdb46368732a0a26f72e74062704623a55a85c6d`
**Date:** 2026-07-24

Delivery Phase 3 is committed locally as seven commits on `stage-9-audit-history`.
Nothing has been tagged, pushed, or merged. Delivery Phases 4 and 5 have not
begun, Stage 9 is not complete, and Stage 9 has not been merged to `main`.

Implementation began under OpenAI Codex and was handed to Claude after Codex's
usage allowance was exhausted mid-task. Claude independently re-verified the
entire working tree from a cold read (not from Codex's self-reported numbers)
before continuing: every `record_audit_event`/`_audit` call site in the
codebase was cross-checked against the presentation registry, and one gap was
found and fixed — see "Correction made during handoff review" below. Every
number in the Verification table below was re-run by Claude.

## Outcome

LifeFlow now has one canonical, owner-only audit-history experience at
`/audit-history`. It presents privacy-reviewed plain-language summaries of
known audit events, supports closed activity/time filters and stable keyset
pagination, and links bidirectionally with Privacy & Connections. Raw internal
audit data never crosses this API boundary.

## Delivered scope

### Closed presentation registry

`lifeflow_api.audit_history_registry.AUDIT_EVENT_PRESENTATIONS` is the closed
public vocabulary, in its own module so registry content and API/route code
can be reviewed and committed independently. Every registered internal event
maps to a fixed title, summary, category, and tone. New/unknown internal
events remain invisible until a privacy-reviewed presentation is explicitly
added — the dict is a closed allowlist, never a best-effort lookup with a raw
fallback, so unknown events fail closed by construction.

The renderer (`audit_history.py`) derives only the closed actor label `you` /
`lifeflow`. It never interpolates or serialises raw event type, raw actor,
entity type/id, correlation id, `safe_metadata_json`, payload, reason,
memory/preference value, provider identifier, count, or error detail. No
metadata-key allowlist/validator was added on the read side because none is
needed: the renderer never reads `safe_metadata_json` at all, so there is no
metadata path for an allowlist to guard against. Write-side validation
(rejecting secret-shaped metadata keys) already exists in `audit.py` from
Stage 9 Phase 1 and is unchanged.

### Owner-scoped read API

`GET /audit-history`:

- authenticates through `CurrentUser`;
- constructs `AuditEventRepository(session, user.id)`;
- reapplies the owner predicate on every page, in the same query as the
  event-type allowlist and before the `LIMIT`;
- filters event types through the closed registry before rendering;
- returns only `id`, `occurred_at`, closed `category`/`actor`/`tone`, and fixed
  `title`/`summary`;
- exposes no audit create, update, or delete route.

The audit repository gained one read-only `list_history_page` method and still
has no update/delete method. The append-only capture model and all Phase 2
deletion semantics are unchanged.

### Stable keyset pagination and closed filters

Activity filters are exactly `all`, `actions`, `briefs`, `connections`,
`privacy`, `preferences`, and `account`. Time filters are exactly `7d`, `30d`,
`90d`, and `all`. Page size is bounded to 1–50.

Rows order by `(timestamp DESC, id DESC)`. The first page freezes an `as_of`
upper bound; each cursor carries the last displayed key plus that bound and the
selected filters. Strict decoding validates the cursor version, exact fields,
types, timezone-aware timestamps, UUID, and filter binding; malformed or
mismatched cursors return 422. A cursor is navigation state, never authority.

### Canonical frontend and Privacy integration

`/audit-history` is an accessible ordered timeline with:

- activity and time-period selects;
- user-timezone rendering;
- explicit actor, category, and outcome text;
- honest loading, empty, unauthenticated, API-error, retry, and load-more
  states;
- no audit mutation control.

Privacy & Connections now links to the canonical route, and Audit history links
back to Privacy & Connections and Today.

### Contracts, browser journey, and documentation

- OpenAPI and generated TypeScript contracts include only the public projection.
- The Playwright journey creates a fresh synthetic owner, generates a brief,
  rejects an action with a private sentinel reason, navigates from Privacy &
  Connections, verifies safe summaries and absent internals, exercises the
  closed filters, and returns through the canonical link.
- ADR 0005 D75–D78, the threat model, stage plan, assumptions/decisions,
  README, repository instructions, metrics, and the manual checklist record the
  implemented boundary.

## Correction made during handoff review

Cross-checking every internal `event_type` literal actually written by the
codebase (accounts, action proposals, extraction, memory, memory inference,
demo mode, auth, briefs, ingestion, retention, preferences, scheduled briefs,
and the shared deletion/retention audit helper) against the registry surfaced
one gap: `cancel_operation` (existing Phase 2 route) accepts any owner-scoped
operation in `pending`/`previewed` state regardless of type, and retention
operations — already visible via the existing `GET
/privacy/deletion-operations` list — are created directly in `pending`. A user
could therefore legitimately cancel a still-pending retention operation, but
the resulting `retention.operation_cancelled` event had no presentation entry
and would have silently vanished from their history (fail-closed, not a leak —
no crash, no raw data exposure — but incomplete). Fixed by adding the missing
registry entry plus regression tests. The two adjacent combinations,
`retention.operation_previewed`/`requested`, were confirmed unreachable —
retention operations are never created in, nor ever transition through, the
`previewed` state — so their absence is correct and required no change.

During the same review, `audit_history.py` was split into
`audit_history_registry.py` (the closed presentation registry — no FastAPI
dependency) and `audit_history.py` (the authenticated route, cursor logic, and
response schemas), so the registry and the API can be reviewed, tested, and
committed as independent concerns. This is a pure code-organisation change:
behaviour, routes, and schemas are unchanged.

## Presentation completeness correction (2026-07-24)

A follow-up review asked whether the committed Phase 3 timeline under-renders
detail the underlying audit writers already capture safely. Inspecting every
`record_audit_event`/`_audit` call site (not inferring from `safe_metadata_json`
shape alone) found three gaps, all now fixed:

- **`action_type`** — a closed 3-value field (`create_task`/`create_gmail_draft`/
  `create_calendar_event`) is written on every single proposal/execution/
  approval audit call (verified systematically across all ~17 event types in
  that category) and was never rendered.
- **`reason_code`/`error_code`** on `approval.denied`, `execution.denied`,
  `execution.uncertain`, `execution.failed`, and the deletion/retention/
  account-deletion failure events — drawn from closed, hand-written code
  vocabularies (`action_policy.PolicyViolationError`'s 7 codes,
  `FinalExecutionError`'s ~9 codes plus one bounded parametrized HTTP-status
  case, and `deletion_ops.py`'s 5 codes) — was never rendered.
- **Record counts** (deleted/preserved) for deletion/retention/account-deletion
  events were not even in `AuditEvent.safe_metadata_json` — confirmed by
  reading `deletion.py`'s `_audit()` helper directly: it wrote only
  `operation_type`, `state`, and the error code when set. Fixing this required
  modifying that Phase 2 writer, already committed and pushed on
  `origin/stage-9-deletion-retention` — **explicit authorisation was given** to
  make this one narrow, audit-only addition (ADR 0005 D80). No deletion
  planning, batching, preservation rule, retention eligibility, account
  anonymisation, or state-transition logic was touched.

**action_type/reason (ADR 0005 D79):** `Presentation` gained
`show_action_type`/`show_reason` declaration flags, and
`audit_history_registry.py` gained `safe_action_type_label`/`safe_reason_label`
— two closed lookup functions that return `None` for anything absent,
wrong-typed, or unregistered, never a raw fallback.

**Safe aggregate counts (ADR 0005 D80):** `deletion.py` gained
`safe_aggregate_counts(operation)`, called from `_audit()` only for the three
terminal suffixes (`completed`/`partially_failed`/`failed`) where deletion
actually ran; it sums each per-category counts dict into one flat, bounded,
non-negative total, invalidating the whole total (never under-counting) if any
entry is malformed. Only the two flat totals are ever written to the audit
event — never the raw per-category JSON. There is no per-record failure count
anywhere in this engine, so `failed_count` is never produced by any writer; and
`retention.py` has never populated `preserved_counts_json` at all (pre-existing,
unrelated to this correction), so `preserved_count` is correctly always absent
specifically on retention events. `Presentation` gained a third flag,
`show_counts`, on the nine terminal deletion/retention/account-deletion event
types; `audit_history_registry.py` gained `safe_counts(metadata)`, which
independently re-validates each of the three approved keys rather than
trusting the writer.

`AuditHistoryItem` gained five new optional fields total: `action_type`,
`reason`, `deleted_count`, `preserved_count`, `failed_count` — all closed,
independently validated values, never raw metadata. The frontend renders
`action_type` as a small badge next to the entry title, `reason` as a one-line
explanation beneath the summary, and each present count as a plain sentence
("36 records deleted", "1 record preserved for reconciliation") with correct
singular/plural wording and zero-value counts omitted as noise. See ADR 0005
D79/D80 for the full design record. This correction is implemented, tested,
and verified below, split across two commits:
`feat(stage-9): record safe aggregate counts in audit events` (the writer) and
`feat(stage-9): add typed details to audit summaries` (the presentation
layer).

## Tests added

- **Backend deletion-engine writer (`test_deletion_engine.py`, +12 tests):**
  `_sum_safe_counts`/`safe_aggregate_counts` unit behaviour (malformed/
  negative/boolean/string/float/excessive values invalidate the whole total;
  the per-category breakdown is never in the output); real end-to-end runs
  proving `completed`/`partially_failed`/`failed` audit events for
  imported-data, retention, and account-deletion all carry only the two flat,
  content-free totals (no account id, operation id, or scope descriptor); a
  provider-revoke partial failure still recording the real, non-zero deleted
  count; and a direct proof that `previewed`/`requested`/`cancelled`/`started`
  never attach counts even when the operation already has valid ones to show.
- **Backend registry (`test_audit_history_registry.py`, 8 tests):** closed
  registry shape (no duplicate/malformed entries, no residual "metadata"
  wording), `retention.operation_cancelled` presence, the exact
  "did not retry automatically" wording on `execution.uncertain`,
  `safe_action_type_label`'s/`safe_reason_label`'s closed lookup behaviour
  (known values map correctly; unknown/malformed/non-string values return
  `None`; the parametrized `google_client_error_*` code is bounded to a valid
  HTTP-status shape), a guard that no label ever equals or echoes its raw
  source code, and `safe_counts`'s closed extraction (only the three approved
  keys; malformed/negative/boolean/string/float/excessive values rejected).
- **Backend API (`test_audit_history.py`, 29 tests):** authentication/
  read-only behaviour with no side effect on read, owner isolation,
  unknown-event exclusion, raw-field sentinels, closed filters/time windows,
  equal-timestamp ordering, frozen-window pagination, no duplicates,
  filter-bound/malformed cursors, deletion-summary privacy, the
  cancelled-retention-operation fix end-to-end, connection-sync and
  execution-uncertain rendering (parametrized, 2 cases), index-catalog
  verification that the query keeps real `(user_id, timestamp)` index support,
  Gmail-draft/Calendar-event safe action labels, unknown action types omitted,
  registered/unregistered reasons, a historical shape with no optional detail
  still rendering safely, the parametrized Google error code, and — from the
  safe-counts correction — imported-data/retention/account-deletion completion
  emitting correct totals, a partially-failed operation distinguishing
  deleted/preserved totals, a non-terminal event ignoring count-shaped
  metadata defensively, a historical completion with no count keys at all
  rendering safely, negative/boolean/string/float/excessive counts all
  omitted, unknown metadata keys ignored, and the raw per-category JSON shape
  never returned. The existing append-only repository surface test
  (`test_audit.py`) now pins the one additional read method.
- **Frontend:** 11 canonical-page tests (5 typed-detail tests: safe
  action-type badge, safe reason line, both omitted when absent, validated
  counts with correct singular/plural wording, and no claim that preserved
  records were deleted plus zero-value omission) plus 1 Privacy & Connections
  link test.
- **Browser:** 1 real API/ARQ-worker/PostgreSQL Playwright journey, extended to
  drive a genuine imported-data deletion to completion and assert the rejected
  proposal's action-type badge is one of the three closed safe labels, the
  completed deletion shows the exact seeded count ("3 records deleted"), and
  no raw `create_*` action type, category breakdown, operation id, or scope
  descriptor ever appears in the DOM.

A live `EXPLAIN`-based query-plan assertion was deliberately not used: each
test creates its own near-empty audit log, and PostgreSQL's planner prefers a
sequential scan over an index on a tiny table regardless of index presence, so
a live-plan assertion would be flaky rather than meaningful. The index-catalog
test instead asserts the physical index a production-sized table would use
still exists and still covers the right columns.

## Verification

| Gate | Post-registry-split | Post-typed-detail (action_type/reason) | Post-safe-counts (final) |
|---|---|---|---|
| Git starting boundary | pass — HEAD `eedd69d`, `fdb4636` ancestor | pass — five commits now on top | pass — committed as commits 6 (writer) and 7 (presentation) |
| Backend pytest | **616 passed** in ~4m | **626 passed** in ~3.4m | **653 passed** in ~3.5m |
| Backend coverage | **91%** | **91%** | **91%** |
| Ruff format / check | pass | pass | pass |
| mypy | pass — 80 files | pass — 80 files | pass — 80 files |
| Alembic | pass — single head `0011` | pass — single head `0011` | pass — single head `0011`; no migration for the writer change either |
| Frontend Vitest | **70 passed** | **73 passed** | **76 passed** |
| ESLint / TypeScript | pass / pass | pass / pass | pass / pass |
| Repository frontend format check | pass | pass | pass |
| Production build | pass | pass | pass |
| Playwright complete suite | **7 passed** in 2.0m / 1.6m (×2) | **7 passed** in 2.2m | **7 passed** in 1.4m (includes a real completed deletion showing "3 records deleted") |
| Deterministic + action evals | pass, baseline | pass, baseline | pass, baseline |
| Contract freshness | pass, byte-identical | pass, deterministic | pass, deterministic (repeated-hash check); new count fields present |
| Metrics | 158/29/616/70/7/91% | 158/29/626/73/7/91% | **158/29/653/76/7/91%** |
| pre-commit `--all-files` | pass | pass | pass — all 10 hooks |
| detect-secrets | pass, baseline unchanged | pass, baseline unchanged | pass, baseline unchanged |
| gitleaks full history | pass | pass | pass — 35 commits, no leaks |
| `.env.example` validation | pass | pass | pass |
| `git diff --check` | pass | pass | pass |

Two flaky tests were found and fixed during this work, both the same class of
issue as an earlier documented flake (a coincidental digit match inside a
UUID/timestamp, not a real leak):

- `test_typed_details_never_expose_raw_metadata_or_google_status_message`
  asserted the bare substring `"503"` was absent from the whole response.
  Fixed to rely on exact-value equality for `reason` (already fully proving no
  interpolation) plus a precise check that the full raw code string is absent.
- `test_malformed_counts_are_omitted[negative]` asserted the bare substring
  `"-1"` was absent from the whole response; a generated UUID's hyphen
  followed by a digit ("...3-104b...") produced a false failure. Fixed to rely
  on the exact `deleted_count is None` field check alone, which is sufficient
  and deterministic.

Both were verified stable across repeated runs after the fix, and clean across
every subsequent full-suite and Playwright run in this report.

## Focused verification corrections

The first complete Playwright run was 6/7 because Playwright's non-exact
`Audit history` heading locator also matched the screen-reader-only `Audit
history results` heading. The assertion was made exact; no product code or
privacy assertion was weakened. The complete rerun passed 7/7.

A backend privacy test initially asserted that the substring `42` was absent
from the whole JSON response; a run at minute 42 correctly found those digits
inside the public timestamp. The test now asserts the forbidden raw field name
`deleted_counts` is absent, which directly and deterministically verifies the
intended disclosure boundary.

Both corrections above were made and verified before this handoff; Claude's
independent full-suite reruns (7/7 Playwright twice consecutively, full
backend suite green) show no recurrence of either flake and no new one.

## Security and privacy review

- Another owner's registered event and metadata sentinel never appear.
- Unknown event types never appear.
- Raw metadata, event type, actor, entity/correlation fields, rejection reason,
  values, counts, and error detail never appear.
- The endpoint is read-only and leaves the audit row count unchanged.
- Same-timestamp events have deterministic UUID tie-breaking.
- Concurrent later inserts cannot shift a cursor's frozen page window.
- Malformed, wrong-typed, and filter-mismatched cursors fail closed with 422.
- No new OAuth/provider scope, external side effect, or framework was added.

## Explicitly excluded

No rate limiting; trusted-proxy implementation; general outage resilience;
telemetry/logging expansion; deletion-engine or retention-policy change; audit
mutation/deletion route; raw audit metadata; new provider scope; Delivery Phase
4; or Delivery Phase 5 work.

## Git and remote status

Committed as seven commits on `stage-9-audit-history`, all reachable from the
approved preparatory HEAD `eedd69d`: presentation registry, audit history API,
Audit History frontend, tests and Playwright, documentation, safe aggregate
counts in the deletion/retention/account-deletion audit writer, and the typed
action-type/reason/counts presentation layer. `fdb4636` remains an ancestor;
`origin/stage-9-deletion-retention` remains the Phase 2 remote boundary at
`fdb4636`, unchanged and not amended. Nothing has been tagged, pushed, or
merged; no `origin/stage-9-audit-history` tracking ref and no Stage 9 tag
exist.

## Stop point

Delivery Phase 3, including the presentation completeness correction (D79
action-type/reason, D80 safe aggregate counts), is committed locally as seven
commits and fully verified. Do not push, tag, merge, or begin Delivery Phase 4
without explicit approval.
