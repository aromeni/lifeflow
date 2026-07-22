# evals

Golden datasets, scoring, and regression tests for extraction, briefs, and action proposals (skill §14).

- `golden/v1/cases.json` — golden truth for demo dataset v1 (20 cases: expected signals, deadlines, priority bands, prohibitions). **Development set**: consulted while building det-v1, so its metrics are regression floors, not generalisation claims. A blind holdout + adversarial set is planned before the Stage 10 pilot gate (ADR 0002).
- `golden/v1/brief_cases.json` — brief-level golden expectations (Stage 5): grounding, ordering, injection containment, low-confidence containment, usefulness proxies, plus the manual usefulness rubric applied at each gate.
- `golden/v1/action_cases.json` — action-proposal expectations (Stage 6): deterministic typed payloads, evidence grounding, stable origins, injection containment, approval binding and usefulness proxies.
- `fixtures/` — canned LLM outputs for the mock provider (plumbing metrics, never model-quality claims).
- `run_evals.py` — runner; invoke via `./scripts/run-evals.sh [det|det+mock|det+anthropic|brief|brief+mock|actions]`. Deterministic signal, brief and action modes exit non-zero below their ratified floors, so they gate CI.
- `results/` — generated reports, one per mode; committed as evidence.

Acceptance targets are ratified in docs/architecture/adr/0002-evaluation-targets.md.
