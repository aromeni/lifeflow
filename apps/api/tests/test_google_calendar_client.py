"""Stage 7: the narrow Calendar transport client (ADR 0003 D13).

`insert_event` always sends `sendUpdates=none` and is the only write this
client can perform — there is no `update`/`patch`/`delete` method at all
(threat model T23), proven structurally and by inspecting every call made.
"""

from datetime import UTC, datetime

import httpx
import pytest

from lifeflow_api.google.calendar_client import CalendarEventClient
from lifeflow_api.google.errors import GoogleSyncTokenExpiredError, GoogleTransientError
from lifeflow_api.metrics import REGISTRY


def _client(handler: httpx.MockTransport) -> CalendarEventClient:
    return CalendarEventClient(httpx.AsyncClient(transport=handler))


def test_client_exposes_no_update_patch_or_delete_method() -> None:
    """Structural proof, not just behavioural: the capability to modify or
    delete an existing event does not exist in this class at all."""
    public_methods = {name for name in dir(CalendarEventClient) if not name.startswith("_")}
    assert public_methods == {"list_events", "insert_event", "get_event"}


async def test_insert_event_always_sends_send_updates_none() -> None:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "id": "event-1",
                "summary": "Project sync",
                "start": {"dateTime": "2026-07-20T10:00:00+01:00"},
                "end": {"dateTime": "2026-07-20T10:30:00+01:00"},
                "attendees": [{"email": "dana@example.com"}],
            },
        )

    client = _client(httpx.MockTransport(handle))
    result = await client.insert_event(
        access_token="token",
        summary="Project sync",
        description="",
        location=None,
        starts_at=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 20, 10, 30, tzinfo=UTC),
        timezone="Europe/London",
        attendees=["dana@example.com"],
    )

    assert len(calls) == 1
    assert calls[0].method == "POST"
    assert calls[0].url.path == "/calendar/v3/calendars/primary/events"
    assert calls[0].url.params["sendUpdates"] == "none"
    assert result.event_id == "event-1"
    assert result.attendees == ("dana@example.com",)


async def test_sync_token_expired_raises_typed_error_on_410() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(410, json={})

    client = _client(httpx.MockTransport(handle))
    with pytest.raises(GoogleSyncTokenExpiredError):
        await client.list_events(
            access_token="token",
            time_min=None,
            time_max=None,
            sync_token="stale-token",
            page_token=None,
        )


async def test_list_events_uses_time_bounds_only_on_first_sync() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert "timeMin" in request.url.params
        assert "timeMax" in request.url.params
        assert "syncToken" not in request.url.params
        return httpx.Response(200, json={"items": [], "nextSyncToken": "fresh-token"})

    client = _client(httpx.MockTransport(handle))
    page = await client.list_events(
        access_token="token",
        time_min=datetime(2026, 7, 1, tzinfo=UTC),
        time_max=datetime(2026, 8, 1, tzinfo=UTC),
        sync_token=None,
        page_token=None,
    )
    assert page.next_sync_token == "fresh-token"


async def test_transient_error_on_5xx() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    client = _client(httpx.MockTransport(handle))
    with pytest.raises(GoogleTransientError):
        await client.list_events(
            access_token="token",
            time_min=None,
            time_max=None,
            sync_token="token-1",
            page_token=None,
        )


async def test_list_events_emits_a_success_request_metric() -> None:
    """Stage 9 Delivery Phase 5 (§14/§18 item 36): Calendar's ingestion read
    now emits the same metric its write/verification calls already did."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [], "nextSyncToken": "t"})

    client = _client(httpx.MockTransport(handle))
    before = (
        REGISTRY.get_sample_value(
            "lifeflow_provider_requests_total",
            {"provider": "calendar", "operation": "list_events", "outcome": "success"},
        )
        or 0.0
    )

    await client.list_events(
        access_token="token", time_min=None, time_max=None, sync_token="t", page_token=None
    )

    after = REGISTRY.get_sample_value(
        "lifeflow_provider_requests_total",
        {"provider": "calendar", "operation": "list_events", "outcome": "success"},
    )
    assert after == before + 1


async def test_list_events_sync_token_expiry_is_a_distinct_outcome_not_unknown_error() -> None:
    """A 410 syncToken-expired response is an expected, routine resync
    trigger — it must not pollute the `unknown_error` bucket, which is
    reserved for genuinely unclassified failures."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(410, json={})

    client = _client(httpx.MockTransport(handle))
    before = (
        REGISTRY.get_sample_value(
            "lifeflow_provider_requests_total",
            {
                "provider": "calendar",
                "operation": "list_events",
                "outcome": "sync_token_expired",
            },
        )
        or 0.0
    )

    with pytest.raises(GoogleSyncTokenExpiredError):
        await client.list_events(
            access_token="token",
            time_min=None,
            time_max=None,
            sync_token="stale",
            page_token=None,
        )

    after = REGISTRY.get_sample_value(
        "lifeflow_provider_requests_total",
        {"provider": "calendar", "operation": "list_events", "outcome": "sync_token_expired"},
    )
    assert after == before + 1
