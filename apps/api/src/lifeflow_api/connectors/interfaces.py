"""Connector contracts (ADR 0001 D6, naming-conventions.md).

DTOs are vendor-neutral: a Gmail message and a synthetic message normalise to
the same `EmailMessage`. All datetimes are timezone-aware; adapters must
return items in a deterministic order (occurred/starts ascending, then id).

Content from any connector is UNTRUSTED DATA (threat model T3) — nothing in
these DTOs is ever treated as an instruction.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable


class EmailFolder(StrEnum):
    inbox = "inbox"
    sent = "sent"


@dataclass(frozen=True)
class EmailMessage:
    external_id: str
    folder: EmailFolder
    sender_name: str
    sender_email: str
    recipients: tuple[str, ...]
    subject: str
    body_text: str
    sent_at: datetime  # timezone-aware
    thread_id: str | None = None
    # True when the source message carried a List-Unsubscribe header — the
    # RFC-standard marker of bulk/marketing mail (ADR 0003 D42). Bulk mail
    # never yields actionable signals; this generalises the heuristic
    # sender/keyword rules without any domain blocklist.
    list_unsubscribe: bool = False


@dataclass(frozen=True)
class CalendarEvent:
    external_id: str
    title: str
    organiser_email: str
    starts_at: datetime  # timezone-aware
    ends_at: datetime  # timezone-aware
    all_day: bool = False
    location: str | None = None
    description: str = ""
    attendees: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TaskItem:
    external_id: str
    title: str
    notes: str = ""
    due_at: datetime | None = None
    completed: bool = False


@runtime_checkable
class EmailConnector(Protocol):
    async def fetch_recent(self, *, since: datetime, until: datetime) -> list[EmailMessage]: ...


@runtime_checkable
class CalendarConnector(Protocol):
    async def fetch_events(self, *, since: datetime, until: datetime) -> list[CalendarEvent]: ...


@runtime_checkable
class TaskConnector(Protocol):
    async def fetch_tasks(self) -> list[TaskItem]: ...
