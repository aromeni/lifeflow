"""The LLMProvider contract (skill §6.3)."""

from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

OutputT = TypeVar("OutputT", bound=BaseModel)


class LLMProviderError(Exception):
    """The provider failed (timeout, API error, unparseable output after
    retries). Never contains prompt or personal data — callers degrade
    gracefully when they catch it."""


@runtime_checkable
class LLMProvider(Protocol):
    async def generate_structured(
        self,
        *,
        task: str,
        input_data: dict[str, Any],
        output_schema: type[OutputT],
        trace_context: dict[str, Any],
    ) -> OutputT: ...
