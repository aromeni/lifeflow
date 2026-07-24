# Stage 9 Delivery Phase 3 Completion Report — Audit History

**Branch:** `stage-9-audit-history`
**Committed parent:** `eedd69d97bcdde66ffdb5c6890bdd6037f84df89`
**Immutable Delivery Phase 2 ancestor:** `fdb46368732a0a26f72e74062704623a55a85c6d`
**Date:** 2026-07-24

Delivery Phase 3 is committed locally as five commits on `stage-9-audit-history`.
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

## Tests added

- **Backend registry (`test_audit_history_registry.py`, 3 tests):** closed
  registry shape (no duplicate/malformed entries, no residual "metadata"
  wording), `retention.operation_cancelled` presence, and the exact
  "did not retry automatically" wording on `execution.uncertain`.
- **Backend API (`test_audit_history.py`, 9 tests):** authentication/read-only
  behaviour with no side effect on read, owner isolation, unknown-event
  exclusion, raw-field sentinels, closed filters/time windows,
  equal-timestamp ordering, frozen-window pagination, no duplicates,
  filter-bound/malformed cursors, deletion-summary privacy, the
  cancelled-retention-operation fix end-to-end, connection-sync and
  execution-uncertain rendering (parametrized, 2 cases), and index-catalog
  verification that the query keeps real `(user_id, timestamp)` index support.
  The existing append-only repository surface test (`test_audit.py`) now pins
  the one additional read method.
- **Frontend:** 5 canonical-page tests plus 1 Privacy & Connections link test,
  covering safe rendering, timezone/actor/category/outcome text, filter reset,
  cursor-based append, empty/auth/error/retry states, and the canonical link.
- **Browser:** 1 real API/PostgreSQL Playwright journey.

A live `EXPLAIN`-based query-plan assertion was deliberately not used: each
test creates its own near-empty audit log, and PostgreSQL's planner prefers a
sequential scan over an index on a tiny table regardless of index presence, so
a live-plan assertion would be flaky rather than meaningful. The index-catalog
test instead asserts the physical index a production-sized table would use
still exists and still covers the right columns.

## Verification

| Gate | Result |
|---|---|
| Git starting boundary | pass — branch `stage-9-audit-history`, HEAD `eedd69d`, `fdb4636` immutable ancestor, clean starting tree/index; re-confirmed by Claude on handoff |
| Backend pytest | **616 passed** in ~4m (real PostgreSQL/Redis; includes the registry-split tests) |
| Backend coverage | **91%** |
| Ruff format / check | pass |
| mypy | pass — 80 source files (one new module after the registry split) |
| Alembic | pass — single head `0011`; no Phase 3 migration |
| Frontend Vitest | **70 passed** |
| ESLint / TypeScript | pass / pass |
| Repository frontend format check | pass — repository-pinned Prettier (`format:check`) |
| Production build | pass — Next.js 16.2.10 (Turbopack); `/audit-history` prerendered as static content |
| Playwright complete suite, run 1 | **7 passed** in 2.0m |
| Playwright complete suite, run 2 | **7 passed** in 1.6m (both runs from a clean state, no reused/orphan processes) |
| Deterministic eval (`det`) | pass — precision 1.00, recall 0.94, matches established baseline |
| Action-proposal eval (`actions`) | PASS — 0 grounding/injection/usefulness violations, matches baseline |
| Contract freshness | pass — regenerating `openapi.json`/`index.d.ts` reproduced byte-identical diffs (no drift), including after the registry-module split |
| Metrics | regenerated — see the committed `metrics.md` for the exact final numbers |
| pre-commit `--all-files` | **pass** — all 10 hooks passed (trailing-whitespace, end-of-file, yaml, large-files, merge-conflict, private-key, ruff, ruff-format, Detect secrets, `.env.example`) |
| detect-secrets | pass — no unstaged-baseline warning; `.secrets.baseline` byte-identical to HEAD (0-line diff) |
| gitleaks full history | pass — no leaks |
| `.env.example` validation | pass |
| `git diff --check` | pass |

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

Committed as five commits on `stage-9-audit-history`, all reachable from the
approved preparatory HEAD `eedd69d`: presentation registry, audit history API,
Audit History frontend, tests and Playwright, and this documentation. `fdb4636`
remains an ancestor. Nothing has been tagged, pushed, or merged.
`origin/stage-9-deletion-retention` remains the Phase 2 remote boundary; no
`origin/stage-9-audit-history` tracking ref and no Stage 9 tag exist.

## Stop point

Delivery Phase 3 is committed locally and fully verified. Do not push, tag,
merge, or begin Delivery Phase 4 without explicit approval.
