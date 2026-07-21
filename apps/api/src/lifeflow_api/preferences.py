"""Explicit user preferences — a closed, typed registry (ADR 0004 D44).

Only registry keys exist; each has its own strict value schema and a default
returned until the user sets it. Every write is explicit provenance and
audited (D46). Preferences shape display, timing, and ranking inputs only —
nothing here is ever consulted by the policy engine, executors, or approval
binding.
"""

import uuid
from datetime import datetime, time
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.audit import record_audit_event
from lifeflow_api.deps import CurrentUser, DbSession
from lifeflow_api.models import Preference, Provenance
from lifeflow_api.repositories import PreferenceRepository

router = APIRouter(prefix="/preferences")

BRIEFING_TIME_KEY = "briefing_time"
WORKING_HOURS_KEY = "working_hours"
BRIEF_SECTIONS_KEY = "brief_sections"
SCHEDULED_BRIEFS_ENABLED_KEY = "scheduled_briefs_enabled"

# Sections the user may hide. `needs_attention` is deliberately absent —
# high-priority items can never be configured out of sight (ADR 0004 D45).
# Written as literal strings (not BriefSectionKey members) so
# `brief_composition` can import this module without a cycle; a test pins
# these literals against the enum.
NEEDS_ATTENTION_SECTION = "needs_attention"
OPTIONAL_BRIEF_SECTIONS = (
    "today_upcoming",
    "waiting_for",
    "suggested_actions",
    "low_confidence_review",
)


def _parse_hhmm(value: str, *, label: str) -> str:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ValueError(f"{label} must be a 24-hour time written as HH:MM.")
    try:
        time.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label} must be a valid 24-hour time written as HH:MM.") from None
    return value


class BriefingTimeValue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str

    @field_validator("value")
    @classmethod
    def value_is_time(cls, value: str) -> str:
        return _parse_hhmm(value, label="Briefing time")


class WorkingHoursValue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    start: str
    end: str

    @field_validator("start")
    @classmethod
    def start_is_time(cls, value: str) -> str:
        return _parse_hhmm(value, label="Working-hours start")

    @field_validator("end")
    @classmethod
    def end_is_time(cls, value: str) -> str:
        return _parse_hhmm(value, label="Working-hours end")

    @model_validator(mode="after")
    def start_before_end(self) -> "WorkingHoursValue":
        if self.start >= self.end:
            raise ValueError("Working hours must start before they end.")
        return self


class BriefSectionsValue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sections: Annotated[list[str], Field(max_length=len(OPTIONAL_BRIEF_SECTIONS))]

    @field_validator("sections")
    @classmethod
    def sections_are_known_and_unique(cls, value: list[str]) -> list[str]:
        allowed = set(OPTIONAL_BRIEF_SECTIONS)
        unknown = [section for section in value if section not in allowed]
        if unknown:
            raise ValueError(
                "Brief sections may only contain: " + ", ".join(sorted(allowed)) + ". "
                "The 'Needs attention' section is always shown and cannot be configured."
            )
        if len(set(value)) != len(value):
            raise ValueError("Brief sections must be unique.")
        return value


class ScheduledBriefsEnabledValue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool


_DEFAULTS: dict[str, dict[str, Any]] = {
    BRIEFING_TIME_KEY: {"value": "07:30"},
    WORKING_HOURS_KEY: {"start": "09:00", "end": "17:30"},
    BRIEF_SECTIONS_KEY: {"sections": list(OPTIONAL_BRIEF_SECTIONS)},
    # Default off (ADR 0004 D50): an existing deployment must not suddenly
    # start scheduling briefs for every user just because briefing_time
    # already had a default.
    SCHEDULED_BRIEFS_ENABLED_KEY: {"enabled": False},
}
_VALIDATORS: dict[str, type[BaseModel]] = {
    BRIEFING_TIME_KEY: BriefingTimeValue,
    WORKING_HOURS_KEY: WorkingHoursValue,
    BRIEF_SECTIONS_KEY: BriefSectionsValue,
    SCHEDULED_BRIEFS_ENABLED_KEY: ScheduledBriefsEnabledValue,
}
PREFERENCE_KEYS = tuple(_DEFAULTS)


def validate_preference_value(key: str, value: dict[str, Any]) -> dict[str, Any]:
    """Validate a raw value against the key's schema; returns the canonical
    JSON shape. Raises KeyError for an unknown key, ValueError for a bad
    value (with a plain-language message)."""
    model = _VALIDATORS[key]
    try:
        return model.model_validate(value).model_dump(mode="json")
    except Exception as exc:  # pydantic ValidationError → plain message
        raise ValueError(_first_error_message(exc)) from exc


