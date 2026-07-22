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
from lifeflow_api.scheduling_phrases import parse_scheduling_request

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


INVALID_ATTENDEES_METADATA = "invalid_attendees_metadata"


@dataclass(frozen=True)
class DetectionDiagnostic:
    """A safe record that one source item's metadata could not be processed.

    Carries a fixed code and the source item's own external id (an internal
    reference, not source content) — never the malformed value, names,
    addresses, or any other connector content (threat model logging rules).
    """

    code: str
    severity: str
    source_item_id: str


@dataclass(frozen=True)
class DetectionResult:
    signals: list[DetectedSignal]
    diagnostics: list[DetectionDiagnostic]


def _email_text(item: SourceItem) -> str:
    return f"{item.title}\n{item.metadata_json.get('body_preview', '')}"


def is_bulk_email(item: SourceItem) -> bool:
    sender = item.sender_or_organiser or ""
    local_part = sender.split("@")[0].lower()
    body = str(item.metadata_json.get("body_preview", "")).lower()
    return (
        local_part in _BULK_SENDER_LOCALS
        or "unsubscribe" in body
        # The RFC 2369/8058 List-Unsubscribe header (recorded at sync time,
        # ADR 0003 D42): the standard marker virtually all bulk/marketing
        # mail carries, which heuristic sender/keyword rules alone missed on
        # real promotional mail.
        or bool(item.metadata_json.get("list_unsubscribe"))
    )


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


def detect_schedule_requests(
    items: list[SourceItem], *, timezone: str, reference: datetime
) -> list[DetectedSignal]:
    """Explicit scheduling requests in inbox emails (ADR 0003 D39).

    A fully-specified, future request (title, date, start, end/duration,
    timezone, attendees all stated) is high-confidence and carries the event
    start as `due_at`; anything incomplete or in the past stays below the
    composition threshold — a clarification signal the user can see, never
    an executable calendar proposal built on guessed details.
    """
    signals = []
    for item in items:
        if item.source_type != SourceType.email:
            continue
        if item.metadata_json.get("folder") != "inbox" or is_bulk_email(item):
            continue
        extraction = parse_scheduling_request(
            _email_text(item),
            subject=item.title,
            sender=item.sender_or_organiser,
            timezone=timezone,
        )
        if not extraction.has_intent:
            continue
        executable = extraction.executable(reference=reference)
        in_past = (
            extraction.complete
            and extraction.starts_at is not None
            and extraction.starts_at <= reference
        )
        reasons = ["schedule_request"]
        if executable:
            reasons.append("event_details_extracted")
        else:
            reasons.append("event_details_incomplete")
            reasons.extend(f"missing_{name}" for name in extraction.missing)
            if in_past:
                reasons.append("event_in_past")
        reasons.extend(extraction.reason_codes)
        sender_name = item.metadata_json.get("sender_name", item.sender_or_organiser)
        summary = f"Scheduling cue '{extraction.cue}'" + (
            "; complete event details were extracted for review."
            if executable
            else "; the event details are incomplete, so nothing can be prepared yet."
        )
        signals.append(
            DetectedSignal(
                signal_type=SignalType.schedule_request,
                title=f"Scheduling request from {sender_name}: {item.title}",
                summary=summary,
                evidence_refs=(item.external_id,),
                confidence=0.9 if executable else 0.45,
                urgency=0.6 if executable else 0.3,
                due_at=extraction.starts_at if executable else None,
                reason_codes=tuple(dict.fromkeys(reasons)),
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
        recipient = _first_recipient(item)
        signals.append(
            DetectedSignal(
                signal_type=SignalType.commitment,
                title=f"You promised: {item.title}",
                summary=f"Commitment cue '{cue.group(0)}' in a message you sent"
                + (f" to {recipient}" if recipient else "")
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


def detect_meetings(items: list[SourceItem], *, reference: datetime) -> DetectionResult:
    signals = []
    diagnostics = []
    for item in items:
        if item.source_type != SourceType.calendar_event:
            continue
        if item.metadata_json.get("all_day") or item.occurred_at < reference:
            continue
        attendee_count, diagnostic = _attendee_metadata(item)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
            continue
        if attendee_count < 2:
            continue
        signals.append(
            DetectedSignal(
                signal_type=SignalType.meeting,
                title=f"Meeting: {item.title}",
                summary=f"{attendee_count} attendees, organised by {item.sender_or_organiser}",
                evidence_refs=(item.external_id,),
                confidence=0.95,
                urgency=0.5 if item.occurred_at - reference < timedelta(days=1) else 0.3,
                due_at=item.occurred_at,
                reason_codes=("meeting_upcoming",),
            )
        )
    return DetectionResult(signals=signals, diagnostics=diagnostics)


def parse_aware_datetime(value: object) -> datetime | None:
    """Parse an ISO date-time from untrusted connector metadata.

    Returns None for anything unusable — non-strings, malformed strings, and
    timezone-naive values. A naive value must never reach a comparison against
    an aware datetime, and a timezone is never guessed for it: the affected
    item degrades its own detection instead of aborting extraction.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _event_end(item: SourceItem) -> datetime | None:
    return parse_aware_datetime(item.metadata_json.get("ends_at"))


_ABSENT = object()


def _attendee_metadata(item: SourceItem) -> tuple[int, DetectionDiagnostic | None]:
    """Resolve an attendee count from untrusted metadata, or a diagnostic.

    A missing key is normal (no attendee information supplied) and yields a
    zero count with no diagnostic. A key present with a non-list value —
    string, object, number, or explicit null — is malformed: it cannot
    establish an attendee count, is never guessed or coerced, and is reported
    through a diagnostic instead of silently producing a zero count.
    """
    raw = item.metadata_json.get("attendees", _ABSENT)
    if raw is _ABSENT:
        return 0, None
    if not isinstance(raw, list):
        return 0, DetectionDiagnostic(
            code=INVALID_ATTENDEES_METADATA,
            severity="warning",
            source_item_id=item.external_id,
        )
    return len(raw), None


def _first_recipient(item: SourceItem) -> str | None:
    raw = item.metadata_json.get("recipients")
    if isinstance(raw, list) and raw and isinstance(raw[0], str):
        return raw[0]
    return None


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
        first_end = _event_end(first)
        if first_end is None:
            continue
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
        recipient = _first_recipient(item)
        signals.append(
            DetectedSignal(
                signal_type=SignalType.follow_up,
                title=f"No reply for {days_waiting} days: {item.title}",
                summary=f"You wrote to {recipient or 'someone'} "
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
) -> DetectionResult:
    """The full det-v1 baseline, in a fixed, deterministic order.

    Returns both the detected signals and any safe diagnostics recorded for
    source items whose metadata could not be processed — a typed result
    rather than a raised exception, so one malformed item degrades only its
    own detection and every other item is still extracted.
    """
    requests = detect_requests(items, timezone=timezone)
    commitments = detect_commitments(items, timezone=timezone)
    schedule_requests = detect_schedule_requests(items, timezone=timezone, reference=reference)
    covered = {
        ref
        for signal in (*requests, *commitments, *schedule_requests)
        for ref in signal.evidence_refs
    }
    deadlines = detect_deadlines(items, timezone=timezone, already_covered=covered)
    meetings = detect_meetings(items, reference=reference)
    conflicts = detect_conflicts(items, reference=reference)
    follow_ups = detect_follow_ups(items, reference=reference)
    return DetectionResult(
        signals=[
            *requests,
            *commitments,
            *schedule_requests,
            *deadlines,
            *meetings.signals,
            *conflicts,
            *follow_ups,
        ],
        diagnostics=list(meetings.diagnostics),
    )
