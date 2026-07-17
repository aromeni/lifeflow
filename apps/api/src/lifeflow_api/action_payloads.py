"""Strict action payloads and canonical approval hashing.

Every field an executor can consume is required in these schemas, including
explicit ``null`` values. Approval therefore binds to the complete typed
input; executors cannot add hidden defaults after the user reviews it.

Datetime canonicalisation binds the REPRESENTATION the user saw, not the
instant: UTC spellings ("Z" vs "+00:00") normalise identically, but the same
instant written with a different non-zero offset ("+01:00") hashes
differently by design — an approval covers exactly what was displayed.
"""

import hashlib
import json
import re
from datetime import datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from lifeflow_api.models import ActionType


class ActionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


# FastAPI parses JSON before invoking Pydantic, so ISO date-time strings arrive
# through the Python-object validation path. Permit that one JSON-native
# conversion while every other executor field remains strict.
JsonAwareDatetime = Annotated[AwareDatetime, Field(strict=False)]


def _reject_non_iso_datetime(value: Any) -> Any:
    if value is not None and not isinstance(value, str | datetime):
        raise ValueError("Date-time fields must be ISO strings or datetime values.")
    return value


EMAIL_ADDRESS_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def _validate_addresses(addresses: list[str], *, label: str) -> list[str]:
    """Validate syntax without rejecting reserved, non-routable demo domains."""

    if any(not EMAIL_ADDRESS_PATTERN.fullmatch(address) for address in addresses):
        raise ValueError(f"{label} must contain valid email addresses.")
    normalised = [address.lower() for address in addresses]
    if len(normalised) != len(set(normalised)):
        raise ValueError(f"{label} must be unique.")
    return addresses


class TaskCreatePayload(ActionPayload):
    title: str = Field(min_length=1, max_length=200)
    notes: str = Field(max_length=2_000)
    due_at: JsonAwareDatetime | None

    @field_validator("due_at", mode="before")
    @classmethod
    def due_at_is_iso_datetime(cls, value: Any) -> Any:
        return _reject_non_iso_datetime(value)


class GmailDraftCreatePayload(ActionPayload):
    to: list[str] = Field(min_length=1, max_length=10)
    subject: str = Field(min_length=1, max_length=250)
    body: str = Field(min_length=1, max_length=10_000)
    thread_id: str | None = Field(max_length=512)

    @field_validator("to")
    @classmethod
    def recipients_are_valid(cls, value: list[str]) -> list[str]:
        return _validate_addresses(value, label="Draft recipients")


class CalendarEventCreatePayload(ActionPayload):
    title: str = Field(min_length=1, max_length=250)
    starts_at: JsonAwareDatetime
    ends_at: JsonAwareDatetime
    timezone: str = Field(min_length=1, max_length=64)
    location: str | None = Field(max_length=500)
    description: str = Field(max_length=5_000)
    attendees: list[str] = Field(min_length=1, max_length=50)

    @field_validator("starts_at", "ends_at", mode="before")
    @classmethod
    def event_times_are_iso_datetimes(cls, value: Any) -> Any:
        return _reject_non_iso_datetime(value)

    @field_validator("timezone")
    @classmethod
    def timezone_exists(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Calendar timezone is not recognised.") from exc
        return value

    @field_validator("attendees")
    @classmethod
    def attendees_are_valid(cls, value: list[str]) -> list[str]:
        return _validate_addresses(value, label="Calendar attendees")

    @model_validator(mode="after")
    def ends_after_start(self) -> "CalendarEventCreatePayload":
        if self.ends_at <= self.starts_at:
            raise ValueError("Calendar event must end after it starts.")
        return self


type TypedActionPayload = TaskCreatePayload | GmailDraftCreatePayload | CalendarEventCreatePayload

PAYLOAD_MODELS: dict[ActionType, type[ActionPayload]] = {
    ActionType.create_task: TaskCreatePayload,
    ActionType.create_gmail_draft: GmailDraftCreatePayload,
    ActionType.create_calendar_event: CalendarEventCreatePayload,
}


def parse_action_payload(
    action_type: ActionType | str,
    payload: dict[str, Any] | TypedActionPayload,
) -> TypedActionPayload:
    """Validate a payload against the application-owned action type."""

    typed_action = ActionType(action_type)
    model = PAYLOAD_MODELS[typed_action]
    raw = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    parsed = model.model_validate_json(
        json.dumps(raw, ensure_ascii=False, separators=(",", ":"), default=str)
    )
    if not isinstance(
        parsed,
        TaskCreatePayload | GmailDraftCreatePayload | CalendarEventCreatePayload,
    ):
        raise TypeError("Unsupported action payload model.")
    return parsed


def canonical_payload(
    action_type: ActionType | str,
    payload: dict[str, Any] | TypedActionPayload,
) -> dict[str, Any]:
    """Return the complete JSON-safe payload after type normalisation."""

    return parse_action_payload(action_type, payload).model_dump(mode="json")


def canonical_action_bytes(
    action_type: ActionType | str,
    payload: dict[str, Any] | TypedActionPayload,
) -> bytes:
    document = {
        "action_type": ActionType(action_type).value,
        "payload": canonical_payload(action_type, payload),
    }
    return json.dumps(
        document,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def action_payload_hash(
    action_type: ActionType | str,
    payload: dict[str, Any] | TypedActionPayload,
) -> str:
    return hashlib.sha256(canonical_action_bytes(action_type, payload)).hexdigest()


def approval_binding_hash(
    action_type: ActionType | str,
    payload: dict[str, Any] | TypedActionPayload,
    proposal_version: int,
) -> str:
    """Bind approval to action type, canonical payload, and proposal version."""

    if proposal_version < 1:
        raise ValueError("Proposal version must be positive.")
    digest = hashlib.sha256()
    digest.update(canonical_action_bytes(action_type, payload))
    digest.update(b"\x00version\x00")
    digest.update(str(proposal_version).encode("ascii"))
    return digest.hexdigest()


def effective_payload_deadline(payload: TypedActionPayload) -> datetime | None:
    if isinstance(payload, TaskCreatePayload):
        return payload.due_at
    if isinstance(payload, CalendarEventCreatePayload):
        return payload.starts_at
    return None


__all__ = [
    "PAYLOAD_MODELS",
    "ActionPayload",
    "CalendarEventCreatePayload",
    "GmailDraftCreatePayload",
    "TaskCreatePayload",
    "TypedActionPayload",
    "action_payload_hash",
    "approval_binding_hash",
    "canonical_action_bytes",
    "canonical_payload",
    "effective_payload_deadline",
    "parse_action_payload",
]
