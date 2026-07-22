# Stage 6 Completion Report

**Independent review:** APPROVE WITH MINOR CHANGES (2026-07-16) · **Remediation:** applied the same day across three rounds — see "Post-review remediation", "Focused re-review remediation", and "Second focused re-review remediation" below.

## Outcome

LifeFlow now converts validated persisted signals into grounded, typed proposals for an internal task, Gmail draft, and calendar event, then lets a user inspect the evidence and every executor input, edit, approve, reject, simulate, and trace each proposal without any hidden side effect. Proposal generation is deterministic, change-aware, and origin-idempotent; approval is an immutable binding over the closed action type, canonical complete payload, and proposal version; editing invalidates approval atomically; expiry and policy checks run under a row lock immediately before approval and first execution; and duplicate execution returns the original simulated result without invoking an executor again.

## Implemented

- **Green-baseline restoration:** fixed brief regeneration so a synchronous in-flight guard permits exactly one request and one `N → N+1` version increment per click; the button is disabled until completion. Corrected the Next.js workspace root, separated development/build caches, removed network-dependent Google font fetching in favour of system fonts, and updated stale Stage 5 approval documentation.
- **Migration `0005_action_proposal_integrity.py`:** added proposal origin/brief linkage, canonical payload hash, version, approval snapshot/binding, edit/rejection timestamps, created/updated timestamps, closed action/risk/status checks, stable per-user origin uniqueness, complete execution snapshots, and one-execution-per-proposal uniqueness. The migration includes defensive legacy backfill and a complete downgrade.
- **Typed payload boundary (`action_payloads.py`):** strict, extra-forbidden schemas for task creation, Gmail draft creation, and calendar event creation. Every executor field is required, including explicit nullable fields; canonical JSON, payload hashes, and action/type/version approval bindings are application-owned. Only ISO datetime parsing is allowed at the HTTP boundary; numeric coercion is rejected.
- **Deterministic composition (`proposal_composition.py`):** creates at most one evidence-resolvable proposal of each closed type, in deterministic order, from persisted signals. Stable `action-origin-v1` fingerprints use action type + signal dedupe identity and are independent of composer versions. Prompt-injection fixture `em-004` cannot become a proposal.
- **Lifecycle and policy (`action_proposal_service.py`, `action_policy.py`):** owner-bound row locking; proposed → edited/approved/rejected/expired/executing/executed/failed transitions; protected edited/approved/rejected/expired/executed/failed rows; atomic approval invalidation; deterministic ownership, status, expiry, risk, synthetic-scope, payload-hash, due-time, event-time, approval-version, and binding validation. Internal tasks also require approval.
- **Simulated execution (`action_executors.py`):** task, Gmail-draft, and calendar-event simulators only. Stable simulated IDs and execution snapshots contain the exact approved payload. Success and final failure are each persisted once; replay returns that original record; no automatic or hidden retry exists.
- **Audit and ownership (`audit.py`, `repositories.py`):** append-time ordered UTC events for creation, update, edit, approval, invalidation, rejection, expiry, denied/started/replayed/succeeded/failed execution, and terminal state changes. Timeline reads and every proposal/execution query are user-scoped; audit metadata contains hashes/reason codes, never payload bodies or secrets.
- **API (`action_proposals.py`):** `GET /action-proposals`, `GET /action-proposals/{id}`, `PATCH /action-proposals/{id}`, and `POST` approve/reject/execute routes. Responses expose source evidence, exact typed payload/hash/version, approval binding, execution snapshot/result, safe audit timeline, expiry, and the `simulation_only` marker. OpenAPI and TypeScript contracts were regenerated.
- **Approval inbox UI:** `/approvals` shows evidence drawers, rationale/risk/confidence/expiry, every executor field, canonical JSON/hash/version, approval binding, JSON editing with approval-invalidation warning, approve/reject/simulate controls, terminal states, results, and an audit timeline. Today links directly to the inbox.
- **Evaluation and CI:** added `action_cases.json`, the `actions` evaluation mode, and a committed PASS report covering expected actions/evidence, determinism, typed payloads, origin stability, grounding, expiry, injection containment, usefulness, and version-sensitive approval bindings. CI now gates both signal modes, both brief modes, and the action suite; generated frontend contracts remain a dedicated freshness gate.
- **Playwright:** added an isolated full approval journey covering exact evidence/payload preview, approved edit invalidation, stale version rejection, displayed-payload binding, idempotent simulated execution, terminal rejection, injection containment, and no proposal duplication or protected-state overwrite after brief regeneration. Existing demo/brief and exact one-click regeneration journeys remain green.

