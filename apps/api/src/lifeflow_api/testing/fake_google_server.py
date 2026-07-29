"""A fake Gmail/Calendar server for Stage 9 Delivery Phase 5's Playwright
resilience journeys (§20).

This is deliberately its OWN small standalone ASGI app — never imported by
`lifeflow_api.main`, never sharing a process with the real API — so it can
never weaken the production application's abstractions or route surface.
It is reachable only when the real API is separately configured (via
`E2E_TEST_CONTROLS_ENABLED=true` and `GOOGLE_API_ORIGIN_OVERRIDE`, both
refused in production, see `main.py`) to redirect its Google clients here
instead of to the real Google hosts.

Safety properties:
  * Refuses to import (raises `SystemExit` at module load, before uvicorn
    can construct `app`) unless `LIFEFLOW_E2E_FAKE_GOOGLE=1` is set — the
    same explicit-marker convention `scripts/e2e_deletion_support.py`
    already uses for its own test-only DB access.
  * Never talks to a real Google host, never accepts or validates a real
    OAuth/bearer credential (the `Authorization` header, if present, is
    ignored entirely) — it is pure in-memory state.
  * Never exposes anything beyond synthetic object counts and call counts
    (`GET /__control__/state`) — no tokens, no user data, nothing it wasn't
    itself handed by the very same test run.
  * The fault-injection vocabulary (`Scenario`) is a closed enum; the
    targetable operation vocabulary (`_OPERATIONS`) is a closed set. Both
    `POST /__control__/scenario` inputs are validated against them — an
    unrecognised value is rejected (422), never silently accepted.

Run standalone:
    LIFEFLOW_E2E_FAKE_GOOGLE=1 uv run uvicorn --app-dir src \\
        lifeflow_api.testing.fake_google_server:app --port 8098
"""

from __future__ import annotations

import asyncio
import os
import uuid
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

if os.environ.get("LIFEFLOW_E2E_FAKE_GOOGLE") != "1":
    raise SystemExit(
        "refusing to start: LIFEFLOW_E2E_FAKE_GOOGLE=1 is required "
        "(this is test-only fault-injection infrastructure, never a real Google host)"
    )


class Scenario(StrEnum):
    """The complete, closed set of fault-injection behaviours. Adding a new
    one means adding it here first, never passing an ad hoc string."""

    healthy = "healthy"
    transient_then_recover = "transient_then_recover"
    permanent_failure = "permanent_failure"
    auth_expired = "auth_expired"
    hang_on_write = "hang_on_write"


_OPERATIONS = frozenset(
    {
        "gmail_list_messages",
        "gmail_get_message",
        "gmail_list_history",
        "gmail_get_current_history_id",
        "gmail_create_draft",
        "gmail_get_draft",
        "calendar_list_events",
        "calendar_insert_event",
        "calendar_get_event",
    }
)

# How long `hang_on_write` withholds its response — must comfortably exceed
# whatever GOOGLE_WRITE_TIMEOUT_SECONDS the e2e API process under test is
# configured with, so the client always gives up first.
_HANG_SECONDS = 4.0
_DISCONNECT_POLL_INTERVAL = 0.25


async def _sleep_or_bail_if_disconnected(request: Request, seconds: float) -> None:
    """Withholds a response for `seconds`, but polls for the client having
    already disconnected (as it always will here, once the real client's
    own short write-timeout fires) and returns as soon as that happens —
    never wastes time or leaves a request outstanding purely to satisfy a
    peer that already gave up, mirroring how a real server socket write
    would fail fast against a closed connection."""
    elapsed = 0.0
    while elapsed < seconds:
        if await request.is_disconnected():
            return
        await asyncio.sleep(_DISCONNECT_POLL_INTERVAL)
        elapsed += _DISCONNECT_POLL_INTERVAL


class _ScenarioState(BaseModel):
    scenario: Scenario = Scenario.healthy
    fail_count: int = 0


class _ScenarioRequest(BaseModel):
    operation: str
    scenario: Scenario
    fail_count: int = 0


_scenarios: dict[str, _ScenarioState] = {}
_call_counts: dict[str, int] = {}
_drafts: dict[str, dict[str, Any]] = {}
_events: dict[str, dict[str, Any]] = {}
_history_id = 1000


def _reset() -> None:
    global _history_id
    _scenarios.clear()
    _call_counts.clear()
    _drafts.clear()
    _events.clear()
    _history_id = 1000


async def _gate(operation: str) -> None:
    """Applies whatever scenario is currently configured for `operation`,
    before the route's own handler does anything else. Raises the same way
    a real transient/permanent Google failure would (an HTTP error status,
    never a raw exception) so the real `httpx`-based clients classify it
    exactly as they would a real outage."""
    assert operation in _OPERATIONS  # noqa: S101 -- closed vocabulary, programmer error otherwise
    _call_counts[operation] = _call_counts.get(operation, 0) + 1
    state = _scenarios.get(operation, _ScenarioState())
    if state.scenario == Scenario.healthy:
        return
    if state.scenario == Scenario.permanent_failure:
        raise HTTPException(status_code=400, detail="permanent_failure (fake)")
    if state.scenario == Scenario.auth_expired:
        raise HTTPException(status_code=401, detail="auth_expired (fake)")
    if state.scenario == Scenario.transient_then_recover:
        if _call_counts[operation] <= state.fail_count:
            raise HTTPException(status_code=503, detail="transient_then_recover (fake)")
        return
    # hang_on_write is applied by the write routes themselves, after they've
    # recorded the object — it needs to hang *after* creating the side
    # effect, not before, to simulate "the write actually happened".


