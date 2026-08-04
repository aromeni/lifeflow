"""Stage 11A Phase 4D — the live read-only transport guard.

Regression coverage for `scripts.stage11a_phase4d_live_readonly_guard`, the
one safeguard that stands directly between LifeFlow's real Google clients
and the real Google hosts during the single authorised live connection.
These tests prove the guard itself; the live rehearsal (fake-provider) and
the real live run separately prove it is actually installed.
"""

from __future__ import annotations

import httpx
import pytest
from scripts.stage11a_phase4d_live_readonly_guard import (
    CALENDAR_EVENTS_LIST,
    CALENDAR_GET_PRIMARY,
    GMAIL_GET_PROFILE,
    GMAIL_MESSAGES_LIST,
    TOKEN_EXCHANGE,
    TOKEN_REVOKE,
    LiveGuardBudgetExceededError,
    LiveGuardViolationError,
    LiveReadOnlyGuardTransport,
)

pytestmark = pytest.mark.asyncio


def _ok_transport() -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(200, json={}))


@pytest.mark.parametrize(
    "method,host,path",
    [
        TOKEN_EXCHANGE,
        TOKEN_REVOKE,
        GMAIL_GET_PROFILE,
        GMAIL_MESSAGES_LIST,
        CALENDAR_GET_PRIMARY,
        CALENDAR_EVENTS_LIST,
    ],
)
async def test_each_approved_operation_is_allowed_once(method: str, host: str, path: str) -> None:
    guard = LiveReadOnlyGuardTransport(_ok_transport())
    response = await guard.handle_async_request(httpx.Request(method, f"https://{host}{path}"))
    assert response.status_code == 200


@pytest.mark.parametrize(
    "method,host,path",
    [
        ("POST", GMAIL_GET_PROFILE[1], "/gmail/v1/users/me/drafts"),
        ("POST", CALENDAR_EVENTS_LIST[1], "/calendar/v3/calendars/primary/events"),
        ("PUT", CALENDAR_EVENTS_LIST[1], "/calendar/v3/calendars/primary/events/e1"),
        ("PATCH", CALENDAR_EVENTS_LIST[1], "/calendar/v3/calendars/primary/events/e1"),
        ("DELETE", CALENDAR_EVENTS_LIST[1], "/calendar/v3/calendars/primary/events/e1"),
        ("GET", GMAIL_GET_PROFILE[1], "/gmail/v1/users/me/messages/msg-1"),  # message content
        ("GET", GMAIL_GET_PROFILE[1], "/gmail/v1/users/me/messages/msg-1/attachments/a1"),
        ("GET", GMAIL_GET_PROFILE[1], "/gmail/v1/users/me/history"),  # history traversal
        ("POST", CALENDAR_EVENTS_LIST[1], "/calendar/v3/calendars/primary/events/watch"),
        ("POST", GMAIL_GET_PROFILE[1], "/batch/gmail/v1"),  # batch endpoint
        ("GET", "evil-mirror.example.net", "/gmail/v1/users/me/profile"),  # unapproved host
        ("GET", GMAIL_GET_PROFILE[1], "/gmail/v1/users/me/drafts"),  # unapproved Gmail path
    ],
)
async def test_every_unapproved_operation_is_refused_before_transmission(
    method: str, host: str, path: str
) -> None:
    def never_called(request: httpx.Request) -> httpx.Response:
        raise AssertionError("wrapped transport must not run for a refused operation")

    guard = LiveReadOnlyGuardTransport(httpx.MockTransport(never_called))
    with pytest.raises(LiveGuardViolationError):
        await guard.handle_async_request(httpx.Request(method, f"https://{host}{path}"))


async def test_call_budget_is_enforced_per_operation() -> None:
    guard = LiveReadOnlyGuardTransport(_ok_transport(), budget={GMAIL_MESSAGES_LIST: 1})
    method, host, path = GMAIL_MESSAGES_LIST
    request = httpx.Request(method, f"https://{host}{path}")
    first = await guard.handle_async_request(request)
    assert first.status_code == 200
    with pytest.raises(LiveGuardBudgetExceededError):
        await guard.handle_async_request(request)


async def test_default_budget_matches_the_governing_task_exactly() -> None:
    guard = LiveReadOnlyGuardTransport(_ok_transport())
    for method, host, path in [
        TOKEN_EXCHANGE,
        TOKEN_REVOKE,
        GMAIL_GET_PROFILE,
        GMAIL_MESSAGES_LIST,
        CALENDAR_GET_PRIMARY,
        CALENDAR_EVENTS_LIST,
    ]:
        request = httpx.Request(method, f"https://{host}{path}")
        await guard.handle_async_request(request)
        with pytest.raises(LiveGuardBudgetExceededError):
            await guard.handle_async_request(request)


async def test_no_environment_variable_can_select_an_unapproved_operation(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_API_ORIGIN_OVERRIDE", "https://gmail.googleapis.com")
    guard = LiveReadOnlyGuardTransport(
        httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError("must not run")))
    )
    with pytest.raises(LiveGuardViolationError):
        await guard.handle_async_request(
            httpx.Request("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages/x")
        )


async def test_a_redirect_to_an_unapproved_host_is_refused_on_the_second_hop() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == GMAIL_GET_PROFILE[1]:
            return httpx.Response(302, headers={"location": "https://evil-mirror.example.net/x"})
        raise AssertionError("must never be reached — the redirect hop must be blocked first")

    guard = LiveReadOnlyGuardTransport(httpx.MockTransport(handle))
    async with httpx.AsyncClient(transport=guard, follow_redirects=True) as client:
        with pytest.raises(LiveGuardViolationError):
            await client.get(f"https://{GMAIL_GET_PROFILE[1]}{GMAIL_GET_PROFILE[2]}")


async def test_content_free_metrics_report_only_method_and_path() -> None:
    guard = LiveReadOnlyGuardTransport(_ok_transport())
    await guard.handle_async_request(
        httpx.Request(
            GMAIL_GET_PROFILE[0], f"https://{GMAIL_GET_PROFILE[1]}{GMAIL_GET_PROFILE[2]}?secret=1"
        )
    )
    metrics = guard.content_free_metrics()
    assert metrics == {"GET /gmail/v1/users/me/profile": 1, **{k: 0 for k in _other_metric_keys()}}


def _other_metric_keys() -> list[str]:
    return [
        "POST /token",
        "POST /revoke",
        "GET /gmail/v1/users/me/messages",
        "GET /calendar/v3/calendars/primary",
        "GET /calendar/v3/calendars/primary/events",
    ]


async def test_guard_closes_the_wrapped_transport() -> None:
    closed = False

    class _Wrapped(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise AssertionError("not exercised in this test")

        async def aclose(self) -> None:
            nonlocal closed
            closed = True

    guard = LiveReadOnlyGuardTransport(_Wrapped())
    await guard.aclose()
    assert closed is True