## Architecture decisions

- No new architecture ADR was required. Stage 6 implements the already accepted deterministic safety pipeline in ADR 0001 D5; that ADR now records the concrete immutable approval snapshot, complete-payload preview, stable-origin, and one-execution semantics.
- Assumptions A19–A20 record the immutable origin namespace and the final-failure/no-automatic-retry rule. Any future retry must be designed as a new explicit user action with fresh policy review.
- The threat model is reviewed as v2 for Stage 6, with implemented verification notes for prompt injection (T3/T4), replay/idempotency (T12), approval mutation (T13), atomic expiry/ownership, and the absence of real external executors.
- ADR 0002 remains unchanged in principle: all current signal, brief, and action metrics are development-set regression results. A separate blind holdout/adversarial dataset is still required before the Stage 10 pilot gate, and real LLM augmentation remains disabled by default pending its real-provider evaluation.

## Tests and evidence

| Check | Result | Evidence |
|---|---|---|
| Unit tests | PASS | `uv run pytest -m "not integration"` — **101 passed**, 91 deselected |
| Integration tests | PASS | `uv run pytest -m integration` — **91 passed**, 101 deselected; full suite **192 passed** (current verified total, after both remediation rounds; see "Second focused re-review remediation" below) |
| Frontend tests | PASS | `pnpm web:test` — **19 passed** across 7 files |
| Coverage | PASS | `python3 scripts/metrics.py` — backend **93%** |
| Type checking | PASS | `uv run mypy` — 48 source files; `pnpm web:typecheck` |
| Lint | PASS | `uv run ruff check .`; `pnpm web:lint`; `git diff --check` |
| Format | PASS | `uv run ruff format --check .` — 81 files; `pnpm web:format:check` |
| Build | PASS | `NEXT_TELEMETRY_DISABLED=1 pnpm web:build` — Next.js 16 production build, 9 pages, no font fetch or workspace-root warning |
| Migration | PASS | `alembic 0005 → 0004 → 0005`; `uv run alembic check` — no schema drift |
| Contracts | PASS | fresh `generate-contracts.sh` output byte-identical for `openapi.json` and `index.d.ts`; CI freshness job retained |
| Signal evals | PASS | `det`: precision 1.00, recall 0.94, 0 unsafe; `det+mock`: recall 1.00, one fabricated-evidence signal rejected |
| Brief evals | PASS | `brief` and `brief+mock`: 0 grounding/ordering/injection violations; valid prose accepted and fabricated prose rejected |
| Action eval | PASS | `actions`: 3 proposals; exact expected evidence/types; deterministic; 0 grounding/schema/origin/expiry/injection/usefulness violations |
| Playwright | PASS | **3 passed**: demo → onboarding → brief → evidence; exact one-request/one-version regeneration; complete approval lifecycle and regeneration idempotency |
| Security checks | PASS | all 9 pre-commit hooks; detect-secrets; gitleaks full history (8 commits), 0 leaks |
| Stage 7 scope exclusion | PASS | no Google/OAuth/Gmail/Calendar API client imports or calls in proposal, policy, executor, API, or approval UI paths |

## Manual verification

