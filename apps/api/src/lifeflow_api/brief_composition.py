"""Deterministic, evidence-first daily brief composition (Stage 5).

Persisted active signals are assigned to one fixed section, ordered with
stable application rules, and expanded with user-owned source evidence. A
signal whose evidence cannot be resolved is omitted rather than surfaced as
an unsupported claim. Optional LLM prose may only select and repeat exact
application-authored sentences; any altered fact, date, priority, or action
is rejected and the deterministic summary remains available.
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.action_proposal_service import ActionProposalService
from lifeflow_api.audit import record_audit_event
from lifeflow_api.extraction import ExtractionSummary, SignalExtractionService
from lifeflow_api.llm.provider import LLMProvider, LLMProviderError
from lifeflow_api.models import (
    AccountStatus,
    Brief,
    BriefStatus,
    Signal,
    SignalType,
    SourceItem,
    SourceType,
)
from lifeflow_api.repositories import (
    BriefRepository,
    ConnectedAccountRepository,
    SignalRepository,
    SourceItemRepository,
)

logger = logging.getLogger(__name__)

COMPOSER_VERSION = "brief-det-v1"
BRIEF_PROMPT_TASK = "brief_composition_v1"
SOURCE_WINDOW = "past-14d/future-30d"
LOW_CONFIDENCE_THRESHOLD = 0.5


class BriefSectionKey(StrEnum):
    needs_attention = "needs_attention"
    today_upcoming = "today_upcoming"
    waiting_for = "waiting_for"
    suggested_actions = "suggested_actions"
    low_confidence_review = "low_confidence_review"


SECTION_LABELS = {
    BriefSectionKey.needs_attention: "Needs attention",
    BriefSectionKey.today_upcoming: "Today and upcoming",
    BriefSectionKey.waiting_for: "Waiting for",
    BriefSectionKey.suggested_actions: "Suggested actions",
    BriefSectionKey.low_confidence_review: "Low-confidence review",
}
SECTION_ORDER = tuple(BriefSectionKey)

ACTIONABLE_TYPES = {
    SignalType.request,
    SignalType.commitment,
    SignalType.deadline,
    SignalType.follow_up,
    SignalType.conflict,
}


class BriefEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_item_id: str | None
    source_ref: str
    source_type: str
    title: str
    sender_or_organiser: str | None
    occurred_at: datetime
    excerpt: str


class BriefItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str
    signal_type: str
    title: str
    summary: str
    due_at: datetime | None
    confidence: float
    priority_score: float
    priority_band: str
    reason_codes: list[str]
    actionable: bool
    suggested_action: str | None
    evidence: list[BriefEvidence] = Field(min_length=1)


class BriefSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: BriefSectionKey
    label: str
    items: list[BriefItem]


class BriefNotice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class BriefDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: list[BriefSection]
    notices: list[BriefNotice]


class BriefSummarySentence(BaseModel):
    """One optional prose sentence tied to one persisted signal."""

    model_config = ConfigDict(extra="forbid")

    signal_id: str
    text: str = Field(min_length=1, max_length=300)


class BriefCompositionOutput(BaseModel):
    """Strict output for optional LLM-authored headline prose.

    Semantic validation additionally requires every sentence to be an exact
    match from the deterministic allow-list built below.
    """

    model_config = ConfigDict(extra="forbid")

    summary_sentences: list[BriefSummarySentence] = Field(min_length=1, max_length=3)


class BriefProseValidationError(ValueError):
    """Optional prose contained a sentence outside the deterministic allow-list."""


@dataclass(frozen=True)
class ComposedSections:
    sections: list[BriefSection]
    included_signals: int
    omitted_signals: int


def _section_for(signal: Signal) -> BriefSectionKey:
    signal_type = SignalType(signal.signal_type)
    if signal.confidence < LOW_CONFIDENCE_THRESHOLD:
        return BriefSectionKey.low_confidence_review
    if signal_type == SignalType.follow_up:
        return BriefSectionKey.waiting_for
    if signal_type == SignalType.meeting:
        return BriefSectionKey.today_upcoming
    if signal_type == SignalType.conflict or signal.priority_band == "high":
        return BriefSectionKey.needs_attention
    return BriefSectionKey.suggested_actions


def _suggested_action(signal_type: SignalType, section: BriefSectionKey) -> str | None:
    if section == BriefSectionKey.low_confidence_review:
        return None
    return {
        SignalType.request: "Review the request and decide how to respond.",
        SignalType.commitment: "Review the commitment and plan the next step.",
        SignalType.deadline: "Review the deadline and decide what to complete.",
        SignalType.follow_up: "Decide whether to follow up.",
        SignalType.conflict: "Resolve the overlap before the earlier event starts.",
    }.get(signal_type)


def _evidence_from_source(item: SourceItem) -> BriefEvidence:
    if item.source_type == SourceType.email:
        excerpt = str(item.metadata_json.get("body_preview", ""))
    else:
        excerpt = str(
            item.metadata_json.get("description")
            or item.metadata_json.get("location")
            or "No additional source excerpt was retained."
        )
    return BriefEvidence(
        source_item_id=str(item.id) if item.id is not None else None,
        source_ref=item.external_id,
        source_type=item.source_type,
        title=item.title,
        sender_or_organiser=item.sender_or_organiser,
        occurred_at=item.occurred_at,
        excerpt=excerpt,
    )


def _item_sort_key(section: BriefSectionKey, item: BriefItem) -> tuple[object, ...]:
    due_timestamp = item.due_at.timestamp() if item.due_at is not None else float("inf")
    stable_tail: tuple[object, ...] = (
        -item.priority_score,
        due_timestamp,
        -item.confidence,
        item.signal_type,
        item.title.casefold(),
        tuple(e.source_ref for e in item.evidence),
    )
    if section == BriefSectionKey.today_upcoming:
        event_timestamp = min(e.occurred_at.timestamp() for e in item.evidence)
        return (event_timestamp, *stable_tail)
    if section == BriefSectionKey.low_confidence_review:
        return (item.confidence, *stable_tail)
    return stable_tail


def compose_sections(signals: list[Signal], source_items: list[SourceItem]) -> ComposedSections:
    """Pure deterministic composition from persisted values.

    This function is also the brief-level evaluation boundary: it performs no
    database or model calls and never invents evidence.
    """

    sources = {item.external_id: item for item in source_items}
    items_by_section: dict[BriefSectionKey, list[BriefItem]] = {key: [] for key in SECTION_ORDER}
    omitted = 0

    for signal in signals:
        if not signal.evidence_refs or any(ref not in sources for ref in signal.evidence_refs):
            omitted += 1
            continue
        try:
            section = _section_for(signal)
            signal_type = SignalType(signal.signal_type)
        except ValueError:
            omitted += 1
            continue
        actionable = (
            signal_type in ACTIONABLE_TYPES and section != BriefSectionKey.low_confidence_review
        )
        item = BriefItem(
            signal_id=str(signal.id) if signal.id is not None else signal.dedupe_key,
            signal_type=signal.signal_type,
            title=signal.title,
            summary=signal.summary,
            due_at=signal.due_at,
            confidence=signal.confidence,
            priority_score=signal.priority_score or 0.0,
            priority_band=signal.priority_band or "low",
            reason_codes=list(signal.reason_codes),
            actionable=actionable,
            suggested_action=_suggested_action(signal_type, section) if actionable else None,
            evidence=[_evidence_from_source(sources[ref]) for ref in signal.evidence_refs],
        )
        items_by_section[section].append(item)

    sections = [
        BriefSection(
            key=key,
            label=SECTION_LABELS[key],
            items=sorted(items_by_section[key], key=lambda item: _item_sort_key(key, item)),
        )
        for key in SECTION_ORDER
    ]
    included = sum(len(section.items) for section in sections)
    return ComposedSections(sections=sections, included_signals=included, omitted_signals=omitted)


def deterministic_summary(sections: list[BriefSection]) -> str:
    counts = {section.key: len(section.items) for section in sections}
    if not sum(counts.values()):
        return (
            "There is nothing to review yet. Generate again after source information is available."
        )

    needs = counts[BriefSectionKey.needs_attention]
    upcoming = counts[BriefSectionKey.today_upcoming]
    waiting = counts[BriefSectionKey.waiting_for]
    suggested = counts[BriefSectionKey.suggested_actions]
    low = counts[BriefSectionKey.low_confidence_review]
    summary = (
        f"{needs} item{'s' if needs != 1 else ''} need attention; "
        f"{upcoming} {'are' if upcoming != 1 else 'is'} today or upcoming. "
        f"{waiting} follow-up{'s are' if waiting != 1 else ' is'} waiting; "
        f"{suggested} more item{'s have' if suggested != 1 else ' has'} suggested next steps."
    )
    if low:
        summary += f" {low} low-confidence item{'s need' if low != 1 else ' needs'} your judgement."
    return summary


def allowed_summary_sentences(sections: list[BriefSection]) -> dict[str, str]:
    """Return the only prose sentences an optional provider may emit."""

    suffixes = {
        BriefSectionKey.needs_attention: "needs attention.",
        BriefSectionKey.today_upcoming: "is today or upcoming.",
        BriefSectionKey.waiting_for: "is waiting for a response.",
        BriefSectionKey.suggested_actions: "has a suggested next step.",
        BriefSectionKey.low_confidence_review: "needs your judgement.",
    }
    return {
        item.signal_id: f"{item.title} {suffixes[section.key]}"
        for section in sections
        for item in section.items
    }


def validate_optional_summary(output: BriefCompositionOutput, *, allowed: dict[str, str]) -> str:
    seen: set[str] = set()
    accepted: list[str] = []
    for sentence in output.summary_sentences:
        if sentence.signal_id in seen:
            raise BriefProseValidationError("A signal may appear only once in the summary.")
        if allowed.get(sentence.signal_id) != sentence.text:
            raise BriefProseValidationError(
                "Summary prose must exactly match a deterministic supported sentence."
            )
        seen.add(sentence.signal_id)
        accepted.append(sentence.text)
    return " ".join(accepted)


class BriefService:
    """On-demand extraction + deterministic brief generation orchestration."""

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

    async def generate(self, *, timezone: str, reference: datetime | None = None) -> Brief:
        reference = reference or datetime.now(UTC)
        if reference.tzinfo is None:
            raise ValueError("Brief generation reference must be timezone-aware.")

        extraction = await SignalExtractionService(
            self._session, self._user_id, llm_provider=self._provider
        ).extract(timezone=timezone, reference=reference)
        signals = await SignalRepository(self._session, self._user_id).list_ranked(limit=1000)
        sources = await SourceItemRepository(self._session, self._user_id).list(limit=1000)
        composed = compose_sections(signals, sources)

        accounts = await ConnectedAccountRepository(self._session, self._user_id).list()
        inactive_accounts = [
            account for account in accounts if account.status != AccountStatus.active
        ]
        notices: list[BriefNotice] = []
        if inactive_accounts:
            notices.append(
                BriefNotice(
                    code="source_partial",
                    message=(
                        f"{len(inactive_accounts)} configured source"
                        f"{'s are' if len(inactive_accounts) != 1 else ' is'} unavailable. "
                        "The brief uses previously persisted evidence only."
                    ),
                )
            )
        if composed.omitted_signals:
            notices.append(
                BriefNotice(
                    code="evidence_missing",
                    message=(
                        f"{composed.omitted_signals} signal"
                        f"{'s were' if composed.omitted_signals != 1 else ' was'} omitted "
                        "because its source evidence could not be resolved."
                    ),
                )
            )

        summary = deterministic_summary(composed.sections)
        prose_state = "not_configured"
        llm_summary_used = False
        llm_summary_failed = False
        allowed = allowed_summary_sentences(composed.sections)
        if self._provider is not None and allowed:
            try:
                output = await self._provider.generate_structured(
                    task=BRIEF_PROMPT_TASK,
                    input_data={
                        "allowed_sentences": json.dumps(
                            [
                                {"signal_id": signal_id, "text": text}
                                for signal_id, text in allowed.items()
                            ],
                            ensure_ascii=False,
                        )
                    },
                    output_schema=BriefCompositionOutput,
                    trace_context={
                        "task": "brief_composition",
                        "user_id": str(self._user_id),
                    },
                )
                summary = validate_optional_summary(output, allowed=allowed)
                prose_state = "augmented"
                llm_summary_used = True
            except (LLMProviderError, ValidationError, BriefProseValidationError):
                llm_summary_failed = True
                prose_state = "degraded"
                logger.warning(
                    "llm.brief_composition failed validation; using deterministic summary"
                )

        if extraction.llm_failed or llm_summary_failed:
            notices.append(
                BriefNotice(
                    code="llm_degraded",
                    message=(
                        "Optional model augmentation was unavailable or rejected. "
                        "This brief was composed from deterministic signals and rules."
                    ),
                )
            )
        if not composed.included_signals and not inactive_accounts and not composed.omitted_signals:
            notices.append(
                BriefNotice(
                    code="brief_empty",
                    message=(
                        "No supported signals are available yet. "
                        "Add or refresh sources, then try again."
                    ),
                )
            )
        if extraction.diagnostic_counts:
            notices.append(
                BriefNotice(
                    code="signal_data_quality",
                    message="Some calendar information could not be processed.",
                )
            )

        partial = bool(
            inactive_accounts or composed.omitted_signals or extraction.diagnostic_counts
        )
        degraded = extraction.llm_failed or llm_summary_failed
        if partial:
            status = BriefStatus.partial
        elif not composed.included_signals:
            status = BriefStatus.empty
        elif degraded:
            status = BriefStatus.degraded
        else:
            status = BriefStatus.complete

        local_date = reference.astimezone(ZoneInfo(timezone)).date()
        briefing_date = datetime.combine(
            local_date, time.min, tzinfo=ZoneInfo(timezone)
        ).astimezone(UTC)
        briefs = BriefRepository(self._session, self._user_id)
        version = await briefs.next_version(briefing_date)
        section_counts = {str(section.key): len(section.items) for section in composed.sections}
        document = BriefDocument(sections=composed.sections, notices=notices)
        metadata = {
            "composer_version": COMPOSER_VERSION,
            "reference_at": reference.astimezone(UTC).isoformat(),
            "timezone": timezone,
            "source_state": "partial" if partial else "complete",
            "source_item_count": len(sources),
            "signal_count": len(signals),
            "included_signal_count": composed.included_signals,
            "omitted_signal_count": composed.omitted_signals,
            "section_counts": section_counts,
            "extraction_versions": sorted({signal.extraction_version for signal in signals}),
            "extraction": asdict(extraction),
            "prose_state": prose_state,
            "llm_summary_used": llm_summary_used,
            "llm_summary_failed": llm_summary_failed,
        }
        brief = Brief(
            user_id=self._user_id,
            briefing_date=briefing_date,
            version=version,
            status=status,
            summary=summary,
            sections_json=document.model_dump(mode="json"),
            source_window=SOURCE_WINDOW,
            prompt_version=BRIEF_PROMPT_TASK if self._provider is not None and allowed else None,
            model_metadata=metadata,
        )
        briefs.add(brief)
        await self._session.flush()
        await self._session.refresh(brief)
        proposal_generation = await ActionProposalService(
            self._session, self._user_id
        ).generate_from_brief(
            brief=brief,
            signals=signals,
            sources=sources,
            timezone=timezone,
            reference=reference,
        )
        brief.model_metadata = {
            **metadata,
            "proposal_generation": asdict(proposal_generation),
        }
        if proposal_generation.skipped:
            # A candidate action could not be prepared safely from its source
            # data. The brief itself is unaffected; state it honestly without
            # exposing any source content, and mark the brief partial.
            count = proposal_generation.skipped
            notices.append(
                BriefNotice(
                    code="proposal_candidates_skipped",
                    message=(
                        f"{count} suggested action{'s' if count != 1 else ''} could not be "
                        "prepared safely from the source data and "
                        f"{'were' if count != 1 else 'was'} skipped."
                    ),
                )
            )
            brief.sections_json = BriefDocument(
                sections=composed.sections, notices=notices
            ).model_dump(mode="json")
            if brief.status == BriefStatus.complete:
                brief.status = BriefStatus.partial
                status = BriefStatus.partial
        record_audit_event(
            self._session,
            user_id=self._user_id,
            actor="system:brief",
            event_type="brief.generated",
            entity_type="brief",
            entity_id=str(brief.id),
            metadata={
                "version": version,
                "status": str(status),
                "composer_version": COMPOSER_VERSION,
                "included_signals": composed.included_signals,
                "omitted_signals": composed.omitted_signals,
                "llm_summary_used": llm_summary_used,
                "llm_summary_failed": llm_summary_failed,
                "proposals_created": proposal_generation.created,
                "proposals_updated": proposal_generation.updated,
                "proposals_unchanged": proposal_generation.unchanged,
                "proposals_preserved": proposal_generation.preserved,
                "proposals_skipped": proposal_generation.skipped,
                "detection_diagnostics": extraction.diagnostic_counts,
            },
        )
        await self._session.flush()
        return brief


def parse_brief_document(brief: Brief) -> BriefDocument:
    """Validate persisted JSON again before it crosses the API boundary."""

    return BriefDocument.model_validate(brief.sections_json)


def extraction_metadata(summary: ExtractionSummary) -> dict[str, object]:
    """Typed helper retained for contract/eval callers that need safe counters."""

    return asdict(summary)


__all__ = [
    "BRIEF_PROMPT_TASK",
    "COMPOSER_VERSION",
    "BriefCompositionOutput",
    "BriefDocument",
    "BriefItem",
    "BriefNotice",
    "BriefProseValidationError",
    "BriefSection",
    "BriefSectionKey",
    "BriefService",
    "BriefSummarySentence",
    "ComposedSections",
    "allowed_summary_sentences",
    "compose_sections",
    "deterministic_summary",
    "parse_brief_document",
    "validate_optional_summary",
]
