# evals

Golden datasets, scoring, and regression tests for extraction and briefs (skill §14).

- `golden/v1/cases.json` — golden truth for demo dataset v1 (20 cases: expected signals, deadlines, priority bands, prohibitions).
- `fixtures/` — canned LLM outputs for the mock provider (plumbing metrics, never model-quality claims).
- `run_evals.py` — runner; invoke via `./scripts/run-evals.sh [det|det+mock|det+anthropic]`.
- `results/` — generated reports, one per mode; committed as evidence.

Acceptance targets are ratified in docs/architecture/adr/0002-evaluation-targets.md.