app = FastAPI(title="LifeFlow fake Google server (test-only)")


# --- control routes ----------------------------------------------------------


@app.post("/__control__/reset")
async def control_reset() -> dict[str, str]:
    _reset()
    return {"status": "reset"}


@app.post("/__control__/scenario")
async def control_scenario(body: _ScenarioRequest) -> dict[str, str]:
    if body.operation not in _OPERATIONS:
        raise HTTPException(status_code=422, detail=f"unknown operation {body.operation!r}")
    _scenarios[body.operation] = _ScenarioState(scenario=body.scenario, fail_count=body.fail_count)
    _call_counts[body.operation] = 0
    return {"status": "set"}


@app.get("/__control__/state")
async def control_state() -> dict[str, Any]:
    return {
        "draft_count": len(_drafts),
        "event_count": len(_events),
        "call_counts": dict(_call_counts),
    }


# --- Gmail --------------------------------------------------------------------


@app.get("/gmail/v1/users/me/messages")
async def gmail_list_messages() -> dict[str, Any]:
    await _gate("gmail_list_messages")
    return {
        "messages": [
            {"id": "fake-msg-1", "threadId": "fake-thread-1"},
            {"id": "fake-msg-2", "threadId": "fake-thread-2"},
        ]
    }


@app.get("/gmail/v1/users/me/messages/{message_id}")
async def gmail_get_message(message_id: str) -> dict[str, Any]:
    await _gate("gmail_get_message")
    return {
        "id": message_id,
        "threadId": f"thread-for-{message_id}",
        "snippet": "A fake message body snippet.",
        "internalDate": "1700000000000",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.invalid"},
                {"name": "To", "value": "recipient@example.invalid"},
                {"name": "Subject", "value": f"Fake subject for {message_id}"},
            ]
        },
    }


@app.get("/gmail/v1/users/me/history")
async def gmail_list_history(startHistoryId: str) -> dict[str, Any]:  # noqa: N803 -- Google's own query param casing
    await _gate("gmail_list_history")
    return {"history": [], "historyId": startHistoryId}


@app.get("/gmail/v1/users/me/profile")
async def gmail_get_current_history_id() -> dict[str, Any]:
    await _gate("gmail_get_current_history_id")
    global _history_id
    _history_id += 1
    return {"historyId": str(_history_id)}


@app.post("/gmail/v1/users/me/drafts")
async def gmail_create_draft(request: Request) -> dict[str, Any]:
    payload = await request.json()
    draft_id = f"fake-draft-{uuid.uuid4()}"
    message_id = f"fake-message-{uuid.uuid4()}"
    thread_id = payload.get("message", {}).get("threadId") or f"fake-thread-{uuid.uuid4()}"
    raw = payload.get("message", {}).get("raw", "")
    # The write itself always succeeds and is recorded immediately — a
    # `hang_on_write` scenario withholds the *response*, never the side
    # effect, which is exactly what makes an uncertain outcome uncertain.
    _drafts[draft_id] = {
        "id": draft_id,
        "message_id": message_id,
        "thread_id": thread_id,
        "raw": raw,
    }
    state = _scenarios.get("gmail_create_draft", _ScenarioState())
    _call_counts["gmail_create_draft"] = _call_counts.get("gmail_create_draft", 0) + 1
    if state.scenario == Scenario.permanent_failure:
        del _drafts[draft_id]
        raise HTTPException(status_code=400, detail="permanent_failure (fake)")
    if state.scenario == Scenario.hang_on_write:
        await _sleep_or_bail_if_disconnected(request, _HANG_SECONDS)
    return {"id": draft_id, "message": {"id": message_id, "threadId": thread_id}}


@app.get("/gmail/v1/users/me/drafts/{draft_id}")
async def gmail_get_draft(draft_id: str) -> dict[str, Any]:
    await _gate("gmail_get_draft")
    draft = _drafts.get(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found (fake)")
    return {
        "id": draft["id"],
        "message": {"id": draft["message_id"], "threadId": draft["thread_id"], "raw": draft["raw"]},
    }


# --- Calendar -------------------------------------------------------------


@app.get("/calendar/v3/calendars/primary/events")
async def calendar_list_events() -> dict[str, Any]:
    await _gate("calendar_list_events")
    return {"items": [], "nextSyncToken": f"fake-sync-token-{uuid.uuid4()}"}


@app.post("/calendar/v3/calendars/primary/events")
async def calendar_insert_event(request: Request) -> dict[str, Any]:
    payload = await request.json()
    event_id = f"fake-event-{uuid.uuid4()}"
    _events[event_id] = {
        "id": event_id,
        "summary": payload.get("summary", ""),
        "start": payload.get("start", {}),
        "end": payload.get("end", {}),
        "attendees": payload.get("attendees", []),
    }
    state = _scenarios.get("calendar_insert_event", _ScenarioState())
    _call_counts["calendar_insert_event"] = _call_counts.get("calendar_insert_event", 0) + 1
    if state.scenario == Scenario.permanent_failure:
        del _events[event_id]
        raise HTTPException(status_code=400, detail="permanent_failure (fake)")
    if state.scenario == Scenario.hang_on_write:
        await _sleep_or_bail_if_disconnected(request, _HANG_SECONDS)
    return _events[event_id]


@app.get("/calendar/v3/calendars/primary/events/{event_id}")
async def calendar_get_event(event_id: str) -> dict[str, Any]:
    await _gate("calendar_get_event")
    event = _events.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found (fake)")
    return {**event, "status": "confirmed", "organizer": {"email": "organiser@example.invalid"}}


__all__ = ["Scenario", "app"]
