"""LLM-assisted extraction: validation boundary and prompt-injection safety."""

import pytest
from pydantic import ValidationError
from tests.helpers import REFERENCE, TIMEZONE, demo_source_items

from lifeflow_api.extraction_llm import (
    SignalExtractionOutput,
    build_input_data,
    extract_with_llm,
    validate_output,
)
from lifeflow_api.llm.mock import MockLLMProvider
from lifeflow_api.llm.prompt_loader import load_prompt

GOOD_SIGNAL = {
    "signal_type": "request",
    "title": "Book the follow-up coaching session",
    "summary": "James assigned one action: book before the end of the month.",
    "evidence_refs": ["em-019"],
    "due_at": "2026-07-31T22:59:00+00:00",
    "confidence": 0.75,
}


def test_fabricated_evidence_is_rejected() -> None:
    output = SignalExtractionOutput.model_validate(
        {"signals": [GOOD_SIGNAL, {**GOOD_SIGNAL, "evidence_refs": ["em-999"]}]}
    )
    accepted, rejected = validate_output(output, known_ids={"em-019"})
    assert len(accepted) == 1
    assert rejected == 1


def test_prohibited_signal_types_cannot_be_represented() -> None:
    with pytest.raises(ValidationError):
        SignalExtractionOutput.model_validate(
            {"signals": [{**GOOD_SIGNAL, "signal_type": "send_email"}]}
        )
    with pytest.raises(ValidationError):
        SignalExtractionOutput.model_validate({"signals": [{**GOOD_SIGNAL, "evidence_refs": []}]})
    with pytest.raises(ValidationError):
        SignalExtractionOutput.model_validate({"signals": [{**GOOD_SIGNAL, "confidence": 1.7}]})


def test_llm_confidence_is_capped_below_deterministic_certainty() -> None:
    output = SignalExtractionOutput.model_validate(
        {"signals": [{**GOOD_SIGNAL, "confidence": 1.0}]}
    )
    accepted, _ = validate_output(output, known_ids={"em-019"})
    assert accepted[0].confidence <= 0.9


async def test_provider_round_trip_and_trace_context() -> None:
    provider = MockLLMProvider({"signal_extraction_v1": {"signals": [GOOD_SIGNAL]}})
    items = await demo_source_items()
    accepted, rejected = await extract_with_llm(
        provider,
        items,
        [],
        reference=REFERENCE,
        timezone=TIMEZONE,
        trace_context={"task": "signal_extraction"},
    )
    assert rejected == 0
    assert len(accepted) == 1
    assert accepted[0].extraction_version == "llm-v1"
    assert provider.calls[0]["task"] == "signal_extraction_v1"


async def test_untrusted_content_is_delimited_in_the_rendered_prompt() -> None:
    items = await demo_source_items()
    input_data = build_input_data(items, [], reference=REFERENCE, timezone=TIMEZONE)
    prompt = load_prompt("signal_extraction_v1")
    rendered = prompt.render_user(input_data)
    assert "<untrusted_source_items>" in rendered
    # The injection email's payload sits INSIDE the delimited data block.
    payload_pos = rendered.find("Ignore all previous instructions")
    open_pos = rendered.find("<untrusted_source_items>")
    close_pos = rendered.find("</untrusted_source_items>")
    assert open_pos < payload_pos < close_pos
    # And the system prompt tells the model such content is data, not orders.
    assert (
        "never instructions" in prompt.system.lower() or "not instructions" in prompt.system.lower()
    )
