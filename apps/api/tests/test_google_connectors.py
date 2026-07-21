"""Stage 7: GoogleEmailConnector / GoogleCalendarConnector (ADR 0003 D21).

Both implement the existing EmailConnector/CalendarConnector protocols
unchanged. These tests cover cursor-based incremental sync, the fallback to
a full bounded resync when Gmail's historyId (404) or Calendar's syncToken
(410) has expired, and cursor safety under pagination bounds (Stage 7
remediation, independent-review blocker #3): a page bound reached while a
`nextPageToken` remains must never advance the committed cursor, must
persist a resumable continuation, and a later sync must resume from it
rather than skip or re-import.
"""

from datetime import UTC, datetime

import httpx
import pytest

from lifeflow_api.connectors.google_calendar import _MAX_PAGES, GoogleCalendarConnector
from lifeflow_api.connectors.google_email import (
    _MAX_HISTORY_PAGES,
    _MAX_WINDOW_PAGES,
    GoogleEmailConnector,
)
from lifeflow_api.connectors.interfaces import EmailFolder
from lifeflow_api.google.calendar_client import CalendarEventClient
from lifeflow_api.google.errors import GoogleClientError
from lifeflow_api.google.gmail_client import GmailDraftClient
from lifeflow_api.google_sync_cursor import EMPTY_CURSOR, GoogleSyncCursor

SINCE = datetime(2026, 7, 1, tzinfo=UTC)
UNTIL = datetime(2026, 8, 1, tzinfo=UTC)


def _committed(value: str | None) -> GoogleSyncCursor:
    if value is None:
        return EMPTY_CURSOR
    return GoogleSyncCursor(
        committed_cursor=value,
        continuation_page_token=None,
        continuation_base_cursor=None,
        sync_in_progress=False,
        last_complete_sync_at=None,
    )


def _gmail_message_json(msg_id: str, folder_label: str) -> dict:
    return {
        "id": msg_id,
        "threadId": f"thread-{msg_id}",
        "snippet": "Could you confirm the figures?",
        "internalDate": "1700000000000",
        "labelIds": [folder_label],
        "payload": {
            "headers": [
                {"name": "From", "value": "Dana Lee <dana@example.com>"},
                {"name": "To", "value": "demo@lifeflow.local"},
                {"name": "Subject", "value": "Quarterly review"},
            ]
        },
    }


async def test_email_connector_uses_history_cursor_when_present() -> None:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/history"):
            return httpx.Response(
                200,
                json={
                    "history": [{"messagesAdded": [{"message": {"id": "m1"}}]}],
                    "historyId": "42",
                },
            )
        return httpx.Response(200, json=_gmail_message_json("m1", "INBOX"))

    client = GmailDraftClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleEmailConnector(client, access_token="token", cursor=_committed("10"))

    messages = await connector.fetch_recent(since=SINCE, until=UNTIL)

    assert any(path.endswith("/history") for path in calls)
    assert not any(path.endswith("/messages") for path in calls)
    assert len(messages) == 1
    assert messages[0].folder == EmailFolder.inbox
    assert connector.result_cursor.committed_cursor == "42"
    assert connector.sync_complete is True
    assert connector.cursor_status == "incremental"


async def test_email_connector_falls_back_to_windowed_fetch_on_expired_history() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/history"):
            return httpx.Response(404, json={})
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "m1", "threadId": "t1"}]})
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "100"})
        return httpx.Response(200, json=_gmail_message_json("m1", "SENT"))

    client = GmailDraftClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleEmailConnector(client, access_token="token", cursor=_committed("stale"))

    messages = await connector.fetch_recent(since=SINCE, until=UNTIL)

    assert len(messages) == 1
    assert messages[0].folder == EmailFolder.sent
    assert connector.result_cursor.committed_cursor == "100"  # fresh baseline from the resync
    assert connector.cursor_status == "resynced"


async def test_email_connector_skips_messages_outside_inbox_or_sent() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "m1", "threadId": "t1"}]})
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "1"})
        return httpx.Response(200, json=_gmail_message_json("m1", "TRASH"))

    client = GmailDraftClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleEmailConnector(client, access_token="token", cursor=EMPTY_CURSOR)

    messages = await connector.fetch_recent(since=SINCE, until=UNTIL)
    assert messages == []
    assert connector.excluded_count == 1
    assert connector.incomplete_count == 0


