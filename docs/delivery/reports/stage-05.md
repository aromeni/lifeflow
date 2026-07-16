# Stage 5 Completion Report

**Date:** 2026-07-16 · **Approved:** pending

## Outcome

The MVP now produces its first genuinely useful outcome: an on-demand daily brief composed **deterministically** from validated persisted signals — five fixed sections (Needs attention, Today and upcoming, Waiting for, Suggested actions, Low-confidence review), stable ordering rules, and inspectable source evidence on every item. A signal whose evidence cannot be resolved is omitted and reported, never shown as an unsupported claim. Optional LLM prose is allow-list constrained (the model may only select exact application-authored sentences; one deviation rejects the whole output), so unsupported facts, deadlines, priorities, and actions are unrepresentable in a brief. Briefs are versioned and persisted with full generation metadata and honest complete/empty/degraded/partial states.

## Pre-stage gate checks (requested before Stage 5)

1. **Change-aware persistence** — re-running extraction with identical sources, versions, and scores now classifies signals as `unchanged` and writes nothing: the upsert compares all meaningful persisted fields before touching a row, `persisted_unchanged` is reported in the API response and audit event, and a PostgreSQL `xmin` check in the test proves no row was rewritten. Time-shifted re-runs update only signals whose scores/reason codes genuinely moved.
2. **Real LLM disabled by default** — a configured API key alone no longer enables anything: `LLM_EXTRACTION_ENABLED=false` is the default, the flag without a key refuses startup, and four tests pin the matrix. ADR 0002 requires a recorded real-provider evaluation before the flag is ever turned on outside evals.
3. **Dev-set honesty** — ADR 0002 now records that all golden v1 metrics are development-set results (regression floors, not generalisation claims) and commits to a blind holdout + adversarial evaluation set (dataset v2, frozen detectors, run once) before the Stage 10 pilot gate.

## Implemented

- **Migration 0004** — `briefs.version` + `briefs.status` with named unique constraint `uq_briefs_user_date_version`; up/down cycle verified. Regeneration creates a new version; prior versions are kept (A16).
- **`BriefRepository`** — owner-bound get/latest/list_recent/next_version/add; covered by the three-layer ownership suite.
- **`brief_composition.py`** — pure deterministic `compose_sections` (fixed section-assignment rules, stable multi-key ordering, evidence expansion from user-owned source items, omission + notice when evidence is unresolvable), `deterministic_summary`, allow-list prose sentences, `validate_optional_summary` (exact-match or full rejection), and `BriefService` orchestrating extract → compose → optional prose → persist → audit (`brief.generated`).
- **Prompt** — `prompts/brief_composition_v1.md`: the model chooses one to three exact sentences from a deterministic allow-list; source content is declared untrusted data.
- **API** — `POST /briefs/generate`, `GET /briefs/latest`, `GET /briefs` (version list), `GET /briefs/{id}`; persisted JSON re-validated through typed models before crossing the boundary; contracts regenerated.
- **UI** — Today dashboard now renders the brief: summary headline, honest status line (generated-at, version, status), notices for partial/degraded/empty states, five sections with priority badges, plain-language reason codes, confidence, advisory suggested steps ("nothing happens without your approval"), and a native-`<details>` evidence drawer per item (title, sender, time, source ref, excerpt). New `BriefSectionView` + `EvidenceDrawer` components.
- **Evals** — `evals/golden/v1/brief_cases.json` + `brief`/`brief+mock` runner modes scoring grounding, ordering, injection containment, low-confidence containment, determinism, usefulness proxies, and prose validation; non-zero exit on failure. Manual usefulness rubric recorded in the golden file and applied to the demo brief.
- **Playwright** — `apps/web/e2e/demo-brief.spec.ts`: demo start → onboarding → brief generation → evidence inspection → injection containment, plus a version-increment journey; `./scripts/e2e.sh` prepares db+migrations and runs it; CI job added.
- **CI** — new `contracts` job regenerates the OpenAPI types and fails if `packages/contracts` is stale; new `e2e` job runs the Playwright journeys against a live db/api/web stack.

## Tests and evidence

| Check | Result | Evidence |
|---|---|---|
| Backend tests | PASS | `uv run pytest` — **134 passed** (16 new: composition, generation/versioning/statuses, LLM gating, change-aware persistence) |
| Brief deterministic under mock/no provider | PASS | repeat-composition equality in `brief` eval mode + unit tests |
| Every actionable statement has evidence | PASS | grounding check: 0 violations (items without evidence cannot be constructed — `min_length=1` schema) |
| Brief-level golden eval | PASS | `brief`: 20 items, 0 grounding/ordering violations, 0 injection leaks, counts/top-item/low-confidence/summary all match ([brief.md](../../../evals/results/brief.md)) |
| Unsupported-claim rejection | PASS | `brief+mock`: 1 valid selection accepted, 1 fabricated sentence rejected wholesale ([brief-mock.md](../../../evals/results/brief-mock.md)) |
| Empty/degraded/partial states | PASS | status precedence tests + notices (`source_partial`, `evidence_missing`, `llm_degraded`, `brief_empty`) |
| Persisted versions + metadata | PASS | live check: versions [4,3,2,1] listed; each carries composer version, counts, extraction summary, prose state |
| Playwright E2E | PASS | 2 journeys, 23s: demo → onboarding → brief → evidence; regeneration increments version |
| Signal evals unchanged | PASS | det: precision 1.00 / recall 0.94; det+mock: recall 1.00 — refreshed |
| Accessibility | PASS | semantic sections/headings, native disclosure, aria-live status, no colour-only meaning, keyboard operable |
| Types / lint / format / build | PASS | mypy strict (42 files), ruff, ESLint, Prettier, `pnpm web:build`, all 9 pre-commit hooks |
| Migration up/down | PASS | 0003↔0004 both directions |
| Contracts current | PASS | regenerated; CI now enforces freshness |

## Manual verification

Live run: dev-login → demo/start (36 items) → `POST /briefs/generate` → status `complete`, 7/4/2/6/1 section counts, top item Dana's request with `em-010` evidence and an advisory step; `GET /briefs/latest` and version list verified; injection email (em-004) absent from every brief.

## Known limitations

- The usefulness rubric is applied by a human at each gate; only its proxies are automated.
- Scheduled briefs deliberately deferred (skill: on-demand first) — Stage 8.
- Brief golden counts are pinned to dataset v1 (dev set); the blind holdout arrives before Stage 10.
- Frontend coverage still unmeasured (reporter deferred); E2E journeys cover the critical path.
- `GET /briefs/{id}` exists but the UI only surfaces the latest brief; a version-history view is a later-stage concern.

## Recommended commit message

`feat(brief): deterministic daily brief with evidenced sections, versioned persistence, allow-list LLM prose, brief-level evals, and Playwright E2E`

## Gate

Stage 5 is complete. Stop here and wait for explicit approval to begin Stage 6.