def _first_error_message(exc: Exception) -> str:
    errors = getattr(exc, "errors", None)
    if callable(errors):
        details = errors()
        if details:
            return str(details[0].get("msg", "Invalid value.")).removeprefix("Value error, ")
    return "Invalid value."


async def resolved_preferences(
    session: AsyncSession, user_id: uuid.UUID
) -> dict[str, dict[str, Any]]:
    """Every registry key resolved to its stored value or default."""
    stored = {p.key: p for p in await PreferenceRepository(session, user_id).list()}
    resolved: dict[str, dict[str, Any]] = {}
    for key, default in _DEFAULTS.items():
        row = stored.get(key)
        if row is None:
            resolved[key] = dict(default)
            continue
        try:
            resolved[key] = validate_preference_value(key, dict(row.value_json))
        except (ValueError, TypeError):
            # A stored value that no longer validates (schema evolution)
            # degrades to the default rather than failing the caller.
            resolved[key] = dict(default)
    return resolved


async def enabled_brief_sections(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    """The section keys the brief may display: the user's choice plus the
    never-hidden `needs_attention` (ADR 0004 D45)."""
    resolved = await resolved_preferences(session, user_id)
    chosen = set(resolved[BRIEF_SECTIONS_KEY]["sections"])
    return chosen | {NEEDS_ATTENTION_SECTION}


async def scheduled_briefs_enabled(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """Whether this user has explicitly opted into scheduled daily briefs
    (ADR 0004 D50). Consulted only by the Phase 2 dispatcher — never by the
    policy engine, executors, or approval binding (D46)."""
    resolved = await resolved_preferences(session, user_id)
    return bool(resolved[SCHEDULED_BRIEFS_ENABLED_KEY]["enabled"])


async def briefing_schedule(session: AsyncSession, user_id: uuid.UUID) -> str:
    """The user's configured `briefing_time` as `"HH:MM"`."""
    resolved = await resolved_preferences(session, user_id)
    return str(resolved[BRIEFING_TIME_KEY]["value"])


class PreferenceItem(BaseModel):
    key: str
    value: dict[str, Any]
    provenance: str
    is_default: bool
    updated_at: datetime | None


class PreferencesResponse(BaseModel):
    preferences: list[PreferenceItem]


class PreferenceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: dict[str, Any]


def _to_item(key: str, row: Preference | None, resolved_value: dict[str, Any]) -> PreferenceItem:
    return PreferenceItem(
        key=key,
        value=resolved_value,
        provenance=str(row.provenance) if row is not None else str(Provenance.explicit),
        is_default=row is None,
        updated_at=row.updated_at if row is not None else None,
    )


@router.get("", response_model=PreferencesResponse)
async def list_preferences(user: CurrentUser, session: DbSession) -> PreferencesResponse:
    stored = {p.key: p for p in await PreferenceRepository(session, user.id).list()}
    resolved = await resolved_preferences(session, user.id)
    return PreferencesResponse(
        preferences=[_to_item(key, stored.get(key), resolved[key]) for key in PREFERENCE_KEYS]
    )


@router.put("/{key}", response_model=PreferenceItem)
async def set_preference(
    key: str, body: PreferenceUpdateRequest, user: CurrentUser, session: DbSession
) -> PreferenceItem:
    if key not in _DEFAULTS:
        raise HTTPException(status_code=404, detail=f"Unknown preference: {key}")
    try:
        canonical = validate_preference_value(key, body.value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repository = PreferenceRepository(session, user.id)
    existing = await repository.get(key)
    if existing is None:
        existing = Preference(
            user_id=user.id,
            key=key,
            value_json=canonical,
            provenance=Provenance.explicit,
            confidence=None,
        )
        repository.add(existing)
    else:
        existing.value_json = canonical
        existing.provenance = Provenance.explicit
        existing.confidence = None
    record_audit_event(
        session,
        user_id=user.id,
        actor="user",
        event_type="preference.updated",
        entity_type="preference",
        entity_id=key,
        # Configuration values, not personal content — safe to audit whole.
        metadata={"key": key, "provenance": str(Provenance.explicit), "value": canonical},
    )
    await session.flush()
    await session.refresh(existing)
    return _to_item(key, existing, canonical)


__all__ = [
    "BRIEFING_TIME_KEY",
    "BRIEF_SECTIONS_KEY",
    "NEEDS_ATTENTION_SECTION",
    "OPTIONAL_BRIEF_SECTIONS",
    "PREFERENCE_KEYS",
    "SCHEDULED_BRIEFS_ENABLED_KEY",
    "WORKING_HOURS_KEY",
    "briefing_schedule",
    "enabled_brief_sections",
    "resolved_preferences",
    "router",
    "scheduled_briefs_enabled",
    "validate_preference_value",
]
