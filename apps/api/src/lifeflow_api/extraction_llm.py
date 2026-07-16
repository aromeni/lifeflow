"""LLM-assisted signal extraction (llm-v1) — augments, never replaces, det-v1.

The model receives compact, delimited, untrusted item summaries and returns a
typed SignalExtractionOutput. Validation is deterministic and strict:
- evidence_refs must reference known item ids (unsupported claims rejected);
- signal types outside the closed enum are rejected by the schema itself;
- confidence/urgency are clamped; oversized text is truncated;
- the model cannot select tools or actions — its output is data, and every
  signal still flows through the same scoring, policy, and approval pipeline.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from lifeflow_api.detectors import DetectedSignal
from lifeflow_api.llm.provider import LLMProvider, LLMProviderError
from lifeflow_api.models import SignalType, SourceItem

logger = logging.getLogger(__name__)

LLM_EXTRACTION_VERSION = "llm-v1"
PROMPT_TASK = "signal_extraction_v1"
MAX_TITLE_CHARS = 200
MAX_SUMMARY_CHARS = 500


class ExtractedSignal(BaseModel):
    signal_type: Literal["request", "commitment", "deadline", "follow_up", "meeting", "conflict"]
    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)
    evidence_refs: list[str] = Field(min_length=1, max_length=5)
    due_at: datetime | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class SignalExtractionOutput(BaseModel):
    signals: list[ExtractedSignal] = Field(max_length=50)


def _item_summary(item: SourceItem) -> dict[str, object]:
    body = str(item.metadata_json.get("body_preview", item.metadata_json.get("description", "")))
    return {
        "id": item.external_id,
        "type": item.source_type,
        "folder": item.metadata_json.get("folder"),
        "from": item.sender_or_organiser,
        "title": item.title,
        "occurred_at": item.occurred_at.isoformat(),
        "body": body,
    }


def build_input_data(
    items: list[SourceItem],
    already_detected: list[DetectedSignal],
    *,
    reference: datetime,
    timezone: str,
) -> dict[str, str]:
    detected_lines = [
        f"{signal.signal_type}: {sorted(signal.evidence_refs)}" for signal in already_detected
    ]
    return {
        "items": json.dumps([_item_summary(item) for item in items], ensure_ascii=False),
        "already_detected": "\n".join(detected_lines) or "(none)",
        "reference_time": reference.isoformat(),
        "timezone": timezone,
    }


def validate_output(
    output: SignalExtractionOutput, *, known_ids: set[str]
) -> tuple[list[DetectedSignal], int]:
    """Convert model output to DetectedSignals; count rejected entries."""
    accepted: list[DetectedSignal] = []
    rejected = 0
    for signal in output.signals:
        if not set(signal.evidence_refs) <= known_ids:
            rejected += 1  # unsupported claim: cites evidence that does not exist
            continue
        due_at = signal.due_at
        if due_at is not None and due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=UTC)
        accepted.append(
            DetectedSignal(
                signal_type=SignalType(signal.signal_type),
                title=signal.title,
                summary=signal.summary,
                evidence_refs=tuple(sorted(signal.evidence_refs)),
                confidence=min(signal.confidence, 0.9),  # model output never outranks rules
                urgency=0.5,
                extraction_version=LLM_EXTRACTION_VERSION,
                due_at=due_at,
                reason_codes=("llm_extracted",),
            )
        )
    return accepted, rejected


async def extract_with_llm(
    provider: LLMProvider,
    items: list[SourceItem],
    already_detected: list[DetectedSignal],
    *,
    reference: datetime,
    timezone: str,
    trace_context: dict[str, str],
) -> tuple[list[DetectedSignal], int]:
    """Run the llm-v1 pass. Raises LLMProviderError on provider failure —
    the caller degrades to the deterministic baseline."""
    input_data = build_input_data(items, already_detected, reference=reference, timezone=timezone)
    output = await provider.generate_structured(
        task=PROMPT_TASK,
        input_data=input_data,
        output_schema=SignalExtractionOutput,
        trace_context=trace_context,
    )
    known_ids = {item.external_id for item in items}
    accepted, rejected = validate_output(output, known_ids=known_ids)
    if rejected:
        logger.warning("llm.extraction rejected=%d unsupported signals", rejected)
    return accepted, rejected


__all__ = [
    "LLM_EXTRACTION_VERSION",
    "ExtractedSignal",
    "LLMProviderError",
    "SignalExtractionOutput",
    "build_input_data",
    "extract_with_llm",
    "validate_output",
]
