"""Deterministic parsing of relative deadline phrases in email text.

Deliberately small and transparent: a bounded set of UK-English phrases
("by Wednesday", "by the 30th", "before the end of the month", …) resolved
against the moment the message was sent, in the sender's timezone. Anything
outside this set is left for LLM-assisted extraction — with low confidence.

Deadlines resolve to the END of the named day (23:59 local) and are returned
in UTC.
"""

import calendar
import re
from datetime import UTC as _UTC
from datetime import datetime, time, timedelta

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_END_OF_DAY = re.compile(r"\b(?:by|before)\s+(?:the\s+)?end of (?:the )?day\b|\bby eod\b", re.I)
_END_OF_WEEK = re.compile(r"\b(?:by|before)\s+(?:the\s+)?end of (?:the |this )?week\b", re.I)
_END_OF_MONTH = re.compile(r"\b(?:by|before)\s+(?:the\s+)?end of (?:the |this )?month\b", re.I)
_BY_WEEKDAY = re.compile(
    r"\b(?:by|before)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I
)
_BY_ORDINAL = re.compile(r"\b(?:by|before)\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\b", re.I)
_TOMORROW = re.compile(r"\b(?:by|before)\s+tomorrow\b|\btomorrow\b", re.I)


def _at_end_of_day(day: datetime) -> datetime:
    local = datetime.combine(day.date(), time(23, 59), tzinfo=day.tzinfo)
    return local.astimezone(_UTC)


def parse_due_phrase(text: str, *, reference: datetime) -> tuple[datetime | None, str | None]:
    """Return (due_at_utc, matched_phrase) for the first recognised phrase.

    `reference` must be timezone-aware, in the timezone the phrase should be
    interpreted in (normally the sender's local time when the text was written).
    """
    if match := _END_OF_DAY.search(text):
        return _at_end_of_day(reference), match.group(0)

    if match := _END_OF_WEEK.search(text):
        days_to_friday = (WEEKDAYS["friday"] - reference.weekday()) % 7
        return _at_end_of_day(reference + timedelta(days=days_to_friday)), match.group(0)

    if match := _END_OF_MONTH.search(text):
        last_day = calendar.monthrange(reference.year, reference.month)[1]
        return _at_end_of_day(reference.replace(day=last_day)), match.group(0)

    if match := _BY_WEEKDAY.search(text):
        target = WEEKDAYS[match.group(1).lower()]
        days_ahead = (target - reference.weekday()) % 7
        if days_ahead == 0:  # "by Wednesday" written on a Wednesday means next week
            days_ahead = 7
        return _at_end_of_day(reference + timedelta(days=days_ahead)), match.group(0)

    if match := _BY_ORDINAL.search(text):
        day_of_month = int(match.group(1))
        if not 1 <= day_of_month <= 31:
            return None, None
        year, month = reference.year, reference.month
        if day_of_month < reference.day:  # already passed this month → next month
            month += 1
            if month == 13:
                month, year = 1, year + 1
        last_day = calendar.monthrange(year, month)[1]
        candidate = reference.replace(year=year, month=month, day=min(day_of_month, last_day))
        return _at_end_of_day(candidate), match.group(0)

    if match := _TOMORROW.search(text):
        return _at_end_of_day(reference + timedelta(days=1)), match.group(0)

    return None, None