- Exercised a fresh isolated demo session through onboarding, version-1 brief generation, and an approval inbox containing exactly three unique proposal origins.
- Inspected the Gmail-draft proposal’s exact source reference and all four executor fields (`to`, `subject`, `body`, `thread_id`); injection text and `em-004` were absent.
- Approved a task, edited its displayed payload, observed version `1 → 2`, approval removal and `approval.invalidated`, rejected a stale-version request, then freshly approved the displayed version.
- Ran the task simulator, replayed the execution endpoint, and confirmed the same execution ID, result, and exact approved payload were returned. Rejected a calendar proposal and confirmed later approval was terminally denied.
- Regenerated the brief and confirmed exactly three proposals remained with identical IDs/origins; the edited/executed task payload and rejected calendar state were preserved.

## Post-review remediation (2026-07-16)

The independent Stage 6 review returned APPROVE WITH MINOR CHANGES. All required items were remediated on this branch:

- **Resilient composition (review H1):** malformed or incomplete source metadata (missing/garbage/non-string calendar `ends_at`, invalid attendee addresses, and equivalent failures in task and Gmail-draft candidates) now skips that candidate only. Brief generation always completes, remaining valid proposals are still created, the brief carries an honest `proposal_candidates_skipped` notice and `partial` status, and a `proposal.candidates_skipped` audit event records only the closed action type and a fixed reason code — never source content. The Stage 4 conflict detector's `ends_at` parsing was hardened the same way (`_event_end`). Proven by four parametrised integration tests plus an HTTP-level test asserting a 200, not a 500.
- **Concurrent first-time generation (review M1):** the origin insert now runs inside a savepoint; on a uniqueness conflict the loser re-reads the winning row under lock and continues down the change-aware path. The database constraint remains authoritative. Proven by a real two-connection PostgreSQL race test.
- **Policy tamper defences now test-backed (review M2):** ten integration tests corrupt persisted approval state directly — incomplete snapshot, action-type/version/payload-hash/payload-json/binding-hash mismatches, approval predating an edit, missing demo scope, disconnected account — plus a direct ownership-mismatch check on the policy engine. Each asserts the stable error code, the `approval.denied`/`execution.denied` audit event with safe metadata only, and zero executor invocations. `action_policy.py` coverage rose from 75% to 89%.
- **Change-aware update path exercised (review M3):** changing an underlying source materially updates the pristine proposal in place — same id and origin, version incremented, payload hash changed, `proposal.updated` audited — and `failed` was added to the protected-status regeneration test matrix.
- **Audit privacy regression test:** after a full lifecycle (approve, execute, replay, edit, re-approve, reject-with-reason) no audit metadata contains payload keys (`to`, `subject`, `body`, `attendees`, `title`, `notes`, `description`, …) or payload/rejection values, at any nesting depth.
- **Additional robustness tests:** two concurrent executions produce exactly one executor invocation and one replayed record; a simultaneous approve/edit race resolves to a controlled success-or-conflict outcome with a consistent final row; migration 0005 is now cycled with populated legacy records against a dedicated scratch database (backfill verified, downgrade retains rows, second upgrade re-backfills).
- **Deferred technical debt recorded** (assumptions-and-decisions.md, Stage 6 table): GET-route expiry reconciliation (Stage 8 scheduler), durable audit for unexpected executor exceptions (Stage 7 prerequisite), offset-representation binding semantics (documented in `action_payloads.py`), deterministic expiry-sweep ordering (Stage 8), optional client-side hash recomputation (Stage 9 candidate).

Post-remediation gate results: backend **180 passed** (22 new), coverage **93%**; mypy strict and ruff clean; web 19 tests/lint/types/format/build clean; all five eval modes PASS; Playwright 3/3; contracts fresh; all 9 pre-commit hooks, detect-secrets, and gitleaks clean; metrics regenerated.

## Focused re-review remediation (2026-07-16)

The focused Codex re-review returned BLOCK: malformed calendar metadata could still abort brief generation inside the deterministic detectors (a timezone-naive `ends_at` reaching an aware-datetime comparison; `len()`/indexing on unvalidated `attendees` and `recipients`). Fixed on this branch:

