"""SignalExtractionService — the orchestrated extraction pipeline (skill §9).

Order is fixed: deterministic detectors always run first and always persist;
the LLM pass (when a provider is configured) may only ADD signals the rules
missed. Provider failure degrades gracefully — the deterministic baseline is
the product's floor, and the failure is visible in the audit trail.
"""

import hashlib
import logging
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.audit import record_audit_event
from lifeflow_api.detectors import DetectedSignal, run_deterministic_detectors
from lifeflow_api.extraction_llm import extract_with_llm
from lifeflow_api.llm.provider import LLMProvider, LLMProviderError
from lifeflow_api.models import Signal
from lifeflow_api.priority import ScoredSignal, build_sender_frequency, score_signal
from lifeflow_api.repositories import SignalRepository, SourceItemRepository

logger = logging.getLogger(__name__)


def dedupe_key(signal: DetectedSignal) -> str:
    canonical = f"{signal.signal_type}|{','.join(sorted(signal.evidence_refs))}"
    return hashlib.sha256(canonical.encode()).hexdigest()


def deduplicate(signals: list[DetectedSignal]) -> list[DetectedSignal]:
    """First occurrence wins — deterministic signals are listed first, so a
    deterministic signal always beats an LLM duplicate."""
    seen: set[str] = set()
    unique: list[DetectedSignal] = []
    for signal in signals:
        key = dedupe_key(signal)
        if key not in seen:
            seen.add(key)
            unique.append(signal)
    return unique


@dataclass
class ExtractionSummary:
    deterministic: int = 0
    llm_added: int = 0
    llm_rejected: int = 0
    llm_used: bool = False
    llm_failed: bool = False
    persisted_new: int = 0
    persisted_updated: int = 0
    persisted_unchanged: int = 0
    # Safe counts only: fixed diagnostic code -> occurrences. Never a source
    # item id or the malformed value itself (threat model logging rules).
    diagnostic_counts: dict[str, int] = field(default_factory=dict)


class SignalExtractionService:
    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._provider = llm_provider
        self._signals = SignalRepository(session, user_id)

    async def extract(
        self, *, timezone: str, reference: datetime | None = None
    ) -> ExtractionSummary:
        reference = reference or datetime.now(UTC)
        items = await SourceItemRepository(self._session, self._user_id).list(limit=1000)
        summary = ExtractionSummary()

        detection = run_deterministic_detectors(items, reference=reference, timezone=timezone)
        detected = detection.signals
        summary.deterministic = len(detected)
        summary.diagnostic_counts = dict(
            Counter(diagnostic.code for diagnostic in detection.diagnostics)
        )

        combined = list(detected)
        if self._provider is not None:
            try:
                llm_signals, rejected = await extract_with_llm(
                    self._provider,
                    items,
                    detected,
                    reference=reference,
                    timezone=timezone,
                    trace_context={"task": "signal_extraction", "user_id": str(self._user_id)},
                )
                summary.llm_used = True
                summary.llm_rejected = rejected
                before = len(deduplicate(combined))
                combined = deduplicate([*detected, *llm_signals])
                summary.llm_added = len(combined) - before
            except LLMProviderError:
                # Degraded mode: deterministic results stand; failure is visible.
                summary.llm_failed = True
                logger.warning("llm.extraction failed; continuing with deterministic baseline")
        combined = deduplicate(combined)

        items_by_external = {item.external_id: item for item in items}
        sender_frequency = build_sender_frequency(items)
        for signal in combined:
            scored = score_signal(
                signal,
                reference=reference,
                items_by_external=items_by_external,
                sender_frequency=sender_frequency,
            )
            outcome = await self._upsert(scored)
            if outcome == "new":
                summary.persisted_new += 1
            elif outcome == "updated":
                summary.persisted_updated += 1
            else:
                summary.persisted_unchanged += 1

        await self._session.flush()
        record_audit_event(
            self._session,
            user_id=self._user_id,
            actor="system:extraction",
            event_type="extraction.completed",
            entity_type="signal",
            entity_id="-",
            metadata={
                "deterministic": summary.deterministic,
                "llm_used": summary.llm_used,
                "llm_added": summary.llm_added,
                "llm_rejected": summary.llm_rejected,
                "llm_failed": summary.llm_failed,
                "persisted_new": summary.persisted_new,
                "persisted_updated": summary.persisted_updated,
                "persisted_unchanged": summary.persisted_unchanged,
                "diagnostic_counts": summary.diagnostic_counts,
            },
        )
        await self._session.flush()
        return summary

    async def _upsert(self, scored: ScoredSignal) -> str:
        signal = scored.signal
        key = dedupe_key(signal)
        existing = await self._signals.get_by_dedupe_key(key)
        if existing is None:
            self._signals.add(
                Signal(
                    user_id=self._user_id,
                    signal_type=signal.signal_type,
                    title=signal.title,
                    summary=signal.summary,
                    evidence_refs=list(signal.evidence_refs),
                    due_at=signal.due_at,
                    confidence=signal.confidence,
                    urgency=signal.urgency,
                    importance=0.0,  # importance is folded into the score; kept for schema parity
                    extraction_version=signal.extraction_version,
                    priority_score=scored.score,
                    priority_band=scored.band,
                    reason_codes=list(scored.reason_codes),
                    dedupe_key=key,
                )
            )
            return "new"
        # Change-aware update: identical re-runs must not rewrite rows. Only
        # the meaningful persisted fields below participate in the comparison.
        fields = {
            "title": signal.title,
            "summary": signal.summary,
            "due_at": signal.due_at,
            "confidence": signal.confidence,
            "urgency": signal.urgency,
            "extraction_version": signal.extraction_version,
            "priority_score": scored.score,
            "priority_band": scored.band,
            "reason_codes": list(scored.reason_codes),
        }
        if all(getattr(existing, name) == value for name, value in fields.items()):
            return "unchanged"
        for name, value in fields.items():
            setattr(existing, name, value)
        return "updated"
