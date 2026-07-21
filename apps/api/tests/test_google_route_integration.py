"""Stage 7 remediation: route-level integration tests proving the real
Google sync and execution paths are actually reachable through the running
FastAPI application (independent-review blockers #1, #2, #5; verification
item #6).

Every test here builds the app exactly as `main.create_app()` does and only
ever substitutes the HTTP transport underneath the Google clients with
`httpx.MockTransport` — the same pattern `test_google_auth_and_connections_api.py`
already uses for OAuth. `GoogleSyncService` and the Google executors are never
constructed directly inside a test; they are reached only by calling the real
HTTP routes, so these tests fail if the application wiring in
`connected_accounts.py` / `action_proposals.py` / `google_wiring.py` is ever
removed or bypassed again.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL, _test_settings
from tests.helpers import TIMEZONE, demo_source_items, scheduling_email_source

from lifeflow_api.brief_composition import BriefService
from lifeflow_api.google.calendar_client import CalendarEventClient
from lifeflow_api.google.gmail_client import GmailDraftClient
from lifeflow_api.google.oauth import GoogleOAuthClient
from lifeflow_api.main import create_app
from lifeflow_api.models import AccountStatus, ConnectedAccount, User

pytestmark = pytest.mark.integration

GOOGLE_SETTINGS_OVERRIDES = {
    "google_oauth_enabled": True,
    "google_oidc_client_id": "oidc-id",
    "google_oidc_client_secret": "oidc-secret",
    "google_oidc_redirect_uri": "http://localhost:8010/auth/google/callback",
    "google_connector_client_id": "conn-id",
    "google_connector_client_secret": "conn-secret",
    "google_connector_redirect_uri": "http://localhost:8010/connected-accounts/google/callback",
}

FULL_CONNECTOR_SCOPE = (
    "https://www.googleapis.com/auth/gmail.readonly "
    "https://www.googleapis.com/auth/gmail.compose "
    "https://www.googleapis.com/auth/calendar.readonly "
    "https://www.googleapis.com/auth/calendar.events"
)


async def _app_client(mock_transport: httpx.MockTransport) -> AsyncIterator[AsyncClient]:
    """The exact `create_app()` composition, with only the Google clients'
    transport swapped for a mock — nothing about the route/service/wiring
    layer is bypassed."""
    settings = _test_settings("development").model_copy(update=GOOGLE_SETTINGS_OVERRIDES)
    app = create_app(settings)
    mock_http = httpx.AsyncClient(transport=mock_transport)
    app.state.google_oauth_client = GoogleOAuthClient(mock_http)
    app.state.gmail_client = GmailDraftClient(mock_http)
    app.state.calendar_client = CalendarEventClient(mock_http)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


def _extract_state(location: str) -> str:
    return parse_qs(urlparse(location).query)["state"][0]


async def _dev_login(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/auth/dev-login",
        json={"email": email, "display_name": "Route Test"},
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200


async def _connect_google(client: AsyncClient, token_json: dict) -> None:
    """Drives the real connector-consent HTTP flow (`connect` -> `callback`)
    against a mocked `/token` response."""
    connect = await client.get("/connected-accounts/google/connect", follow_redirects=False)
    assert connect.status_code == 302
    state = _extract_state(connect.headers["location"])
    callback = await client.get(
        "/connected-accounts/google/callback",
        params={"code": "connector-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 302


# Route-level tests approve and execute through the REAL app, whose policy
# engine checks proposal expiry and event start times against
# `datetime.now(UTC)` — so seeding must anchor to the wall clock, never the
# frozen helpers.REFERENCE (a frozen anchor gives every generated proposal a
# fixed absolute expiry, and the whole suite silently rots once wall time
# passes it).
LIVE_REFERENCE = datetime.now(UTC)


async def _seed_synthetic_proposals(email: str) -> uuid.UUID:
    """Seeds a user (by email, so a later dev-login reuses the same row),
    a synthetic demo account, and one generated proposal per action type —
    identical to how `test_action_proposals.py`'s `_seed_proposals` builds
    fixtures, just committed through an independent connection so the HTTP
    client (a separate connection to the same database) can see it."""
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            user = User(email=email, display_name="Route Test")
            session.add(user)
            await session.flush()
            session.add(
                ConnectedAccount(
                    user_id=user.id,
                    provider="synthetic",
                    encrypted_access_token=None,
                    encrypted_refresh_token=None,
                    granted_scopes=["demo"],
                    expires_at=None,
                    status=AccountStatus.active,
                    last_sync_at=None,
                )
            )
            session.add_all(await demo_source_items(user.id, anchor=LIVE_REFERENCE.date()))
            await session.flush()
            await BriefService(session, user.id).generate(
                timezone=TIMEZONE, reference=LIVE_REFERENCE
            )
            await session.commit()
            return user.id
    finally:
        await engine.dispose()


async def _seed_google_sourced_proposals(email: str, *, granted_scopes: list[str]) -> uuid.UUID:
    """Like `_seed_synthetic_proposals`, but every `SourceItem`'s evidence is
    tagged to a pre-created `google` `ConnectedAccount` row instead of left
    unlinked, so the generated proposals are Google-sourced, not synthetic
    (Stage 7 remediation blocker #1). The later `_connect_google()` OAuth
    round-trip reuses this exact row (`ConnectedAccountService.store_tokens`
    matches on `user_id`+`provider`), so the account identity the evidence
    is bound to never changes underneath the test."""
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            user = User(email=email, display_name="Route Test")
            session.add(user)
            await session.flush()
            account = ConnectedAccount(
                user_id=user.id,
                provider="google",
                encrypted_access_token=None,
                encrypted_refresh_token=None,
                granted_scopes=granted_scopes,
                expires_at=None,
                status=AccountStatus.active,
                last_sync_at=None,
            )
            session.add(account)
            await session.flush()
            session.add_all(
                await demo_source_items(
                    user.id, account_id=account.id, anchor=LIVE_REFERENCE.date()
                )
            )
            session.add(
                scheduling_email_source(user.id, account_id=account.id, reference=LIVE_REFERENCE)
            )
            await session.flush()
            await BriefService(session, user.id).generate(
                timezone=TIMEZONE, reference=LIVE_REFERENCE
            )
            await session.commit()
            return user.id
    finally:
        await engine.dispose()


def _gmail_message_json(msg_id: str) -> dict:
    return {
        "id": msg_id,
        "threadId": f"thread-{msg_id}",
        "snippet": "Could you confirm the figures?",
        "internalDate": "1700000000000",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": "Dana Lee <dana@example.com>"},
                {"name": "To", "value": "demo@lifeflow.local"},
                {"name": "Subject", "value": "Quarterly review"},
            ]
        },
    }


def _calendar_event_json(event_id: str) -> dict:
    return {
        "id": event_id,
        "summary": "Sync",
        "start": {"dateTime": "2026-07-20T10:00:00+01:00"},
        "end": {"dateTime": "2026-07-20T10:30:00+01:00"},
        "attendees": [{"email": "dana@example.com"}],
        "status": "confirmed",
    }


def _token_response(scope: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 3600,
            "scope": scope,
            "id_token": None,
        },
    )


async def test_real_sync_route_persists_source_items_and_feeds_brief_generation() -> None:
    """Section 6, "Real synchronisation": connect -> POST .../sync -> real
    connector responses become persisted SourceItems -> a second sync reuses
    cursors -> signals/brief generation succeeds from that real data."""
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/token":
            return _token_response(FULL_CONNECTOR_SCOPE)
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "m1", "threadId": "t1"}]})
        if request.url.path.endswith("/messages/m1"):
            return httpx.Response(200, json=_gmail_message_json("m1"))
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "100"})
        if request.url.path.endswith("/history"):
            return httpx.Response(200, json={"history": [], "historyId": "101"})
        if request.url.path.endswith("/events"):
            if "syncToken" in request.url.params:
                return httpx.Response(200, json={"items": [], "nextSyncToken": "sync-token-2"})
            return httpx.Response(
                200,
                json={"items": [_calendar_event_json("ev1")], "nextSyncToken": "sync-token-1"},
            )
        raise AssertionError(f"unexpected request: {request.url.path}")

    email = f"sync-route-{uuid.uuid4()}@example.com"
    async for client in _app_client(httpx.MockTransport(handle)):
        await _dev_login(client, email)
        await _connect_google(client, _token_response(FULL_CONNECTOR_SCOPE).json())

        first_sync = await client.post("/connected-accounts/google/sync", headers=CSRF_HEADERS)
        assert first_sync.status_code == 200
        body = first_sync.json()
        assert body["imported"] == 2  # one email, one calendar event
        assert body["gmail_synced"] is True
        assert body["calendar_synced"] is True
        assert body["gmail_cursor_status"] == "initial"
        assert body["calendar_cursor_status"] == "initial"

        source_items = await client.get("/source-items")
        assert source_items.status_code == 200
        assert {item["source_type"] for item in source_items.json()["items"]} == {
            "email",
            "calendar_event",
        }

        # Second sync must use the persisted cursors, not a fresh window.
        second_sync = await client.post("/connected-accounts/google/sync", headers=CSRF_HEADERS)
        assert second_sync.status_code == 200
        second_body = second_sync.json()
        assert second_body["gmail_cursor_status"] == "incremental"
        assert second_body["calendar_cursor_status"] == "incremental"
        assert second_body["imported"] == 0
        assert second_body["unchanged"] == 0  # no items at all returned this time

        # The real-connector-sourced data is exactly what the existing
        # signal/brief pipeline (unchanged since Stage 5) then runs on.
        brief = await client.post("/briefs/generate", headers=CSRF_HEADERS)
        assert brief.status_code == 200
        assert brief.json()["status"] in {"complete", "empty", "partial", "degraded"}
        break

    assert any(path.endswith("/history") for path in calls)  # second sync used the cursor


async def test_sync_route_reports_incomplete_sync_truthfully() -> None:
    """11. The Connections UI (via the sync route response) reports an
    incomplete/partial sync truthfully rather than as an ordinary success —
    Stage 7 remediation blocker #3."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return _token_response(FULL_CONNECTOR_SCOPE)
        if request.url.path.endswith("/messages"):
            # A fresh (first-ever) sync goes through the windowed path, and
            # never stops paginating — the sync must hit its page bound.
            return httpx.Response(200, json={"messages": [], "nextPageToken": "keep-going"})
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                json={"items": [], "nextPageToken": "keep-going", "nextSyncToken": "irrelevant"},
            )
        raise AssertionError(f"unexpected request: {request.url.path}")

    email = f"incomplete-sync-{uuid.uuid4()}@example.com"
    async for client in _app_client(httpx.MockTransport(handle)):
        await _dev_login(client, email)
        await _connect_google(client, _token_response(FULL_CONNECTOR_SCOPE).json())

        sync = await client.post("/connected-accounts/google/sync", headers=CSRF_HEADERS)
        assert sync.status_code == 200
        body = sync.json()
        assert body["gmail_cursor_status"] == "incomplete"
        assert body["calendar_cursor_status"] == "incomplete"
        assert body["gmail_sync_complete"] is False
        assert body["calendar_sync_complete"] is False
        # No page token or provider error detail leaks into the response.
        assert "keep-going" not in str(body)
        assert "irrelevant" not in str(body)
        break