async def test_email_connector_skips_a_404_history_reference_without_failing_the_whole_sync() -> (
    None
):
    """Real sandbox finding (D38): Gmail's History API documents that a
    `messageAdded` entry can reference a message no longer retrievable (here,
    a draft's underlying message superseded by a later edit). Fetching it
    404s; the connector must skip just that one message — count it as
    genuinely incomplete — and still return every other message in the
    batch, never raise and take down the whole sync."""

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/history"):
            return httpx.Response(
                200,
                json={
                    "history": [
                        {"messagesAdded": [{"message": {"id": "gone"}}]},
                        {"messagesAdded": [{"message": {"id": "m1"}}]},
                    ],
                    "historyId": "42",
                },
            )
        if path.endswith("/messages/gone"):
            return httpx.Response(404, json={"error": {"message": "Not Found"}})
        return httpx.Response(200, json=_gmail_message_json("m1", "INBOX"))

    client = GmailDraftClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleEmailConnector(client, access_token="token", cursor=_committed("10"))

    messages = await connector.fetch_recent(since=SINCE, until=UNTIL)

    assert len(messages) == 1
    assert messages[0].external_id == "m1"
    assert connector.incomplete_count == 1
    assert connector.excluded_count == 0
    assert connector.sync_complete is True
    assert connector.result_cursor.committed_cursor == "42"  # sync still completes normally


async def test_email_connector_reraises_non_404_errors_when_resolving_a_message() -> None:
    """The 404-is-expected carve-out must stay narrow: any other client
    error resolving a message (bad request, permission denied, etc.) is a
    real, actionable failure and must still propagate, not be silently
    swallowed alongside the benign stale-history-reference case."""

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/history"):
            return httpx.Response(
                200,
                json={
                    "history": [{"messagesAdded": [{"message": {"id": "m1"}}]}],
                    "historyId": "1",
                },
            )
        return httpx.Response(400, json={"error": {"message": "Bad Request"}})

    client = GmailDraftClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleEmailConnector(client, access_token="token", cursor=_committed("10"))

    with pytest.raises(GoogleClientError):
        await connector.fetch_recent(since=SINCE, until=UNTIL)


async def test_calendar_connector_uses_sync_token_when_present() -> None:
    calls: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "ev1",
                        "summary": "Sync",
                        "start": {"dateTime": "2026-07-20T10:00:00+01:00"},
                        "end": {"dateTime": "2026-07-20T10:30:00+01:00"},
                        "attendees": [{"email": "dana@example.com"}],
                        "status": "confirmed",
                    }
                ],
                "nextSyncToken": "new-token",
            },
        )

    client = CalendarEventClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleCalendarConnector(
        client, access_token="token", cursor=_committed("old-token")
    )

    events = await connector.fetch_events(since=SINCE, until=UNTIL)

    assert calls[0].get("syncToken") == "old-token"
    assert "timeMin" not in calls[0]
    assert len(events) == 1
    assert connector.result_cursor.committed_cursor == "new-token"
    assert connector.cursor_status == "incremental"


async def test_calendar_connector_falls_back_to_windowed_fetch_on_invalid_sync_token() -> None:
    call_count = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(410, json={})
        assert "timeMin" in request.url.params
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "ev1",
                        "summary": "Sync",
                        "start": {"dateTime": "2026-07-20T10:00:00+01:00"},
                        "end": {"dateTime": "2026-07-20T10:30:00+01:00"},
                        "attendees": [{"email": "dana@example.com"}],
                        "status": "confirmed",
                    }
                ],
                "nextSyncToken": "fresh-token",
            },
        )

    client = CalendarEventClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleCalendarConnector(
        client, access_token="token", cursor=_committed("stale-token")
    )

    events = await connector.fetch_events(since=SINCE, until=UNTIL)

    assert len(events) == 1
    assert connector.result_cursor.committed_cursor == "fresh-token"
    assert connector.cursor_status == "resynced"


async def test_calendar_connector_skips_cancelled_events() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "ev1",
                        "summary": "Cancelled meeting",
                        "start": {"dateTime": "2026-07-20T10:00:00+01:00"},
                        "end": {"dateTime": "2026-07-20T10:30:00+01:00"},
                        "attendees": [],
                        "status": "cancelled",
                    }
                ],
                "nextSyncToken": "t2",
            },
        )

    client = CalendarEventClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleCalendarConnector(client, access_token="token", cursor=EMPTY_CURSOR)

    events = await connector.fetch_events(since=SINCE, until=UNTIL)
    assert events == []


