"""Synthetic adapters: the demo-mode implementations of the connector
contracts (ADR 0001 D6). They read the fictional dataset and materialise
day-offsets against an anchor date in the demo timezone, so the demo always
looks current while remaining fully deterministic for a fixed anchor.
"""

import json
from datetime import date, datetime, time, timedelta
from importlib import resources
from zoneinfo import ZoneInfo

from lifeflow_api.connectors.interfaces import CalendarEvent, EmailFolder, EmailMessage

DEMO_TIMEZONE = ZoneInfo("Europe/London")
DATASET_VERSION = "v1"


def _load_dataset(filename: str, version: str = DATASET_VERSION) -> list[dict]:  # type: ignore[type-arg]
    package = resources.files("lifeflow_api.demo.data").joinpath(version)
    data: list[dict] = json.loads(package.joinpath(filename).read_text("utf-8"))  # type: ignore[type-arg]
    return data


def _materialise(anchor: date, day_offset: int, hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    local = datetime.combine(anchor + timedelta(days=day_offset), time(hour, minute))
    return local.replace(tzinfo=DEMO_TIMEZONE)


class SyntheticEmailConnector:
    """EmailConnector adapter over the fictional dataset."""

    def __init__(self, anchor: date, dataset_version: str = DATASET_VERSION) -> None:
        self._anchor = anchor
        self._version = dataset_version

    async def fetch_recent(self, *, since: datetime, until: datetime) -> list[EmailMessage]:
        messages = []
        for row in _load_dataset("emails.json", self._version):
            sent_at = _materialise(self._anchor, row["day_offset"], row["time"])
            if not (since <= sent_at <= until):
                continue
            messages.append(
                EmailMessage(
                    external_id=row["id"],
                    folder=EmailFolder(row["folder"]),
                    sender_name=row["from_name"],
                    sender_email=row["from_email"],
                    recipients=tuple(row["to"]),
                    subject=row["subject"],
                    body_text=row["body"],
                    sent_at=sent_at,
                    thread_id=row.get("thread_id"),
                )
            )
        return sorted(messages, key=lambda m: (m.sent_at, m.external_id))


class SyntheticCalendarConnector:
    """CalendarConnector adapter over the fictional dataset."""

    def __init__(self, anchor: date, dataset_version: str = DATASET_VERSION) -> None:
        self._anchor = anchor
        self._version = dataset_version

    async def fetch_events(self, *, since: datetime, until: datetime) -> list[CalendarEvent]:
        events = []
        for row in _load_dataset("events.json", self._version):
            if row.get("all_day"):
                starts = _materialise(self._anchor, row["day_offset"], "00:00")
                ends = starts + timedelta(days=1)
            else:
                starts = _materialise(self._anchor, row["day_offset"], row["start_time"])
                ends = _materialise(self._anchor, row["day_offset"], row["end_time"])
            if not (since <= starts <= until):
                continue
            events.append(
                CalendarEvent(
                    external_id=row["id"],
                    title=row["title"],
                    organiser_email=row["organiser"],
                    starts_at=starts,
                    ends_at=ends,
                    all_day=bool(row.get("all_day", False)),
                    location=row.get("location"),
                    description=row.get("description", ""),
                    attendees=tuple(row.get("attendees", ())),
                )
            )
        return sorted(events, key=lambda e: (e.starts_at, e.external_id))
