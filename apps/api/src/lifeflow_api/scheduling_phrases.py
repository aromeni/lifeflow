"""Deterministic parsing of explicit scheduling requests in email text
(Stage 7, ADR 0003 D39).

Mirrors `deadline_phrases.py` in spirit: a bounded, transparent set of
UK-English scheduling cues ("please schedule", "can you book", "shall we
meet", …) plus strict field extraction — title, full date, start time, end
time or duration, timezone, attendees. Nothing is ever guessed: a field the
text does not state unambiguously is reported in ``missing`` and the request
stays non-executable. The source text is untrusted data throughout — it is
matched against closed patterns, never interpreted as instructions (threat
model T3), and an extracted value only ever fills a typed
`CalendarEventCreatePayload` that a human must review before anything is
created.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lifeflow_api.deadline_phrases import WEEKDAYS

# Closed set of scheduling-intent cues. Deliberately distinct from the
# generic request cues in detectors.py: "please schedule" must become a
# schedule_request signal with extraction requirements, never merely a
# generic reply-draft request.
_INTENT_CUES = re.compile(
    r"\bplease (?:schedule|arrange|book)\b"
    r"|\b(?:can|could|would) you (?:schedule|arrange|book)\b"
    r"|\bplease (?:create|set up) (?:a |the )?(?:calendar )?"
    r"(?:event|meeting|call|appointment)\b"
    r"|\b(?:please )?add (?:this|it|that) to my calendar\b"
    r"|\b(?:shall|can|could) we meet\b"
    r"|\bare you available on\b"
    r"|\bset up a meeting\b",
    re.I,
)

# Straight AND typographic ("smart") quotes: real mail clients write both.
_TITLE_CUE = re.compile(
    "\\b(?:called|titled|named)\\s+[\"'\u201c\u2018](.+?)[\"'\u201d\u2019]",
    re.I | re.S,
)
_SUBJECT_PREFIXES = re.compile(
    r"^(?:re:|fwd?:)\s*|^please\s+(?:schedule|arrange|book)\s*(?::\s*)?", re.I
)

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_NAMES = "|".join(_MONTHS)
_WEEKDAY_NAMES = "|".join(WEEKDAYS)

# Full, unambiguous dates only. A date without a year, or a bare weekday, is
# never resolved to "the next such day" — that would be a guess.
_DATE_DMY = re.compile(
    rf"\b(?:({_WEEKDAY_NAMES}),?\s+)?"
    rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_NAMES})\s+(\d{{4}})\b",
    re.I,
)
_DATE_MDY = re.compile(
    rf"\b(?:({_WEEKDAY_NAMES}),?\s+)?"
    rf"({_MONTH_NAMES})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b",
    re.I,
)
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

_TIME_RANGE = re.compile(
    r"\bfrom\s+(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?"
    "\\s*(?:to|until|[-\\u2013])\\s*"
    r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\b",
    re.I,
)
_TIME_SINGLE = re.compile(r"\bat\s+(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\b", re.I)
_DURATION = re.compile(
    r"\b(\d{1,3})[-\s]minutes?\b|\b(\d{1,2})[-\s]hours?\b|\ban hour\b",
    re.I,
)

_IANA_TIMEZONE = re.compile(r"\b([A-Z][A-Za-z_]+/[A-Z][A-Za-z_]+(?:/[A-Z][A-Za-z_]+)?)\b")

_EMAIL_IN_TEXT = re.compile(r"\b[A-Za-z0-9._%+\-']+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_SELF_ATTENDEE_CUES = re.compile(
    r"\badd (?:my email(?: address)?|me)\b(?:\s+as\s+(?:the\s+|an?\s+)?attendee)?"
    r"|\binvite me\b"
    r"|\binclude me\b",
    re.I,
)

MAX_ATTENDEES = 50


@dataclass(frozen=True)
class SchedulingExtraction:
    """The complete deterministic reading of one email's scheduling request.

    ``missing`` lists every required field the text did not state
    unambiguously (from: ``title``, ``date``, ``start_time``,
    ``end_or_duration``, ``attendees``). An extraction is executable only
    when intent was found, nothing is missing, and the start is in the
    future — checked by callers against their own reference clock.
    """

    has_intent: bool
    cue: str | None
    title: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    timezone: str | None
    attendees: tuple[str, ...]
    missing: tuple[str, ...]
    reason_codes: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return self.has_intent and not self.missing

    def executable(self, *, reference: datetime) -> bool:
        return self.complete and self.starts_at is not None and self.starts_at > reference


_NO_EXTRACTION = SchedulingExtraction(
    has_intent=False,
    cue=None,
    title=None,
    starts_at=None,
    ends_at=None,
    timezone=None,
    attendees=(),
    missing=(),
    reason_codes=(),
)


def _extract_title(text: str, subject: str) -> str | None:
    if match := _TITLE_CUE.search(text):
        title = " ".join(match.group(1).split())
        if title:
            return title
    cleaned = _SUBJECT_PREFIXES.sub("", subject.strip()).strip()
    return cleaned or None


def _extract_date(text: str, reasons: list[str]) -> tuple[int, int, int] | None:
    """Return (year, month, day) only when exactly one full date is stated
    and any written weekday actually matches it."""
    candidates: list[tuple[tuple[int, int, int], str | None]] = []
    for match in _DATE_DMY.finditer(text):
        weekday, day, month, year = match.groups()
        candidates.append(((int(year), _MONTHS[month.lower()], int(day)), weekday))
    for match in _DATE_MDY.finditer(text):
        weekday, month, day, year = match.groups()
        candidates.append(((int(year), _MONTHS[month.lower()], int(day)), weekday))
    for match in _DATE_ISO.finditer(text):
        year, month, day = match.groups()
        candidates.append((((int(year)), int(month), int(day)), None))

    valid: set[tuple[int, int, int]] = set()
    for (year, month, day), weekday in candidates:
        try:
            parsed = datetime(year, month, day)
        except ValueError:
            continue
        if weekday is not None and parsed.weekday() != WEEKDAYS[weekday.lower()]:
            reasons.append("date_weekday_mismatch")
            continue
        valid.add((year, month, day))
    if len(valid) > 1:
        reasons.append("ambiguous_date")
        return None
    return next(iter(valid)) if valid else None


def _hour_24(hour: int, minute: int, meridiem: str | None) -> tuple[int, int] | None:
    if meridiem is None:
        return (hour, minute) if 0 <= hour <= 23 and 0 <= minute <= 59 else None
    if not 1 <= hour <= 12 or not 0 <= minute <= 59:
        return None
    if meridiem.lower() == "am":
        return (0 if hour == 12 else hour, minute)
    return (12 if hour == 12 else hour + 12, minute)


def _extract_times(text: str) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    """Return (start_hm, end_hm). A bare-hour time with no am/pm marker is
    ambiguous and ignored; 24-hour times require explicit minutes."""
    if match := _TIME_RANGE.search(text):
        s_hour, s_min, s_mer, e_hour, e_min, e_mer = match.groups()
        start_meridiem = s_mer or e_mer  # "from 4 to 4:30 pm" — pm covers both
        if (start_meridiem is None and s_min is None) or (e_mer is None and e_min is None):
            return None, None
        start = _hour_24(int(s_hour), int(s_min or 0), start_meridiem)
        end = _hour_24(int(e_hour), int(e_min or 0), e_mer or s_mer)
        if start is not None and end is not None:
            return start, end
    if match := _TIME_SINGLE.search(text):
        hour, minute, meridiem = match.groups()
        if meridiem is None and minute is None:
            return None, None
        return _hour_24(int(hour), int(minute or 0), meridiem), None
    return None, None


def _extract_duration(text: str) -> timedelta | None:
    if match := _DURATION.search(text):
        minutes, hours = match.group(1), match.group(2)
        if minutes is not None:
            return timedelta(minutes=int(minutes))
        if hours is not None:
            return timedelta(hours=int(hours))
        return timedelta(hours=1)  # "an hour"
    return None


def _extract_timezone(text: str, default: str, reasons: list[str]) -> str:
    for match in _IANA_TIMEZONE.finditer(text):
        name = match.group(1)
        try:
            ZoneInfo(name)
        except ZoneInfoNotFoundError:
            continue
        return name
    reasons.append("timezone_from_profile")
    return default


def _extract_attendees(text: str, sender: str | None, reasons: list[str]) -> tuple[str, ...]:
    attendees: list[str] = []
    seen: set[str] = set()
    for match in _EMAIL_IN_TEXT.finditer(text):
        address = match.group(0)
        if address.lower() not in seen:
            seen.add(address.lower())
            attendees.append(address)
    if _SELF_ATTENDEE_CUES.search(text) and sender and sender.lower() not in seen:
        seen.add(sender.lower())
        attendees.append(sender)
        reasons.append("sender_as_attendee")
    return tuple(attendees)


def parse_scheduling_request(
    text: str,
    *,
    subject: str,
    sender: str | None,
    timezone: str,
) -> SchedulingExtraction:
    """Parse one email's text (subject + stored preview) for an explicit,
    fully-specified scheduling request.

    ``timezone`` is the user's configured timezone; it is used only when the
    text does not itself name a valid IANA timezone (recorded via the
    ``timezone_from_profile`` reason code) — consistent with how every other
    calendar proposal is already stamped with the profile timezone.
    """
    cue_match = _INTENT_CUES.search(text)
    if cue_match is None:
        return _NO_EXTRACTION

    reasons: list[str] = []
    missing: list[str] = []

    title = _extract_title(text, subject)
    if title is None:
        missing.append("title")

    timezone_name = _extract_timezone(text, timezone, reasons)
    date_parts = _extract_date(text, reasons)
    if date_parts is None:
        missing.append("date")
    start_hm, end_hm = _extract_times(text)
    duration = _extract_duration(text)
    if start_hm is None:
        missing.append("start_time")
    if end_hm is None and duration is None:
        missing.append("end_or_duration")

    starts_at: datetime | None = None
    ends_at: datetime | None = None
    if date_parts is not None and start_hm is not None:
        year, month, day = date_parts
        tz = ZoneInfo(timezone_name)
        starts_at = datetime(year, month, day, start_hm[0], start_hm[1], tzinfo=tz)
        if end_hm is not None:
            ends_at = datetime(year, month, day, end_hm[0], end_hm[1], tzinfo=tz)
        elif duration is not None:
            ends_at = starts_at + duration
        if ends_at is not None and ends_at <= starts_at:
            reasons.append("end_not_after_start")
            ends_at = None
            if "end_or_duration" not in missing:
                missing.append("end_or_duration")

    attendees = _extract_attendees(text, sender, reasons)
    if not attendees:
        missing.append("attendees")
    elif len(attendees) > MAX_ATTENDEES:
        missing.append("attendees")
        reasons.append("too_many_attendees")
        attendees = ()

    return SchedulingExtraction(
        has_intent=True,
        cue=cue_match.group(0),
        title=title,
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=timezone_name,
        attendees=attendees,
        missing=tuple(missing),
        reason_codes=tuple(reasons),
    )


__all__ = [
    "MAX_ATTENDEES",
    "SchedulingExtraction",
    "parse_scheduling_request",
]
