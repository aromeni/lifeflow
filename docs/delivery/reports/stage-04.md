# Stage 4 Completion Report

**Date:** 2026-07-16 · **Approved:** 2026-07-16

## Outcome

The system now turns normalised source data into defensible, prioritised signals — deterministic-first, exactly as mandated. Six transparent detectors (requests, commitments, deadlines, meetings, follow-ups, conflicts) form a measured baseline (precision 1.00, recall 0.94 on golden v1); an explainable hybrid priority engine ranks every signal with reason codes and evidence; and a provider-neutral LLM layer augments — never replaces — the rules, behind strict validation that rejects fabricated evidence, absorbs duplicates, caps confidence, and degrades visibly to the baseline on provider failure. The demo dataset is now versioned (v1 + scenario manifest) and a 20-case golden evaluation suite gates future changes.

## Implemented

- **Dataset versioning** (pre-stage request): `demo/data/v1/` + `manifest.json` scenario map; connectors take a `dataset_version`.
- **Deterministic baseline (det-v1)**: `deadline_phrases.py` (bounded UK-English due-phrase parser, end-of-day semantics, DST-safe) and `detectors.py` (cue-based requests with strong/weak confidence, sent-mail commitments, deadline detection incl. all-day "due" events, upcoming meetings, interval-overlap conflicts, 5-day stale follow-ups via thread arithmetic, bulk/newsletter suppression).
- **Priority engine** (`priority.py`): the skill §8 formula (0.30 urgency + 0.25 importance + 0.20 request strength + 0.15 deadline proximity + 0.10 relationship), all components in [0,1], reason codes (`explicit_request`, `due_within_24h`, `calendar_conflict`, `no_reply_6d`, `frequent_contact`, …), high/medium/low bands.
- **LLM layer** (`llm/`): `LLMProvider` protocol; `MockLLMProvider`/`FailingLLMProvider`; `AnthropicProvider` (AsyncAnthropic, `messages.parse` structured output, adaptive thinking, SDK timeouts/retries, token-usage logging, refusal handling); versioned prompt `prompts/signal_extraction_v1.md` with delimited-untrusted-data injection boundary; `extraction_llm.py` closed-enum output schema + strict validation (evidence must exist, confidence capped at 0.9).
- **Pipeline** (`extraction.py`): detectors → optional LLM add-only pass → dedupe (sha256 type+evidence, deterministic wins) → scoring → idempotent upsert (migration `0003`: priority columns + unique dedupe key, named constraint, verified up/down) → `extraction.completed` audit with llm_used/llm_failed visibility.
- **API**: `POST /signals/extract`, `GET /signals` (ranked, band filter); contracts regenerated.
- **Evals**: `evals/golden/v1/cases.json` (20 cases incl. prohibitions), fixture with deliberate fabrication+duplicate, `run_evals.py` + `scripts/run-evals.sh`, committed results, **ADR 0002** ratifying targets and the LLM gate.

## Tests and evidence

| Check | Result | Evidence |
|---|---|---|
| Backend tests | PASS | `uv run pytest` — **118 passed** (43 new: deadline parser 14, detectors 11, priority 6, LLM validation 6, pipeline/API 8) |
| Golden dataset runs | PASS | `./scripts/run-evals.sh det` and `det+mock` |
| Deterministic baseline metrics | REPORTED | precision **1.00**, recall **0.94**, deadlines 6/6, bands 6/6, duplicates 0, unsafe 0 ([det.md](../../../evals/results/det.md)) |
| LLM-assisted metrics (separate) | REPORTED | fixture-mock: recall **1.00** (+0.06), precision 1.00 held, 1 fabricated signal rejected, 1 duplicate absorbed, 0 unsafe ([det-mock.md](../../../evals/results/det-mock.md)) |
| Unsupported signals rejected / low-confidence | PASS | fabricated-evidence rejection test + em-005 confidence < 0.5 |
| Injection cannot select tools or bypass policy | PASS | closed `Literal` schema (prohibited types unrepresentable), delimiter placement test, zero unsafe outputs in both eval modes |
| No model call for demo-mode tests | PASS | full suite + demo flow run with no key and no provider |
| Degraded mode | PASS | provider outage → baseline persists, `llm_failed` visible in audit |
| Migration up/down | PASS | 0001→0003 full cycle |
| Types / lint / format / web / build | PASS | mypy strict (40 files), ruff, ESLint, Prettier, `pnpm web:build`, all 9 hooks, secrets baseline 0 |

## Baseline vs LLM-assisted (required comparison)

Incremental improvement (fixture plumbing): +1 recovered signal (em-019 implicit request) → recall 0.94→1.00 at unchanged precision. New failure modes introduced by the LLM and their guards: fabricated evidence (rejected by validation, counted), duplicate re-statements (absorbed by dedupe), over-confidence (capped at 0.9, calibration checked). **Real-model metrics were not run — no `ANTHROPIC_API_KEY` is available in this environment**; the `det+anthropic` mode is implemented and must be run and recorded in ADR 0002 before the Stage 10 pilot gate.

## Known limitations

Real-Anthropic eval pending a key; detector cues are English-only (A9); no UI for signals yet (Stage 5 brief consumes them); a dev-database constraint was renamed in place during migration repair (dev-only, documented in the session log).

## Recommended commit message

`feat(signals): deterministic detectors, explainable priority engine, provider-neutral LLM augmentation, golden eval suite`

## Gate

Stage 4 is complete. Stop here and wait for explicit approval to begin Stage 5.