- **Timezone-naive `ends_at` (`detectors.py`, `proposal_composition.py`):** a shared `parse_aware_datetime` helper returns a timezone-aware datetime or `None` — non-strings, malformed strings, and naive values are all invalid source metadata, and a timezone is never guessed. Conflict detection skips the affected event; composition skips the calendar candidate with the existing safe notice/audit path (`partial` status, `invalid_source_data` reason code only).
- **Invalid `attendees` (`detectors.py`, `proposal_composition.py`):** meeting detection resolves attendees only when the metadata is actually a list (originally `_attendee_count`, since superseded — see below); strings, objects, numbers, and null cannot establish an attendee count, so the detector conservatively emits no meeting signal instead of raising. Composition validates that attendees are a list of strings before iterating; element-level garbage (invalid addresses, mixed types) skips the candidate safely. Raw attendee values never appear in logs, notices, or audit metadata.
- **Defensive detector boundary (`detectors.py`):** `recipients` access in commitment and follow-up detection now goes through `_first_recipient` (list-of-strings check, safe fallback), removing the last metadata access that could raise on one malformed `SourceItem`. Every deterministic detector now treats connector metadata as untrusted; a bad item degrades only its own detection.

New regression tests (8): naive-`ends_at` and mixed-attendee-element corruptions added to the malformed-metadata matrix (partial status, one safe skip, corrupted values absent from audit metadata); four whole-value attendee corruptions (string/object/number/null) proving suppressed meeting detection with intact task/draft proposals (brief status at this point is corrected below — see "Second focused re-review remediation"); the HTTP-boundary test parametrised over missing and naive `ends_at` (200, `partial`, no 500); and a detector-level test corrupting three items at once (naive event end, numeric attendees, object recipients) proving extraction of all remaining signals survives with the conflict calculation skipped, not guessed.

Focused-remediation gate results: backend **188 passed** (8 new), coverage unchanged at **93%**; mypy strict and ruff clean; web 19 tests/lint/types/format/build clean; all five eval result files **byte-identical** (checksum-verified) — well-formed dataset-v1 behaviour unchanged; Playwright 3/3; migrations and contracts fresh; all 9 pre-commit hooks, detect-secrets, and gitleaks (full history) clean.

## Second focused re-review remediation (2026-07-16)

The second focused Codex re-review returned BLOCK on one remaining issue: whole-value malformed attendee metadata (string, object, number, null) was silently treated as an attendee count of zero. That correctly prevented a crash, but the resulting brief was marked `complete` even though an authorised source item's metadata could not be processed — misleading, and inconsistent with the project's rule that partial failures stay visible. (The line above describing that case as producing a `complete` brief documents the now-superseded behaviour; the corrected behaviour is below.)

Fixed on this branch, via a typed diagnostic path rather than exceptions or mutable global state:

- **`DetectionDiagnostic` / `DetectionResult` (`detectors.py`):** `detect_meetings` and `run_deterministic_detectors` now return a typed `DetectionResult` (`signals`, `diagnostics`) instead of a bare list. `_attendee_count` was replaced by `_attendee_metadata`, which distinguishes a genuinely absent `attendees` key (count 0, no diagnostic — nothing was malformed) from a key present with a non-list value (count 0 **and** a `DetectionDiagnostic(code="invalid_attendees_metadata", severity="warning", source_item_id=<external id>)`). The value itself is never guessed, coerced, or included in the diagnostic — only the closed code and the source item's own internal reference.
- **`ExtractionSummary.diagnostic_counts` (`extraction.py`):** diagnostics are aggregated into a `{code: count}` dict (via `collections.Counter`) and recorded on the `extraction.completed` audit event — fixed codes and counts only, consistent with the existing redaction discipline for skipped proposal candidates.
- **`BriefService.generate` (`brief_composition.py`):** a non-empty `diagnostic_counts` now makes `partial` true alongside the existing `inactive_accounts`/`omitted_signals` triggers, so the brief is no longer reported `complete` when detection could not process an item's metadata. A generic user-facing notice (`signal_data_quality`, "Some calendar information could not be processed.") is added, and the `brief.generated` audit event gained a `detection_diagnostics` field with the same safe counts.

