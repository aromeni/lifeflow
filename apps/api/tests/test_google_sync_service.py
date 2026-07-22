"""Stage 7: GoogleSyncService — the orchestration wrapper tying token
resolution, both connectors, and the existing IngestionService together,
then persisting each connector's advanced cursor (ADR 0003 D21).
"""

import base64
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL

from lifeflow_api.accounts import ConnectedAccountService, ReauthorisationRequiredError
from lifeflow_api.google.calendar_client import CalendarEventClient
from lifeflow_api.google.errors import GoogleTransientError
from lifeflow_api.google.gmail_client import GmailDraftClient
from lifeflow_api.google.oauth import GoogleOAuthClient
from lifeflow_api.google_scopes import CALENDAR_READONLY_SCOPE, GMAIL_READONLY_SCOPE
from lifeflow_api.google_sync import GoogleReadScopeMissingError, GoogleSyncService
from lifeflow_api.models import AccountStatus, User
from lifeflow_api.repositories import ConnectedAccountRepository, SourceItemRepository
from lifeflow_api.security.token_cipher import AesGcmTokenCipher

pytestmark = pytest.mark.integration

SINCE = datetime(2026, 7, 1, tzinfo=UTC)
UNTIL = datetime(2026, 8, 1, tzinfo=UTC)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


@pytest.fixture
def cipher() -> AesGcmTokenCipher:
    return AesGcmTokenCipher(base64.b64encode(os.urandom(32)).decode(), "test-1")


def _handler() -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "m1", "threadId": "t1"}]})
        if path.endswith("/messages/m1"):
            return httpx.Response(
                200,
                json={
                    "id": "m1",
                    "threadId": "t1",
                    "snippet": "Could you confirm the figures?",
                    "internalDate": "1700000000000",
                    "labelIds": ["INBOX"],
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "Dana <dana@example.com>"},
                            {"name": "To", "value": "demo@lifeflow.local"},
                            {"name": "Subject", "value": "Quarterly review"},
                        ]
                    },
                },
            )
        if path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "100"})
        if path.endswith("/events"):
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
                    "nextSyncToken": "sync-token-1",
                },
            )
        raise AssertionError(f"unexpected request: {path}")

    return httpx.MockTransport(handle)