async def test_sync_route_reports_gmail_incomplete_instead_of_502_on_a_404_message() -> None:
    """Real sandbox finding (D38): a Gmail message id that 404s on fetch
    (observed live: a draft's underlying message superseded by a later edit)
    previously took down the whole sync route with a `502 Bad Gateway`. The
    route must now return `200` with the failure honestly counted in
    `gmail_incomplete`, never surfaced as a provider error."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return _token_response(FULL_CONNECTOR_SCOPE)
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                200,
                json={
                    "messages": [{"id": "gone", "threadId": "t0"}, {"id": "m1", "threadId": "t1"}]
                },
            )
        if request.url.path.endswith("/messages/gone"):
            return httpx.Response(404, json={"error": {"message": "Not Found"}})
        if request.url.path.endswith("/messages/m1"):
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
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "100"})
        if request.url.path.endswith("/events"):
            return httpx.Response(200, json={"items": [], "nextSyncToken": "sync-token-1"})
        raise AssertionError(f"unexpected request: {request.url.path}")

    email = f"gmail-incomplete-{uuid.uuid4()}@example.com"
    async for client in _app_client(httpx.MockTransport(handle)):
        await _dev_login(client, email)
        await _connect_google(client, _token_response(FULL_CONNECTOR_SCOPE).json())

        sync = await client.post("/connected-accounts/google/sync", headers=CSRF_HEADERS)
        assert sync.status_code == 200
        body = sync.json()
        assert body["gmail_incomplete"] == 1
        assert body["gmail_excluded"] == 0
        assert body["imported"] == 1
        break


async def test_real_gmail_execution_calls_exactly_drafts_create() -> None:
    """Section 6, "Real Gmail execution": approving/executing a
    create_gmail_draft proposal with a real, correctly-scoped Google account
    reports execution_mode="real" and calls exactly `users.drafts.create`
    then `users.drafts.get` (Stage 7 focused remediation: verification now
    independently re-fetches the created draft rather than trusting
    `drafts.create`'s own, frequently minimal, response) — never a send
    endpoint."""
    calls: list[httpx.Request] = []
    captured: dict[str, str] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return _token_response(FULL_CONNECTOR_SCOPE)
        if request.url.path == "/gmail/v1/users/me/drafts":
            calls.append(request)
            import json as jsonlib

            body = jsonlib.loads(request.content)
            captured["raw"] = body["message"]["raw"]
            return httpx.Response(
                200,
                json={"id": "draft-1", "message": {"id": "msg-1", "threadId": "thread-created"}},
            )
        if request.url.path == "/gmail/v1/users/me/drafts/draft-1":
            calls.append(request)
            assert request.url.params["format"] == "raw"
            # Gmail stores back exactly what was sent to create — this
            # proves the parser correctly round-trips our own encoder's
            # output, not just a hand-built test fixture.
            return httpx.Response(
                200,
                json={
                    "id": "draft-1",
                    "message": {"id": "msg-1", "threadId": "thread-actual", "raw": captured["raw"]},
                },
            )
        raise AssertionError(f"unexpected request: {request.url.path} (send endpoints forbidden)")

    email = f"gmail-exec-{uuid.uuid4()}@example.com"
    user_id = await _seed_google_sourced_proposals(email, granted_scopes=[])
    async for client in _app_client(httpx.MockTransport(handle)):
        await _dev_login(client, email)
        await _connect_google(client, _token_response(FULL_CONNECTOR_SCOPE).json())

        proposals = await client.get("/action-proposals")
        draft = next(
            p for p in proposals.json()["proposals"] if p["action_type"] == "create_gmail_draft"
        )
        assert draft["execution_mode"] == "real"

        approve = await client.post(
            f"/action-proposals/{draft['id']}/approve",
            json={
                "expected_version": draft["version"],
                "action_type": "create_gmail_draft",
                "displayed_payload_hash": draft["payload_hash"],
                "displayed_execution_context_hash": draft["execution_context_hash"],
            },
            headers=CSRF_HEADERS,
        )
        assert approve.status_code == 200
        assert approve.json()["execution_mode"] == "real"

        execute = await client.post(
            f"/action-proposals/{draft['id']}/execute", headers=CSRF_HEADERS
        )
        assert execute.status_code == 200
        execution = execute.json()["execution"]
        assert execution["execution_mode"] == "real"
        assert execution["effective_status"] == "succeeded"
        assert execution["result"]["draft_id"] == "draft-1"

        # Replay must not call Google again.
        replay = await client.post(f"/action-proposals/{draft['id']}/execute", headers=CSRF_HEADERS)
        assert replay.status_code == 200
        assert replay.json()["execution"]["id"] == execution["id"]
        break

    assert len(calls) == 2  # create, then the independent verification fetch
    assert all(not call.url.path.endswith("/send") for call in calls)
    del user_id


async def test_real_calendar_execution_calls_exactly_events_insert_with_send_updates_none() -> None:
    """Section 6, "Real Calendar execution": exactly one `events.insert`
    call, `sendUpdates=none` present, no update/patch/delete method used."""
    insert_calls: list[httpx.Request] = []
    stored_event: dict = {}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return _token_response(FULL_CONNECTOR_SCOPE)
        if request.method == "POST" and request.url.path.endswith("/events"):
            insert_calls.append(request)
            import json as jsonlib

            body = jsonlib.loads(request.content)
            # Store exactly what was submitted, matching whatever the
            # approved proposal's payload actually is — the point of this
            # test is proving the transport call shape, not a fixed fixture.
            stored_event.update(
                {
                    "id": "event-1",
                    "status": "confirmed",
                    "summary": body["summary"],
                    "start": body["start"],
                    "end": body["end"],
                    "attendees": body.get("attendees", []),
                }
            )
            return httpx.Response(200, json={"id": "event-1"})
        if request.method == "GET" and request.url.path.endswith("/events/event-1"):
            # The independent D40 verification re-fetch reads the stored event.
            return httpx.Response(200, json=stored_event)
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    email = f"cal-exec-{uuid.uuid4()}@example.com"
    await _seed_google_sourced_proposals(email, granted_scopes=[])
    async for client in _app_client(httpx.MockTransport(handle)):
        await _dev_login(client, email)
        await _connect_google(client, _token_response(FULL_CONNECTOR_SCOPE).json())

        proposals = await client.get("/action-proposals")
        event = next(
            p for p in proposals.json()["proposals"] if p["action_type"] == "create_calendar_event"
        )
        assert event["execution_mode"] == "real"

        await client.post(
            f"/action-proposals/{event['id']}/approve",
            json={
                "expected_version": event["version"],
                "action_type": "create_calendar_event",
                "displayed_payload_hash": event["payload_hash"],
                "displayed_execution_context_hash": event["execution_context_hash"],
            },
            headers=CSRF_HEADERS,
        )
        execute = await client.post(
            f"/action-proposals/{event['id']}/execute", headers=CSRF_HEADERS
        )
        assert execute.status_code == 200
        execution = execute.json()["execution"]
        assert execution["execution_mode"] == "real"
        assert execution["effective_status"] == "succeeded"
        assert execution["result"]["guest_notifications"] == "off"
        break

    assert len(insert_calls) == 1
    assert insert_calls[0].url.params["sendUpdates"] == "none"
    assert insert_calls[0].method == "POST"


async def test_simulation_path_reports_simulation_and_never_calls_google() -> None:
    """Section 6, "Simulation path": with no Google account connected at
    all, the proposal (via the synthetic demo account) reports
    execution_mode="simulation" and executing it makes no Google HTTP call —
    the app in this test has no Google client configured whatsoever."""

    def handle(request: httpx.Request) -> httpx.Response:  # pragma: no cover -- must never fire
        raise AssertionError(f"unexpected Google HTTP call: {request.url.path}")

    email = f"sim-path-{uuid.uuid4()}@example.com"
    await _seed_synthetic_proposals(email)
    settings = _test_settings("development")  # GOOGLE_OAUTH_ENABLED is false by default
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _dev_login(client, email)
            proposals = await client.get("/action-proposals")
            draft = next(
                p for p in proposals.json()["proposals"] if p["action_type"] == "create_gmail_draft"
            )
            assert draft["execution_mode"] == "simulation"
            assert draft["simulation_only"] is True

            await client.post(
                f"/action-proposals/{draft['id']}/approve",
                json={
                    "expected_version": draft["version"],
                    "action_type": "create_gmail_draft",
                    "displayed_payload_hash": draft["payload_hash"],
                    "displayed_execution_context_hash": draft["execution_context_hash"],
                },
                headers=CSRF_HEADERS,
            )
            execute = await client.post(
                f"/action-proposals/{draft['id']}/execute", headers=CSRF_HEADERS
            )
            assert execute.status_code == 200
            execution = execute.json()["execution"]
            assert execution["execution_mode"] == "simulation"
            assert execution["simulation_only"] is True
            assert execution["result"]["status"] == "simulated"
    # `handle` above is never wired to this app at all (no Google client
    # constructed when GOOGLE_OAUTH_ENABLED=false), so any real call would
    # have raised inside httpx with a connection error, not reached `handle`.


async def test_transport_timeout_during_real_execution_is_immediately_uncertain() -> None:
    """Section 6, "Transport failures": a raw connection error during the
    real Gmail call becomes an immediate `uncertain` outcome — not a generic
    500, not a silent success, and never retried automatically."""
    call_count = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return _token_response(FULL_CONNECTOR_SCOPE)
        if request.url.path.endswith("/drafts"):
            call_count["n"] += 1
            raise httpx.ConnectError("network down", request=request)
        raise AssertionError(f"unexpected request: {request.url.path}")

    email = f"timeout-exec-{uuid.uuid4()}@example.com"
    await _seed_google_sourced_proposals(email, granted_scopes=[])
    async for client in _app_client(httpx.MockTransport(handle)):
        await _dev_login(client, email)
        await _connect_google(client, _token_response(FULL_CONNECTOR_SCOPE).json())

        proposals = await client.get("/action-proposals")
        draft = next(
            p for p in proposals.json()["proposals"] if p["action_type"] == "create_gmail_draft"
        )
        await client.post(
            f"/action-proposals/{draft['id']}/approve",
            json={
                "expected_version": draft["version"],
                "action_type": "create_gmail_draft",
                "displayed_payload_hash": draft["payload_hash"],
                "displayed_execution_context_hash": draft["execution_context_hash"],
            },
            headers=CSRF_HEADERS,
        )

        execute = await client.post(
            f"/action-proposals/{draft['id']}/execute", headers=CSRF_HEADERS
        )
        assert execute.status_code == 200  # never a generic 500
        execution = execute.json()["execution"]
        assert execution["effective_status"] == "uncertain"
        assert execution["execution_mode"] == "real"
        assert "ConnectError" not in str(execution["result"])  # no raw exception text leaked
        assert "token" not in str(execution["result"]).lower()

        # Replay must not call Google again, and must return the same
        # uncertain execution rather than retrying.
        replay = await client.post(f"/action-proposals/{draft['id']}/execute", headers=CSRF_HEADERS)
        assert replay.status_code == 200
        assert replay.json()["execution"]["id"] == execution["id"]
        assert replay.json()["execution"]["effective_status"] == "uncertain"
        break

    assert call_count["n"] == 1