New/updated regression tests (2 new, 1 rewritten): `test_malformed_metadata_never_aborts_detection` in `test_detectors.py` now also asserts the exact safe diagnostic (code, severity, source item id, and that no other diagnostic is produced) for the whole-value numeric-attendees case. `test_unusable_attendee_metadata_suppresses_meeting_detection` in `test_action_proposals.py` was rewritten: it now asserts `partial` status (not `complete`), the `signal_data_quality` notice and message, the safe `diagnostic_counts`/`detection_diagnostics` audit fields, and that none of the corrupted values or the source item id leak into brief metadata, notices, or audit records — parametrised over string/object/number/null attendees. A new HTTP-boundary test, `test_brief_generation_survives_whole_value_malformed_attendees_api`, proves the same four cases return 200 with `partial` status and the generic notice, with task/draft proposals still created.

Second-focused-remediation gate results: backend **192 passed** (4 net new: 2 new tests, 1 rewritten in place, plus the pre-existing suite), coverage unchanged at **93%**; mypy strict and ruff clean (81 files formatted); web 19 tests/lint/types/format/build clean; all five eval result files **byte-identical** (checksum-verified against the prior round) — well-formed dataset-v1 behaviour unchanged; Playwright 3/3; `alembic check` no drift; contracts regenerated and idempotent (a second run produces byte-identical output); all 9 pre-commit hooks, detect-secrets, gitleaks (full history, 8 commits, 0 leaks), and `git diff --check` clean.

## Known limitations

- Stage 6 deliberately performs no real task, Gmail, Calendar, OAuth, or Google API operation. Real Google integration belongs only to Stage 7 after explicit approval.
- Final execution failures have no retry control in Stage 6. This is intentional: a later retry requires a separately designed explicit user action, not an automatic retry.
- Proposal generation currently selects at most one candidate of each action type per brief. Expanding candidate volume should be driven by usefulness evidence, not arbitrary limits.
- Action and brief golden suites use development dataset v1. Their PASS results are regression floors, not claims of real-world generalisation; the blind holdout/adversarial set remains due before the Stage 10 pilot gate.
- Frontend line coverage is not yet measured; the critical approval boundary is covered by component tests and a real browser/API/PostgreSQL journey.

## Files changed

- **Backend domain and persistence:** proposal/execution models, repositories, migration 0005, payload schemas, deterministic composer, policy engine, lifecycle service, simulated executors, audit ordering, brief integration.
- **API and contracts:** owner-scoped proposal routes, FastAPI registration, regenerated OpenAPI and TypeScript definitions.
- **Frontend:** approval inbox page, proposal/payload/audit components and tests, evidence component generalisation, Today link, brief regeneration guard, offline build/root/font configuration.
- **Evaluation and CI:** action golden set/runner/result, enforced signal/brief/action CI job, retained contract and E2E gates, expanded Playwright journeys.
- **Documentation:** ADR implementation note, Stage 6 assumptions, threat-model review, stage status, Stage 5 approval wording, metrics dashboard, this report.

## Run instructions

```bash
docker compose up -d db --wait
cd apps/api
uv sync --locked
uv run alembic upgrade head
uv run pytest
cd ../..
pnpm install --frozen-lockfile
./scripts/run-evals.sh actions
./scripts/e2e.sh
./scripts/demo.sh
```

Open `http://localhost:3000`, choose **Try demo**, finish onboarding, generate a brief, then choose **Review approvals**.

## Recommended commit message

`feat(actions): add grounded approval-bound proposals and simulated execution`

## Gate

Stage 6 is complete. Stop here and wait for explicit approval to begin Stage 7.
