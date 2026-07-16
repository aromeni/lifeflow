# ADR 0002 — Evaluation Acceptance Targets and LLM Gate

**Status:** Accepted · **Date:** 2026-07-16 · **Stage:** 4

## Context

The skill (§14) requires acceptance targets to be defined *after* establishing
the deterministic baseline, and the stage-gate instruction requires the LLM to
augment — never replace — the deterministic pipeline, with measured evidence.
The det-v1 baseline now exists and was measured against golden v1
(20 cases over demo dataset v1; see [../../../evals/results/det.md](../../../evals/results/det.md)).

## Measured baseline (det-v1, golden v1)

| Metric | Baseline | LLM-assisted (fixture mock) |
|---|---|---|
| Actionable precision | 1.00 | 1.00 |
| Actionable recall | 0.94 (misses em-019's implicit request) | 1.00 |
| Deadline extraction accuracy | 6/6 | 7/7 |
| Duplicate rate | 0 | 1 duplicate emitted, absorbed by dedupe |
| Priority-band agreement | 6/6 | 6/6 |
| Unsafe outputs (injection fixture) | 0 | 0 |
| Unsupported claims | 0 | 1 fabricated-evidence signal, rejected by validation |

The mock numbers measure the *pipeline* (validation, dedupe, capping), not
model quality — the fixture deliberately includes a fabrication and a
duplicate to prove the guards. Real-model metrics require an Anthropic key
(`./scripts/run-evals.sh det+anthropic`) and must be recorded here before the
Stage 10 pilot gate.

## Decision — ratified targets

Safety targets (absolute, enforced by tests at every stage gate):

- 0 prohibited actions ever representable or executed (S1)
- 0 unsafe outputs on prompt-injection fixtures (S5)
- 100% source attribution for actionable signals (S4)
- 0 unsupported claims surviving validation (evidence must exist)
- 0 duplicate signals persisted (dedupe by type + evidence)

Quality targets (regression floor for golden v1; CI-checkable):

- Actionable precision ≥ 0.85 — baseline holds 1.00; regression below 0.95 on
  golden v1 requires investigation before merge
- Recall on explicit requests and deadlines ≥ 0.80 — baseline holds 0.94
- Deadline extraction accuracy ≥ 0.90 on golden due-dates
- Priority-band agreement ≥ 0.80 on banded cases
- Ambiguous items (e.g. em-005) must surface with confidence < 0.5 or not at all

## LLM gate (deterministic-first policy)

1. Detectors always run and their output always persists; the LLM pass may
   only add signals (dedupe prefers deterministic on collision).
2. LLM confidence is capped at 0.9 — model output never outranks a rule.
3. Signals citing unknown evidence are rejected, counted, and logged.
4. A provider failure degrades to the baseline and is visible in the audit
   trail (`extraction.completed` metadata) — never a silent fallback.
5. The real-model pass ships only if, on golden v1, it improves recall without
   dropping precision below target and introduces zero unsafe outputs —
   measured by the same runner, reported side by side with the baseline.

## Development-set status and holdout plan (added at Stage 5 gate)

The 20-case golden v1 metrics above are **development-set results**: the same
cases were consulted while the det-v1 detectors were written and tuned, so
they measure regression safety, not generalisation. They must not be quoted
as expected real-world performance.

Before the Stage 10 pilot gate, a **separate holdout evaluation set** will be
created and run once, blind:

- authored against a *new* synthetic dataset version (v2 scenarios written
  without consulting detector code or existing cases);
- including a dedicated **adversarial slice** (fresh prompt-injection
  variants, evasive phrasing, boundary dates/DST edges, near-duplicate
  threads) at least as hard as the dev set;
- never used for tuning — detectors and prompts are frozen before the run,
  and results are recorded here verbatim, pass or fail;
- run in both `det` and real-provider modes so the LLM increment is measured
  on unseen data.

Until that run, all quoted metrics carry the "dev-set" qualifier.

## Consequences

- The eval suite is a merge gate for extraction changes from Stage 4 onward.
- New failure modes introduced by the LLM (fabricated evidence, duplicates,
  over-confidence) have named counters in the runner, so regressions are
  visible rather than averaged away.
- Golden v1 will grow (new scenarios → new dataset/golden versions);
  targets are re-ratified when the dataset version changes.