async def _seed_google_account(session: AsyncSession, cipher: AesGcmTokenCipher) -> User:
    user = User(email=f"sync-{uuid.uuid4()}@example.com", display_name="Sync")
    session.add(user)
    await session.flush()
    await ConnectedAccountService(session, user.id, cipher).store_tokens(
        provider="google",
        access_token="access-1",
        refresh_token="refresh-1",
        granted_scopes=[GMAIL_READONLY_SCOPE, CALENDAR_READONLY_SCOPE],
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await session.flush()
    return user


def _service(session: AsyncSession, user: User, cipher: AesGcmTokenCipher) -> GoogleSyncService:
    mock_http = httpx.AsyncClient(transport=_handler())
    return GoogleSyncService(
        session,
        user.id,
        cipher=cipher,
        oauth_client=GoogleOAuthClient(mock_http),
        gmail_client=GmailDraftClient(mock_http),
        calendar_client=CalendarEventClient(mock_http),
        client_id="cid",
        client_secret="secret",
    )


async def test_sync_imports_sources_and_persists_both_cursors(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user = await _seed_google_account(session, cipher)
    service = _service(session, user, cipher)

    summary = await service.sync(since=SINCE, until=UNTIL)
    assert summary.imported == 2  # one email, one calendar event

    account = await ConnectedAccountRepository(session, user.id).get_by_provider("google")
    assert account is not None
    assert account.sync_cursors["gmail"]["committed_cursor"] == "100"
    assert account.sync_cursors["calendar"]["committed_cursor"] == "sync-token-1"
    assert account.sync_cursors["gmail"]["continuation_page_token"] is None
    assert account.sync_cursors["calendar"]["continuation_page_token"] is None
    assert account.last_sync_at is not None

    sources = await SourceItemRepository(session, user.id).list(limit=10)
    assert {item.source_type for item in sources} == {"email", "calendar_event"}


async def test_sync_reports_gmail_excluded_and_calendar_incomplete_separately(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    """Stage 7 focused remediation: a Gmail message outside Inbox/Sent is
    excluded by design (D21), not a failure — it must never be counted
    alongside a genuinely unparseable Calendar event under one misleading
    combined "incomplete" number."""

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/messages"):
            return httpx.Response(
                200,
                json={"messages": [{"id": "m1", "threadId": "t1"}, {"id": "m2", "threadId": "t2"}]},
            )
        if path.endswith("/messages/m1"):
            return httpx.Response(
                200,
                json={
                    "id": "m1",
                    "threadId": "t1",
                    "snippet": "Could you confirm the figures?",
                    "internalDate": "1700000000000",
                    "labelIds": ["INBOX"],
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "Dana <dana@example.com>"},
                            {"name": "To", "value": "demo@lifeflow.local"},
                            {"name": "Subject", "value": "Quarterly review"},
                        ]
                    },
                },
            )
        if path.endswith("/messages/m2"):
            # Archived/Spam/Promotions/Social — neither INBOX nor SENT.
            return httpx.Response(
                200,
                json={
                    "id": "m2",
                    "threadId": "t2",
                    "snippet": "50% off everything",
                    "internalDate": "1700000000000",
                    "labelIds": ["CATEGORY_PROMOTIONS"],
                    "payload": {"headers": []},
                },
            )
        if path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "100"})
        if path.endswith("/events"):
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
                        },
                        {
                            "id": "ev-bad",
                            "summary": "Malformed",
                            "start": {"dateTime": "not-a-real-timestamp"},
                            "end": {"dateTime": "2026-07-20T10:30:00+01:00"},
                            "attendees": [],
                            "status": "confirmed",
                        },
                    ],
                    "nextSyncToken": "sync-token-1",
                },
            )
        raise AssertionError(f"unexpected request: {path}")

    user = await _seed_google_account(session, cipher)
    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    service = GoogleSyncService(
        session,
        user.id,
        cipher=cipher,
        oauth_client=GoogleOAuthClient(mock_http),
        gmail_client=GmailDraftClient(mock_http),
        calendar_client=CalendarEventClient(mock_http),
        client_id="cid",
        client_secret="secret",
    )

    summary = await service.sync(since=SINCE, until=UNTIL)

    assert summary.imported == 2  # the one real inbox email + the one valid event
    assert summary.gmail_excluded == 1  # m2, promotions — not a failure
    assert summary.calendar_incomplete == 1  # ev-bad, genuinely unparseable


async def test_sync_reports_gmail_incomplete_and_never_fails_the_whole_sync_on_a_404_history_reference(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    """Real sandbox finding (D38): a Gmail message id (from the initial
    windowed list, or later incremental history — the per-message fetch
    behaves identically either way) that 404s when fetched (e.g. a draft's
    underlying message superseded by a later edit) must not fail the entire
    sync (`502 Bad Gateway`, as observed live) — it must be counted as
    `gmail_incomplete` and the rest of the sync must complete normally."""

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/messages"):
            return httpx.Response(
                200,
                json={
                    "messages": [{"id": "gone", "threadId": "t0"}, {"id": "m1", "threadId": "t1"}]
                },
            )
        if path.endswith("/messages/gone"):
            return httpx.Response(404, json={"error": {"message": "Not Found"}})
        if path.endswith("/messages/m1"):
            return httpx.Response(
                200,
                json={
                    "id": "m1",
                    "threadId": "t1",
                    "snippet": "Could you confirm the figures?",
                    "internalDate": "1700000000000",
                    "labelIds": ["INBOX"],
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "Dana <dana@example.com>"},
                            {"name": "To", "value": "demo@lifeflow.local"},
                            {"name": "Subject", "value": "Quarterly review"},
                        ]
                    },
                },
            )
        if path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "100"})
        if path.endswith("/events"):
            return httpx.Response(200, json={"items": [], "nextSyncToken": "sync-token-1"})
        raise AssertionError(f"unexpected request: {path}")

    user = await _seed_google_account(session, cipher)
    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    service = GoogleSyncService(
        session,
        user.id,
        cipher=cipher,
        oauth_client=GoogleOAuthClient(mock_http),
        gmail_client=GmailDraftClient(mock_http),
        calendar_client=CalendarEventClient(mock_http),
        client_id="cid",
        client_secret="secret",
    )

    summary = await service.sync(since=SINCE, until=UNTIL)

    assert summary.imported == 1  # only m1 — "gone" was skipped, not fatal
    assert summary.gmail_incomplete == 1
    assert summary.gmail_excluded == 0
    assert summary.gmail_sync_complete is True


