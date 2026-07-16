"""Deterministic signal detectors — the extraction baseline (skill §9 step 4).

Every rule here is transparent and unit-testable: keyword cues, thread
arithmetic, and interval overlap. Detectors run first and always; LLM-assisted
extraction (extraction_version llm-v1) may only ADD signals these rules miss,
never replace them.

All detectors treat source content as untrusted data: text is matched against
patterns, never interpreted as instructions (threat model T3).
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from lifeflow_api.deadline_phrases import parse_due_phrase
from lifeflow_api.models import SignalType, SourceItem, SourceType

DETERMINISTIC_VERSION = "det-v1"
STALE_FOLLOW_UP_DAYS = 5  # assumption A5

# Bulk/newsletter senders never yield actionable signals (transparent rule).
_BULK_SENDER_LOCALS = {
    "newsletter",
    "noreply",
    "no-reply",
    "survey",
    "marketing",
    "winners",
    "promotions",
    "tickets",
}

_STRONG_REQUEST_CUES = re.compile(
    r"\b(?:can|could|would) you\b"
    r"|\bplease (?:send|reply|confirm|upload|circulate|check|share|provide)\b"
    r"|\bwe (?:still )?need\b"
    r"|\bwhat(?:'s| is) your availability\b",
    re.I,
)
_WEAK_REQUEST_CUES = re.compile(
    r"\bwhen you get a chance\b|\bit would be good to know\b|\bany movement on\b",
    re.I,
)
_COMMITMENT_CUES = re.compile(r"\bI(?:'ll| will)\b", re.I)
_DEADLINE_TITLE_CUES = re.compile(r"\b(?:due|deadline)\b", re.I)


@dataclass(frozen=True)
class DetectedSignal:
    """Intermediate signal, produced by detectors or validated LLM output."""

    signal_type: SignalType
    title: str
    summary: str
    evidence_refs: tuple[str, ...]  # source item external ids
    confidence: float
    urgency: float
    extraction_version: str = DETERMINISTIC_VERSION
    due_at: datetime | None = None
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


def _email_text(item: SourceItem) -> str:
    return f"{item.title}\n{item.metadata_json.get('body_preview', '')}"


def is_bulk_email(item: SourceItem) -> bool:
    sender = item.sender_or_organiser or ""
    local_part = sender.split("@")[0].lower()
    body = str(item.metadata_json.get("body_preview", "")).lower()
    return local_part in _BULK_SENDER_LOCALS or "unsubscribe" in body


def _local_reference(item: SourceItem, timezone: str) -> datetime:
    return item.occurred_at.astimezone(ZoneInfo(timezone))


def detect_requests(items: list[SourceItem], *, timezone: str) -> list[DetectedSignal]:
    signals = []
    for item in items:
        if item.source_type != SourceType.email:
            continue
        if item.metadata_json.get("folder") != "inbox" or is_bulk_email(item):
            continue
        text = _email_text(item)
        strong = _STRONG_REQUEST_CUES.search(text)
        weak = _WEAK_REQUEST_CUES.search(text)
        if not strong and not weak:
            continue
        cue = strong or weak
        assert cue is not None  # noqa: S101 — guarded by the check above
        due_at, phrase = parse_due_phrase(text, reference=_local_reference(item, timezone))
        reasons = ["explicit_request"] if strong else ["weak_request_cue"]
        if phrase:
            reasons.append("deadline_phrase")
        sender_name = item.metadata_json.get("sender_name", item.sender_or_organiser)
        signals.append(
            DetectedSignal(
                signal_type=SignalType.request,
                title=f"Request from {sender_name}: {item.title}",
                summary=f"Detected cue '{cue.group(0)}'"
                + (f"; deadline phrase '{phrase}'" if phrase else ""),
                evidence_refs=(item.external_id,),
                confidence=0.85 if strong else 0.45,
                urgency=0.6 if strong else 0.3,
                due_at=due_at,
                reason_codes=tuple(reasons),
            )
        )
    return signals


def detect_commitments(items: list[SourceItem], *, timezone: str) -> list[DetectedSignal]:
    signals = []
    for item in items:
        if item.source_type != SourceType.email:
            continue
        if item.metadata_json.get("folder") != "sent":
            continue
        text = _email_text(item)
        cue = _COMMITMENT_CUES.search(text)
        if not cue:
            continue
        due_at, phrase = parse_due_phrase(text, reference=_local_reference(item, timezone))
        recipients = item.metadata_json.get("recipients", [])
        signals.append(
            DetectedSignal(
                signal_type=SignalType.commitment,
                title=f"You promised: {item.title}",
                summary=f"Commitment cue '{cue.group(0)}' in a message you sent"
                + (f" to {recipients[0]}" if recipients else "")
                + (f"; deadline phrase '{phrase}'" if phrase else ""),
                evidence_refs=(item.external_id,),
                confidence=0.8 if phrase else 0.6,
                urgency=0.6 if due_at else 0.4,
                due_at=due_at,
                reason_codes=("commitment_made", *(("deadline_phrase",) if phrase else ())),
            )
        )
    return signals


def detect_deadlines(
    items: list[SourceItem], *, timezone: str, already_covered: set[str]
) -> list[DetectedSignal]:
    """Deadline phrases in emails not already covered by a request/commitment,
    plus all-day calendar entries whose title names a due date."""
    signals = []
    for item in items:
        if item.source_type == SourceType.email:
            if item.external_id in already_covered or is_bulk_email(item):
                continue
            if item.metadata_json.get("folder") != "inbox":
                continue
            due_at, phrase = parse_due_phrase(
                _email_text(item), reference=_local_reference(item, timezone)
            )
            if due_at is None:
                continue
            signals.append(
                DetectedSignal(
                    signal_type=SignalType.deadline,
                    title=f"Deadline mentioned: {item.title}",
                    summary=f"Deadline phrase '{phrase}' with no direct request cue",
                    evidence_refs=(item.external_id,),
                    confidence=0.7,
                    urgency=0.6,
                    due_at=due_at,
                    reason_codes=("deadline_phrase",),
                )
            )
        elif item.source_type == SourceType.calendar_event:
            if not item.metadata_json.get("all_day"):
                continue
            if not _DEADLINE_TITLE_CUES.search(item.title):
                continue
            signals.append(
                DetectedSignal(
                    signal_type=SignalType.deadline,
                    title=item.title,
                    summary="All-day calendar entry naming a due date",
                    evidence_refs=(item.external_id,),
                    confidence=0.9,
                    urgency=0.8,
                    due_at=item.occurred_at,
                    reason_codes=("deadline_detected",),
                )
            )
    return signals


def detect_meetings(items: list[SourceItem], *, reference: datetime) -> list[DetectedSignal]:
    signals = []
    for item in items:
        if item.source_type != SourceType.calendar_event:
            continue
        if item.metadata_json.get("all_day") or item.occurred_at < reference:
            continue
        attendees = item.metadata_json.get("attendees", [])
        if len(attendees) < 2:
            continue
        signals.append(
            DetectedSignal(
                signal_type=SignalType.meeting,
                title=f"Meeting: {item.title}",
                summary=f"{len(attendees)} attendees, organised by {item.sender_or_organiser}",
                evidence_refs=(item.external_id,),
                confidence=0.95,
                urgency=0.5 if item.occurred_at - reference < timedelta(days=1) else 0.3,
                due_at=item.occurred_at,
                reason_codes=("meeting_upcoming",),
            )
        )
    return signals


def detect_conflicts(items: list[SourceItem], *, reference: datetime) -> list[DetectedSignal]:
    events = sorted(
        (
            item
            for item in items
            if item.source_type == SourceType.calendar_event
            and not item.metadata_json.get("all_day")
            and item.occurred_at >= reference
        ),
        key=lambda item: (item.occurred_at, item.external_id),
    )
    signals = []
    for i, first in enumerate(events):
        first_end = datetime.fromisoformat(str(first.metadata_json["ends_at"]))
        for second in events[i + 1 :]:
            if second.occurred_at >= first_end:
                break
            signals.append(
                DetectedSignal(
                    signal_type=SignalType.conflict,
                    title=f"Calendar conflict: '{first.title}' overlaps '{second.title}'",
                    summary=(
                        f"'{second.title}' starts at {second.occurred_at.isoformat()} before "
                        f"'{first.title}' ends at {first_end.isoformat()}"
                    ),
                    evidence_refs=(first.external_id, second.external_id),
                    confidence=1.0,
                    urgency=0.9,
                    due_at=first.occurred_at,
                    reason_codes=("calendar_conflict",),
                )
            )
    return signals


def detect_follow_ups(items: list[SourceItem], *, reference: datetime) -> list[DetectedSignal]:
    """Sent messages in a thread with no later inbox reply, older than the
    stale threshold."""
    emails = [item for item in items if item.source_type == SourceType.email]
    signals = []
    for item in emails:
        if item.metadata_json.get("folder") != "sent":
            continue
        thread_id = item.metadata_json.get("thread_id")
        if not thread_id:
            continue
        days_waiting = (reference - item.occurred_at).days
        if days_waiting < STALE_FOLLOW_UP_DAYS:
            continue
        replied = any(
            other.metadata_json.get("thread_id") == thread_id
            and other.metadata_json.get("folder") == "inbox"
            and other.occurred_at > item.occurred_at
            for other in emails
        )
        if replied:
            continue
        recipients = item.metadata_json.get("recipients", [])
        signals.append(
            DetectedSignal(
                signal_type=SignalType.follow_up,
                title=f"No reply for {days_waiting} days: {item.title}",
                summary=f"You wrote to {recipients[0] if recipients else 'someone'} "
                f"{days_waiting} days ago and nothing has arrived in that thread since.",
                evidence_refs=(item.external_id,),
                confidence=0.85,
                urgency=min(0.4 + days_waiting * 0.05, 1.0),
                reason_codes=(f"no_reply_{days_waiting}d",),
            )
        )
    return signals


def run_deterministic_detectors(
    items: list[SourceItem], *, reference: datetime, timezone: str
) -> list[DetectedSignal]:
    """The full det-v1 baseline, in a fixed, deterministic order."""
    requests = detect_requests(items, timezone=timezone)
    commitments = detect_commitments(items, timezone=timezone)
    covered = {ref for signal in (*requests, *commitments) for ref in signal.evidence_refs}
    deadlines = detect_deadlines(items, timezone=timezone, already_covered=covered)
    meetings = detect_meetings(items, reference=reference)
    conflicts = detect_conflicts(items, reference=reference)
    follow_ups = detect_follow_ups(items, reference=reference)
    return [*requests, *commitments, *deadlines, *meetings, *conflicts, *follow_ups]
