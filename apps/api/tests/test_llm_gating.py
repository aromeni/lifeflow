"""Real LLM augmentation must be disabled by default (ADR 0002).

A configured API key alone must never enable real provider calls; the
explicit LLM_EXTRACTION_ENABLED flag is required, and enabling it without
a key is a refused misconfiguration.
"""

import pytest

from lifeflow_api.config import Settings
from lifeflow_api.main import create_app


def _settings(**overrides: object) -> Settings:
    return Settings(environment="test", **overrides)  # type: ignore[arg-type]


def test_llm_disabled_by_default_even_with_key() -> None:
    app = create_app(_settings(anthropic_api_key="sk-test-not-real"))
    assert app.state.llm_provider is None


def test_llm_disabled_with_no_configuration() -> None:
    app = create_app(_settings())
    assert app.state.llm_provider is None


def test_llm_enabled_only_with_explicit_flag_and_key() -> None:
    app = create_app(_settings(llm_extraction_enabled=True, anthropic_api_key="sk-test-not-real"))
    assert app.state.llm_provider is not None


def test_flag_without_key_refuses_to_start() -> None:
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        create_app(_settings(llm_extraction_enabled=True))
