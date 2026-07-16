"""Mock provider — the default for demo mode, tests, and CI.

Returns canned payloads per task, validated through the same output schema as
a real provider, so the entire pipeline (validation included) is exercised
without any model call.
"""

from typing import Any

from pydantic import BaseModel

from lifeflow_api.llm.provider import LLMProviderError, OutputT


class MockLLMProvider:
    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self._responses = responses or {}
        self.calls: list[dict[str, Any]] = []  # inspected by tests

    async def generate_structured(
        self,
        *,
        task: str,
        input_data: dict[str, Any],
        output_schema: type[OutputT],
        trace_context: dict[str, Any],
    ) -> OutputT:
        self.calls.append({"task": task, "trace_context": trace_context})
        if task not in self._responses:
            raise LLMProviderError(f"MockLLMProvider has no canned response for task '{task}'.")
        return output_schema.model_validate(self._responses[task])


class FailingLLMProvider:
    """Simulates provider outage — every call fails. For degraded-mode tests."""

    async def generate_structured(
        self,
        *,
        task: str,
        input_data: dict[str, Any],
        output_schema: type[BaseModel],
        trace_context: dict[str, Any],
    ) -> BaseModel:
        raise LLMProviderError("Simulated provider outage.")
