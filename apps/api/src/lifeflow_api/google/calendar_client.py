"""Narrow Calendar transport client (ADR 0003 D13, D40).

Exactly three methods exist: `list_events` (read, cursor-aware),
`insert_event` (the one write), and `get_event` (a single-event read used
only to independently verify what Calendar actually stored after a create —
the Calendar analogue of Gmail's `get_draft` verification, D17/D40).
`insert_event` always sends `sendUpdates=none` — hard-coded, not a
caller-supplied parameter — so no attendee is ever notified and no other
calendar is modified (threat model T23). There is no
`update`/`patch`/`delete` method and no generic `request()` passthrough;
only `events.insert` can ever write.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from lifeflow_api.google.errors import (
    GoogleApiError,
    GoogleAuthError,
    GoogleClientError,
    GoogleSyncTokenExpiredError,
    GoogleTransientError,
)

_BASE_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
_ALLOWED_WRITE_PARAMS = {"sendUpdates": "none"}


@dataclass(frozen=True)
class CalendarEventSummary:
    id: str
    summary: str
    start: str
    end: str
    attendees: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class CalendarEventsPage:
    events: tuple[CalendarEventSummary, ...]
    next_page_token: str | None
    next_sync_token: str | None


@dataclass(frozen=True)
class CalendarEventResult:
    event_id: str
    summary: str
    start: str
    end: str
    attendees: tuple[str, ...]


@dataclass(frozen=True)
class CalendarEventRecord:
    """The independently re-fetched, authoritative state of one stored
    event (D40) — everything the executor needs to verify a create against
    the approved payload, and nothing more."""

    event_id: str
    summary: str
    start: str
    end: str
    attendees: tuple[str, ...]
    status: str
    organiser_email: str | None


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def _get(http: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
    """Every read goes through this so a raw transport failure — no response
    ever received, e.g. a timeout or a dropped connection — is classified as
    `GoogleTransientError` (→ `uncertain`) immediately, the same way a 5xx
    response already is (independent-review blocker #5). `_raise_for_error`
    alone cannot catch this: it only ever runs once a response exists."""
    try:
        return await http.get(url, **kwargs)
    except httpx.HTTPError as exc:
        raise GoogleTransientError(
            f"Calendar API request failed before a response was received ({type(exc).__name__})."
        ) from exc


async def _post(http: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
    try:
        return await http.post(url, **kwargs)
    except httpx.HTTPError as exc:
        raise GoogleTransientError(
            f"Calendar API request failed before a response was received ({type(exc).__name__})."
        ) from exc


def _raise_for_error(response: httpx.Response) -> None:
    if response.status_code in (200, 201):
        return
    if response.status_code in (401, 403):
        raise GoogleAuthError(
            f"Calendar API rejected the access token (HTTP {response.status_code})."
        )
    if response.status_code in (429, 500, 502, 503, 504):
        raise GoogleTransientError(f"Calendar API returned HTTP {response.status_code}.")
    raise GoogleClientError(
        f"Calendar API returned HTTP {response.status_code}.", status_code=response.status_code
    )


class CalendarEventClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        write_timeout: httpx.Timeout | None = None,
    ) -> None:
        self._http = http_client
        # Stage 9 Delivery Phase 5: see `GmailDraftClient.__init__` — the same
        # longer, separately-configured write-read budget applies here.
        self._write_timeout = write_timeout

    async def list_events(
        self,
        *,
        access_token: str,
        time_min: datetime | None,
        time_max: datetime | None,
        sync_token: str | None,
        page_token: str | None,
        max_results: int = 100,
    ) -> CalendarEventsPage:
        """Raises GoogleSyncTokenExpiredError on HTTP 410 (invalid
        syncToken) — the connector must fall back to a full bounded resync
        with fresh time bounds (ADR 0003 D21)."""
        params: dict[str, Any] = {"maxResults": max_results, "singleEvents": True}
        if page_token:
            params["pageToken"] = page_token
        elif sync_token:
            params["syncToken"] = sync_token
        else:
            if time_min:
                params["timeMin"] = time_min.isoformat()
            if time_max:
                params["timeMax"] = time_max.isoformat()
        response = await _get(self._http, _BASE_URL, params=params, headers=_headers(access_token))
        if response.status_code == 410:
            raise GoogleSyncTokenExpiredError("Calendar syncToken is invalid.")
        _raise_for_error(response)
        body = response.json()
        events = tuple(
            CalendarEventSummary(
                id=item["id"],
                summary=item.get("summary", ""),
                start=_event_time(item.get("start", {})),
                end=_event_time(item.get("end", {})),
                attendees=tuple(a["email"] for a in item.get("attendees", [])),
                status=item.get("status", "confirmed"),
            )
            for item in body.get("items", [])
        )
        return CalendarEventsPage(
            events=events,
            next_page_token=body.get("nextPageToken"),
            next_sync_token=body.get("nextSyncToken"),
        )

    async def insert_event(
        self,
        *,
        access_token: str,
        summary: str,
        description: str,
        location: str | None,
        starts_at: datetime,
        ends_at: datetime,
        timezone: str,
        attendees: list[str],
    ) -> CalendarEventResult:
        """The one write this client can perform. `sendUpdates=none` is
        hard-coded — never notifies guests, never modifies another
        calendar."""
        if _ALLOWED_WRITE_PARAMS["sendUpdates"] != "none":  # pragma: no cover -- defensive
            raise GoogleApiError("sendUpdates must remain 'none'.")
        body: dict[str, Any] = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": starts_at.isoformat(), "timeZone": timezone},
            "end": {"dateTime": ends_at.isoformat(), "timeZone": timezone},
            "attendees": [{"email": address} for address in attendees],
        }
        if location:
            body["location"] = location
        extra: dict[str, Any] = (
            {"timeout": self._write_timeout} if self._write_timeout is not None else {}
        )
        response = await _post(
            self._http,
            _BASE_URL,
            params={"sendUpdates": "none"},
            json=body,
            headers=_headers(access_token),
            **extra,
        )
        _raise_for_error(response)
        result = response.json()
        return CalendarEventResult(
            event_id=result["id"],
            summary=result.get("summary", summary),
            start=_event_time(result.get("start", {})),
            end=_event_time(result.get("end", {})),
            attendees=tuple(a["email"] for a in result.get("attendees", [])),
        )

    async def get_event(self, *, access_token: str, event_id: str) -> CalendarEventRecord:
        """Read back one stored event so a create can be verified against
        what Calendar actually holds, not against `insert_event`'s own
        response (D40). Read-only; the write surface is unchanged."""
        response = await _get(self._http, f"{_BASE_URL}/{event_id}", headers=_headers(access_token))
        _raise_for_error(response)
        body = response.json()
        organiser = body.get("organizer") or {}
        return CalendarEventRecord(
            event_id=body["id"],
            summary=body.get("summary", ""),
            start=_event_time(body.get("start", {})),
            end=_event_time(body.get("end", {})),
            attendees=tuple(a["email"] for a in body.get("attendees", [])),
            status=body.get("status", "confirmed"),
            organiser_email=organiser.get("email"),
        )


def _event_time(value: dict[str, Any]) -> str:
    return str(value.get("dateTime") or value.get("date") or "")


__all__ = [
    "CalendarEventClient",
    "CalendarEventRecord",
    "CalendarEventResult",
    "CalendarEventSummary",
    "CalendarEventsPage",
]