async def test_calendar_connector_sorts_all_day_and_timed_events_without_crashing() -> None:
    """A real calendar's `date` (all-day, no timezone) and `dateTime` (timed,
    UTC-offset) events must sort together — a naive/aware datetime mismatch
    here raises `TypeError: can't compare offset-naive and offset-aware
    datetimes` (caught only against a real Google account, never the
    synthetic demo dataset or a mocked page containing just one shape)."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "ev-timed",
                        "summary": "Timed meeting",
                        "start": {"dateTime": "2026-07-20T10:00:00+01:00"},
                        "end": {"dateTime": "2026-07-20T10:30:00+01:00"},
                        "attendees": [],
                        "status": "confirmed",
                    },
                    {
                        "id": "ev-all-day",
                        "summary": "All-day event",
                        "start": {"date": "2026-07-19"},
                        "end": {"date": "2026-07-20"},
                        "attendees": [],
                        "status": "confirmed",
                    },
                ],
                "nextSyncToken": "t3",
            },
        )

    client = CalendarEventClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleCalendarConnector(client, access_token="token", cursor=EMPTY_CURSOR)

    events = await connector.fetch_events(since=SINCE, until=UNTIL)

    assert [e.external_id for e in events] == ["ev-all-day", "ev-timed"]
    all_day_event = next(e for e in events if e.external_id == "ev-all-day")
    assert all_day_event.all_day is True
    assert all_day_event.starts_at.tzinfo is not None
    timed_event = next(e for e in events if e.external_id == "ev-timed")
    assert timed_event.all_day is False
    assert timed_event.starts_at.tzinfo is not None


# --- Cursor safety: page bound reached with more pages remaining ----------


async def test_email_history_fetch_stops_after_max_pages_but_never_advances_committed_cursor() -> (
    None
):
    """1/3/4. More pages exist than `_MAX_HISTORY_PAGES` — the fetch stops
    at the bound, reports incomplete, and the committed historyId is
    preserved exactly (never advanced past the unseen pages)."""
    call_count = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/history"):
            call_count["n"] += 1
            return httpx.Response(
                200,
                json={
                    "history": [{"messagesAdded": [{"message": {"id": f"m{call_count['n']}"}}]}],
                    "historyId": str(call_count["n"]),
                    "nextPageToken": "keep-going",  # never empty — server never stops paginating
                },
            )
        return httpx.Response(
            200, json=_gmail_message_json(request.url.path.rsplit("/", 1)[-1], "INBOX")
        )

    client = GmailDraftClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleEmailConnector(client, access_token="token", cursor=_committed("0"))

    await connector.fetch_recent(since=SINCE, until=UNTIL)

    assert call_count["n"] == _MAX_HISTORY_PAGES
    assert connector.sync_complete is False
    assert connector.cursor_status == "incomplete"
    # The original committed cursor ("0") survives untouched — never a
    # newly-returned historyId from a page we know is incomplete.
    assert connector.result_cursor.committed_cursor == "0"
    assert connector.result_cursor.sync_in_progress is True
    assert connector.result_cursor.continuation_page_token == "keep-going"
    assert connector.result_cursor.continuation_base_cursor == "0"


async def test_email_history_fetch_completes_at_exactly_the_page_bound() -> None:
    """2. Exactly `_MAX_HISTORY_PAGES` pages exist (the last carries no
    `nextPageToken`) — the sync completes and the committed cursor
    advances normally."""
    call_count = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/history"):
            call_count["n"] += 1
            body = {
                "history": [{"messagesAdded": [{"message": {"id": f"m{call_count['n']}"}}]}],
                "historyId": str(call_count["n"]),
            }
            if call_count["n"] < _MAX_HISTORY_PAGES:
                body["nextPageToken"] = "more"
            return httpx.Response(200, json=body)
        return httpx.Response(
            200, json=_gmail_message_json(request.url.path.rsplit("/", 1)[-1], "INBOX")
        )

    client = GmailDraftClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleEmailConnector(client, access_token="token", cursor=_committed("0"))

    await connector.fetch_recent(since=SINCE, until=UNTIL)

    assert call_count["n"] == _MAX_HISTORY_PAGES
    assert connector.sync_complete is True
    assert connector.cursor_status == "incremental"
    assert connector.result_cursor.committed_cursor == str(_MAX_HISTORY_PAGES)
    assert connector.result_cursor.continuation_page_token is None
    assert connector.result_cursor.sync_in_progress is False


async def test_email_history_fetch_resumes_from_a_persisted_continuation() -> None:
    """6. A later sync resumes from the persisted continuation token and
    the original base historyId, rather than skipping or re-starting."""
    seen_page_tokens: list[str | None] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/history"):
            seen_page_tokens.append(request.url.params.get("pageToken"))
            assert request.url.params.get("startHistoryId") == "0"
            return httpx.Response(
                200, json={"history": [], "historyId": "99", "nextPageToken": None}
            )
        raise AssertionError("unexpected request")

    incomplete_cursor = GoogleSyncCursor(
        committed_cursor="0",
        continuation_page_token="resume-here",
        continuation_base_cursor="0",
        sync_in_progress=True,
        last_complete_sync_at=None,
    )
    client = GmailDraftClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleEmailConnector(client, access_token="token", cursor=incomplete_cursor)

    await connector.fetch_recent(since=SINCE, until=UNTIL)

    assert seen_page_tokens[0] == "resume-here"
    assert connector.sync_complete is True
    assert connector.result_cursor.committed_cursor == "99"
    assert connector.result_cursor.continuation_page_token is None


async def test_email_windowed_fetch_stops_after_max_pages_and_never_commits_a_new_baseline() -> (
    None
):
    """A first-ever (windowed) sync that hits the page bound must not call
    `get_current_history_id` or commit any baseline — that would silently
    skip whatever the unseen pages contained."""
    call_count = {"n": 0}
    profile_calls = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages"):
            call_count["n"] += 1
            return httpx.Response(
                200,
                json={
                    "messages": [{"id": f"m{call_count['n']}", "threadId": "t"}],
                    "nextPageToken": "keep-going",
                },
            )
        if request.url.path.endswith("/profile"):
            profile_calls["n"] += 1
            return httpx.Response(200, json={"historyId": "1"})
        return httpx.Response(
            200, json=_gmail_message_json(request.url.path.rsplit("/", 1)[-1], "INBOX")
        )

    client = GmailDraftClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleEmailConnector(client, access_token="token", cursor=EMPTY_CURSOR)

    await connector.fetch_recent(since=SINCE, until=UNTIL)

    assert call_count["n"] == _MAX_WINDOW_PAGES
    assert profile_calls["n"] == 0  # never established a new baseline mid-resync
    assert connector.sync_complete is False
    assert connector.cursor_status == "incomplete"
    assert connector.result_cursor.committed_cursor is None
    assert connector.result_cursor.continuation_page_token == "keep-going"


async def test_email_windowed_fetch_resumes_with_the_exact_original_window() -> None:
    """A resumed windowed continuation reuses the exact since/until the
    page token was issued against, not a freshly-shifted rolling window."""
    seen_queries: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages"):
            seen_queries.append(request.url.params.get("q", ""))
            assert request.url.params.get("pageToken") == "resume-here"
            return httpx.Response(200, json={"messages": []})
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "final-baseline"})
        raise AssertionError("unexpected request")

    from lifeflow_api.google_sync_cursor import encode_window

    original_since = datetime(2026, 6, 1, tzinfo=UTC)
    original_until = datetime(2026, 6, 30, tzinfo=UTC)
    incomplete_cursor = GoogleSyncCursor(
        committed_cursor=None,
        continuation_page_token="resume-here",
        continuation_base_cursor=encode_window(original_since, original_until),
        sync_in_progress=True,
        last_complete_sync_at=None,
    )
    client = GmailDraftClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleEmailConnector(client, access_token="token", cursor=incomplete_cursor)

    # A very different "current" window is passed in — it must be ignored
    # in favour of the persisted original window.
    await connector.fetch_recent(
        since=datetime(2026, 8, 1, tzinfo=UTC), until=datetime(2026, 8, 31, tzinfo=UTC)
    )

    assert f"after:{int(original_since.timestamp())}" in seen_queries[0]
    assert f"before:{int(original_until.timestamp())}" in seen_queries[0]


async def test_calendar_sync_token_fetch_stops_after_max_pages_but_never_advances_committed_cursor() -> (
    None
):
    """A Calendar response carrying `nextPageToken` must never be treated as
    final: even though every page here also carries a `nextSyncToken` (an
    intermediate-page mock contract Google's real API never actually uses),
    the connector must not commit it while pages remain."""
    call_count = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(
            200,
            json={
                "items": [],
                "nextPageToken": "keep-going",
                "nextSyncToken": f"token-{call_count['n']}",
            },
        )

    client = CalendarEventClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleCalendarConnector(
        client, access_token="token", cursor=_committed("old-token")
    )

    await connector.fetch_events(since=SINCE, until=UNTIL)

    assert call_count["n"] == _MAX_PAGES
    assert connector.sync_complete is False
    assert connector.cursor_status == "incomplete"
    assert connector.result_cursor.committed_cursor == "old-token"
    assert connector.result_cursor.continuation_page_token == "keep-going"


async def test_calendar_sync_token_fetch_completes_at_exactly_the_page_bound() -> None:
    call_count = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        body: dict = {"items": []}
        if call_count["n"] < _MAX_PAGES:
            body["nextPageToken"] = "more"
        else:
            body["nextSyncToken"] = "final-token"
        return httpx.Response(200, json=body)

    client = CalendarEventClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleCalendarConnector(
        client, access_token="token", cursor=_committed("old-token")
    )

    await connector.fetch_events(since=SINCE, until=UNTIL)

    assert call_count["n"] == _MAX_PAGES
    assert connector.sync_complete is True
    assert connector.result_cursor.committed_cursor == "final-token"
    assert connector.result_cursor.continuation_page_token is None


async def test_calendar_sync_token_fetch_resumes_from_a_persisted_continuation() -> None:
    seen_page_tokens: list[str | None] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen_page_tokens.append(request.url.params.get("pageToken"))
        return httpx.Response(200, json={"items": [], "nextSyncToken": "resumed-final"})

    incomplete_cursor = GoogleSyncCursor(
        committed_cursor="old-token",
        continuation_page_token="resume-here",
        continuation_base_cursor="old-token",
        sync_in_progress=True,
        last_complete_sync_at=None,
    )
    client = CalendarEventClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleCalendarConnector(client, access_token="token", cursor=incomplete_cursor)

    await connector.fetch_events(since=SINCE, until=UNTIL)

    assert seen_page_tokens[0] == "resume-here"
    assert connector.sync_complete is True
    assert connector.result_cursor.committed_cursor == "resumed-final"


async def test_calendar_expired_continuation_falls_back_without_skipping_data() -> None:
    """9. An expired sync token discovered while resuming a continuation
    safely falls back to a full bounded resync — it never raises past the
    connector or leaves the cursor half-updated."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("pageToken") == "resume-here":
            return httpx.Response(410, json={})
        assert "timeMin" in request.url.params
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "ev1",
                        "summary": "Recovered",
                        "start": {"dateTime": "2026-07-20T10:00:00+01:00"},
                        "end": {"dateTime": "2026-07-20T10:30:00+01:00"},
                        "attendees": [],
                        "status": "confirmed",
                    }
                ],
                "nextSyncToken": "fresh-after-recovery",
            },
        )

    incomplete_cursor = GoogleSyncCursor(
        committed_cursor="old-token",
        continuation_page_token="resume-here",
        continuation_base_cursor="old-token",
        sync_in_progress=True,
        last_complete_sync_at=None,
    )
    client = CalendarEventClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleCalendarConnector(client, access_token="token", cursor=incomplete_cursor)

    events = await connector.fetch_events(since=SINCE, until=UNTIL)

    assert len(events) == 1
    assert connector.sync_complete is True
    assert connector.cursor_status == "resynced"
    assert connector.result_cursor.committed_cursor == "fresh-after-recovery"
    assert connector.result_cursor.continuation_page_token is None


async def test_email_connector_flags_list_unsubscribe_as_bulk_marker() -> None:
    """ADR 0003 D42: the RFC-standard List-Unsubscribe header (any casing)
    is recorded on the normalised message; ordinary mail stays unflagged."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/history"):
            return httpx.Response(
                200,
                json={
                    "history": [
                        {"messagesAdded": [{"message": {"id": "promo"}}]},
                        {"messagesAdded": [{"message": {"id": "personal"}}]},
                    ],
                    "historyId": "42",
                },
            )
        if request.url.path.endswith("/messages/promo"):
            body = _gmail_message_json("promo", "INBOX")
            body["payload"]["headers"].append(
                {"name": "List-unsubscribe", "value": "<https://example.com/u>"}
            )
            return httpx.Response(200, json=body)
        return httpx.Response(200, json=_gmail_message_json("personal", "INBOX"))

    client = GmailDraftClient(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    connector = GoogleEmailConnector(client, access_token="token", cursor=_committed("10"))

    messages = await connector.fetch_recent(since=SINCE, until=UNTIL)

    by_id = {message.external_id: message for message in messages}
    assert by_id["promo"].list_unsubscribe is True
    assert by_id["personal"].list_unsubscribe is False