async def test_sync_reuses_stored_cursors_on_a_second_run(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user = await _seed_google_account(session, cipher)
    service = _service(session, user, cipher)
    await service.sync(since=SINCE, until=UNTIL)
    await session.flush()

    seen_params: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen_params.append(dict(request.url.params))
        if request.url.path.endswith("/history"):
            return httpx.Response(200, json={"history": [], "historyId": "101"})
        if request.url.path.endswith("/events"):
            return httpx.Response(200, json={"items": [], "nextSyncToken": "sync-token-2"})
        raise AssertionError(f"unexpected request: {request.url.path}")

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    service2 = GoogleSyncService(
        session,
        user.id,
        cipher=cipher,
        oauth_client=GoogleOAuthClient(mock_http),
        gmail_client=GmailDraftClient(mock_http),
        calendar_client=CalendarEventClient(mock_http),
        client_id="cid",
        client_secret="secret",
    )
    await service2.sync(since=SINCE, until=UNTIL)

    assert any(params.get("syncToken") == "sync-token-1" for params in seen_params)
    account = await ConnectedAccountRepository(session, user.id).get_by_provider("google")
    assert account is not None
    assert account.sync_cursors["gmail"]["committed_cursor"] == "101"
    assert account.sync_cursors["calendar"]["committed_cursor"] == "sync-token-2"


async def test_sync_requires_an_active_google_account(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user = User(email=f"no-account-{uuid.uuid4()}@example.com", display_name="N")
    session.add(user)
    await session.flush()
    service = _service(session, user, cipher)

    with pytest.raises(ReauthorisationRequiredError):
        await service.sync(since=SINCE, until=UNTIL)


async def test_sync_requires_the_account_to_be_active_not_just_present(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user = await _seed_google_account(session, cipher)
    account = await ConnectedAccountRepository(session, user.id).get_by_provider("google")
    assert account is not None
    account.status = AccountStatus.revoked
    await session.flush()

    service = _service(session, user, cipher)
    with pytest.raises(ReauthorisationRequiredError):
        await service.sync(since=SINCE, until=UNTIL)


async def test_sync_skips_calendar_when_only_gmail_scope_is_granted(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    """A partial grant (Stage 7 remediation): syncing must never call an
    endpoint the user didn't authorise, and must not fail the half that was
    granted."""
    user = User(email=f"gmail-only-{uuid.uuid4()}@example.com", display_name="Gmail Only")
    session.add(user)
    await session.flush()
    await ConnectedAccountService(session, user.id, cipher).store_tokens(
        provider="google",
        access_token="access-1",
        refresh_token="refresh-1",
        granted_scopes=[GMAIL_READONLY_SCOPE],
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await session.flush()
    service = _service(session, user, cipher)

    summary = await service.sync(since=SINCE, until=UNTIL)

    assert summary.gmail_synced is True
    assert summary.calendar_synced is False
    assert summary.calendar_cursor_status == "not_granted"
    assert summary.imported == 1  # the email only; /events was never called
    account = await ConnectedAccountRepository(session, user.id).get_by_provider("google")
    assert account is not None
    assert "calendar" not in account.sync_cursors


async def test_sync_raises_when_neither_read_scope_is_granted(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user = User(email=f"no-read-scope-{uuid.uuid4()}@example.com", display_name="No Scope")
    session.add(user)
    await session.flush()
    await ConnectedAccountService(session, user.id, cipher).store_tokens(
        provider="google",
        access_token="access-1",
        refresh_token="refresh-1",
        granted_scopes=["https://www.googleapis.com/auth/gmail.compose"],
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await session.flush()
    service = _service(session, user, cipher)

    with pytest.raises(GoogleReadScopeMissingError):
        await service.sync(since=SINCE, until=UNTIL)


def _paginating_handler(call_count: dict[str, int]) -> httpx.MockTransport:
    """Gmail's `/history` never stops paginating and Calendar's `/events`
    only reports `nextSyncToken` once its own final page is reached — a
    same-account, cross-source pagination-bound scenario (Stage 7
    remediation blocker #3)."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/history"):
            call_count["gmail"] += 1
            return httpx.Response(
                200,
                json={
                    "history": [],
                    "historyId": str(call_count["gmail"]),
                    "nextPageToken": "keep-going",
                },
            )
        if request.url.path.endswith("/events"):
            call_count["calendar"] += 1
            return httpx.Response(
                200,
                json={
                    "items": [],
                    "nextPageToken": "keep-going",
                    "nextSyncToken": f"calendar-{call_count['calendar']}",
                },
            )
        raise AssertionError(f"unexpected request: {request.url.path}")

    return httpx.MockTransport(handle)


async def test_sync_reports_incomplete_and_preserves_committed_cursors_at_the_page_bound(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    """1/3/4. More pages exist than the configured maximum for both Gmail
    and Calendar in the same sync call — the sync reports incomplete for
    both, and neither committed cursor advances past the unseen pages."""
    user = await _seed_google_account(session, cipher)
    account = await ConnectedAccountRepository(session, user.id).get_by_provider("google")
    assert account is not None
    account.sync_cursors = {
        "gmail": {
            "committed_cursor": "original-gmail",
            "continuation_page_token": None,
            "continuation_base_cursor": None,
            "sync_in_progress": False,
            "last_complete_sync_at": None,
        },
        "calendar": {
            "committed_cursor": "original-calendar",
            "continuation_page_token": None,
            "continuation_base_cursor": None,
            "sync_in_progress": False,
            "last_complete_sync_at": None,
        },
    }
    await session.flush()

    call_count = {"gmail": 0, "calendar": 0}
    mock_http = httpx.AsyncClient(transport=_paginating_handler(call_count))
    service = GoogleSyncService(
        session,
        user.id,
        cipher=cipher,
        oauth_client=GoogleOAuthClient(mock_http),
        gmail_client=GmailDraftClient(mock_http),
        calendar_client=CalendarEventClient(mock_http),
        client_id="cid",
        client_secret="secret",
    )

    summary = await service.sync(since=SINCE, until=UNTIL)

    assert summary.gmail_sync_complete is False
    assert summary.calendar_sync_complete is False
    assert summary.gmail_cursor_status == "incomplete"
    assert summary.calendar_cursor_status == "incomplete"

    refreshed = await ConnectedAccountRepository(session, user.id).get_by_provider("google")
    assert refreshed is not None
    assert refreshed.sync_cursors["gmail"]["committed_cursor"] == "original-gmail"
    assert refreshed.sync_cursors["calendar"]["committed_cursor"] == "original-calendar"
    assert refreshed.sync_cursors["gmail"]["continuation_page_token"] == "keep-going"
    assert refreshed.sync_cursors["calendar"]["continuation_page_token"] == "keep-going"


async def test_sync_resumes_from_persisted_continuation_on_a_later_call(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    """6. A later sync resumes from the persisted continuation token rather
    than restarting from the committed cursor or skipping ahead."""
    user = await _seed_google_account(session, cipher)
    account = await ConnectedAccountRepository(session, user.id).get_by_provider("google")
    assert account is not None
    account.sync_cursors = {
        "gmail": {
            "committed_cursor": "5",
            "continuation_page_token": "resume-token",
            "continuation_base_cursor": "5",
            "sync_in_progress": True,
            "last_complete_sync_at": None,
        },
        "calendar": {
            "committed_cursor": "old-calendar",
            "continuation_page_token": "resume-calendar",
            "continuation_base_cursor": "old-calendar",
            "sync_in_progress": True,
            "last_complete_sync_at": None,
        },
    }
    await session.flush()

    seen_page_tokens: list[str | None] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/history"):
            seen_page_tokens.append(request.url.params.get("pageToken"))
            return httpx.Response(200, json={"history": [], "historyId": "6"})
        if request.url.path.endswith("/events"):
            seen_page_tokens.append(request.url.params.get("pageToken"))
            return httpx.Response(200, json={"items": [], "nextSyncToken": "new-calendar"})
        raise AssertionError(f"unexpected request: {request.url.path}")

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    service = GoogleSyncService(
        session,
        user.id,
        cipher=cipher,
        oauth_client=GoogleOAuthClient(mock_http),
        gmail_client=GmailDraftClient(mock_http),
        calendar_client=CalendarEventClient(mock_http),
        client_id="cid",
        client_secret="secret",
    )

    summary = await service.sync(since=SINCE, until=UNTIL)

    assert "resume-token" in seen_page_tokens
    assert "resume-calendar" in seen_page_tokens
    assert summary.gmail_sync_complete is True
    assert summary.calendar_sync_complete is True

    refreshed = await ConnectedAccountRepository(session, user.id).get_by_provider("google")
    assert refreshed is not None
    assert refreshed.sync_cursors["gmail"]["committed_cursor"] == "6"
    assert refreshed.sync_cursors["calendar"]["committed_cursor"] == "new-calendar"
    assert refreshed.sync_cursors["gmail"]["continuation_page_token"] is None
    assert refreshed.sync_cursors["calendar"]["continuation_page_token"] is None


async def test_failed_import_never_advances_committed_or_continuation_cursor(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    """8. A failed import (a connector read raises) never advances either
    the committed cursor or a continuation — the account's stored cursor
    state is untouched by a sync attempt that didn't complete."""
    user = await _seed_google_account(session, cipher)
    account = await ConnectedAccountRepository(session, user.id).get_by_provider("google")
    assert account is not None
    original_cursors = {
        "gmail": {
            "committed_cursor": "5",
            "continuation_page_token": None,
            "continuation_base_cursor": None,
            "sync_in_progress": False,
            "last_complete_sync_at": None,
        },
        "calendar": {
            "committed_cursor": "old-calendar",
            "continuation_page_token": None,
            "continuation_base_cursor": None,
            "sync_in_progress": False,
            "last_complete_sync_at": None,
        },
    }
    account.sync_cursors = dict(original_cursors)
    await session.flush()

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/history"):
            return httpx.Response(200, json={"history": [], "historyId": "999"})
        if request.url.path.endswith("/events"):
            return httpx.Response(500, json={})  # a transient failure mid-sync
        raise AssertionError(f"unexpected request: {request.url.path}")

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    service = GoogleSyncService(
        session,
        user.id,
        cipher=cipher,
        oauth_client=GoogleOAuthClient(mock_http),
        gmail_client=GmailDraftClient(mock_http),
        calendar_client=CalendarEventClient(mock_http),
        client_id="cid",
        client_secret="secret",
    )

    with pytest.raises(GoogleTransientError):
        await service.sync(since=SINCE, until=UNTIL)

    refreshed = await ConnectedAccountRepository(session, user.id).get_by_provider("google")
    assert refreshed is not None
    assert refreshed.sync_cursors == original_cursors
