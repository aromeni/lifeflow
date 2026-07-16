"""Anthropic implementation of LLMProvider.

Uses the official SDK's structured-output helper (`messages.parse` with a
Pydantic schema). Timeouts and bounded retries are SDK-native; usage (token
counts) is logged per call for cost tracking — never prompt contents.
"""

import logging
from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from lifeflow_api.llm.prompt_loader import load_prompt
from lifeflow_api.llm.provider import LLMProviderError, OutputT

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-4-8"
REQUEST_TIMEOUT_SECONDS = 60.0
MAX_RETRIES = 2  # SDK retries connection errors, 408/409/429/5xx with backoff
MAX_OUTPUT_TOKENS = 8192


class AnthropicProvider:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        prompts_dir: str | None = None,
    ) -> None:
        self._client = AsyncAnthropic(
            api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=MAX_RETRIES
        )
        self._model = model
        self._prompts_dir = prompts_dir

    async def generate_structured(
        self,
        *,
        task: str,
        input_data: dict[str, Any],
        output_schema: type[OutputT],
        trace_context: dict[str, Any],
    ) -> OutputT:
        prompt = load_prompt(task, prompts_dir=self._prompts_dir)
        try:
            response = await self._client.messages.parse(
                model=self._model,
                max_tokens=MAX_OUTPUT_TOKENS,
                thinking={"type": "adaptive"},
                system=prompt.system,
                messages=[{"role": "user", "content": prompt.render_user(input_data)}],
                output_format=output_schema,
            )
        except anthropic.APIStatusError as exc:
            raise LLMProviderError(f"Anthropic API error ({exc.status_code}).") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMProviderError("Could not reach the Anthropic API.") from exc

        # Cost/usage capture (threat model T21): counts only, no content.
        logger.info(
            "llm.call task=%s model=%s input_tokens=%s output_tokens=%s stop_reason=%s",
            task,
            self._model,
            response.usage.input_tokens,
            response.usage.output_tokens,
            response.stop_reason,
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise LLMProviderError(f"No structured output returned (task '{task}').")
        return response.parsed_output
