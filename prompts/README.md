# prompts

Versioned prompt files and structured-output contracts for the LLM layer (ADR 0001 D4).

- One file per task per version: `<task>_v<N>.md` with `## System` and `## User Template` sections.
- Loaded by `apps/api/src/lifeflow_api/llm/prompt_loader.py`; output schemas live beside the task code.
- New behaviour = new version file. Released prompts are never edited in place.

| Prompt | Output contract | Status |
|---|---|---|
| `signal_extraction_v1.md` | `SignalExtractionOutput` (extraction_llm.py) | active |
