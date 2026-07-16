from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from lifeflow_api.deadline_phrases import parse_due_phrase

LONDON = ZoneInfo("Europe/London")
# Tuesday 14 July 2026, 09:14 BST
REF = datetime(2026, 7, 14, 9, 14, tzinfo=LONDON)


def date_of(text: str) -> str | None:
    due, _ = parse_due_phrase(text, reference=REF)
    return due.astimezone(LONDON).strftime("%Y-%m-%d") if due else None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("confirm the terms by Wednesday", "2026-07-15"),
        ("please reply by Friday", "2026-07-17"),
        ("circulate before Thursday morning", "2026-07-16"),
        ("upload them by the 30th", "2026-07-30"),
        ("by the 5th please", "2026-08-05"),  # 5th already passed → next month
        ("book before the end of the month", "2026-07-31"),
        ("send it by end of week", "2026-07-17"),
        ("finish by end of day", "2026-07-14"),
        ("get it done by tomorrow", "2026-07-15"),
        ("by Tuesday at the latest", "2026-07-21"),  # written on a Tuesday → next week
        ("no deadline mentioned here", None),
        ("meeting at 3pm", None),
    ],
)
def test_phrase_parsing(text: str, expected: str | None) -> None:
    assert date_of(text) == expected


def test_deadlines_resolve_to_end_of_day_utc() -> None:
    due, phrase = parse_due_phrase("by Wednesday", reference=REF)
    assert phrase == "by Wednesday"
    assert due is not None
    # 23:59 BST on 15 July = 22:59 UTC
    assert due.strftime("%Y-%m-%d %H:%M %Z") == "2026-07-15 22:59 UTC"


def test_out_of_range_ordinal_is_ignored() -> None:
    assert date_of("by the 45th") is None
