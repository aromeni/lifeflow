"""Stage 7 focused remediation: the post-durability-commit TOCTOU race.

The second independent review found that `ActionPolicyEngine.validate_
execution` re-verified the approved execution context BEFORE the durable
`pending` `ActionExecution` commit, but the real Google token was then
selected AFTERWARDS through a fresh `(user, provider)` lookup that never
re-checked the approved account identity, `authorisation_revision`, or
scope. Between the commit (which releases every lock the transaction held)
and the real Gmail/Calendar HTTP call, a concurrent disconnect/reconnect or
scope change could go undetected.

Every test here drives the REAL production objects — `ActionProposalService`,
`GoogleExecutorRegistry`, `GoogleGmailDraftExecutor`/
`GoogleCalendarEventExecutor`, `GoogleTokenService` — against a mocked Google
HTTP transport that raises on any Gmail/Calendar write call, so a bug that
lets execution slip past the fix would fail the test via that assertion, not
merely via a status-code check. `CountingExecutor` (used elsewhere for
pre-commit-only scenarios) never appears here.

The race itself is deterministic, not timing-based: `ActionProposalService`'s
`post_commit_hook` fires exactly once, synchronously within `execute()`,
immediately after the durability commit and before the executor runs. Each
test's hook opens a genuinely independent PostgreSQL session/engine, performs
the concurrent mutation, and commits it — by the time the hook returns and
`execute()` resumes, the mutation is durably visible to the next query on the
main session (Postgres READ COMMITTED). No `asyncio.gather`, no sleeps.
"""

import base64
import json
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL, _test_settings
from tests.test_action_proposals import NOW, _approve, _proposal, _seed_google_sourced_proposals
from tests.test_google_route_integration import (
    FULL_CONNECTOR_SCOPE,
    GOOGLE_SETTINGS_OVERRIDES,
    _connect_google,
    _dev_login,
    _token_response,
)
from tests.test_google_route_integration import (
    _seed_google_sourced_proposals as _seed_google_sourced_route_proposals,
)

from lifeflow_api.accounts import ConnectedAccountService, GoogleTokenService
from lifeflow_api.action_executors import (
    GoogleCalendarEventExecutor,
    GoogleExecutorRegistry,
    GoogleGmailDraftExecutor,
)
from lifeflow_api.action_proposal_service import ActionProposalService, ProposalConflictError
from lifeflow_api.google.calendar_client import CalendarEventClient
from lifeflow_api.google.gmail_client import GmailDraftClient
from lifeflow_api.google.oauth import GoogleOAuthClient
from lifeflow_api.google_scopes import CALENDAR_EVENTS_SCOPE, GMAIL_COMPOSE_SCOPE
from lifeflow_api.main import create_app
from lifeflow_api.models import ActionType, ExecutionOutcome, ProposalStatus
from lifeflow_api.repositories import ActionExecutionRepository, ConnectedAccountRepository
from lifeflow_api.security.token_cipher import AesGcmTokenCipher

pytestmark = pytest.mark.integration


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


def _refusing_transport(*, allow_token: bool = True) -> httpx.MockTransport:
    """Every non-`/token` call raises — proves the executor never reaches
    the real Gmail/Calendar write endpoint once the race is caught."""

    def handle(request: httpx.Request) -> httpx.Response:
        if allow_token and request.url.path == "/token":
            return _token_response(FULL_CONNECTOR_SCOPE)
        raise AssertionError(
            f"unexpected Google HTTP call after the race should have blocked execution: "
            f"{request.url.path}"
        )

    return httpx.MockTransport(handle)


def _google_registry(
    session: AsyncSession,
    user_id: uuid.UUID,
    cipher: AesGcmTokenCipher,
    transport: httpx.MockTransport,
) -> tuple[GoogleExecutorRegistry, GoogleTokenService]:
    mock_http = httpx.AsyncClient(transport=transport)
    oauth = GoogleOAuthClient(mock_http)
    tokens = GoogleTokenService(
        session,
        user_id,
        cipher,
        oauth,
        client_id="cid",
        client_secret="secret",
        now_factory=lambda: NOW,
    )
    registry = GoogleExecutorRegistry(
        {
            ActionType.create_gmail_draft: GoogleGmailDraftExecutor(
                GmailDraftClient(mock_http), tokens
            ),
            ActionType.create_calendar_event: GoogleCalendarEventExecutor(
                CalendarEventClient(mock_http), tokens
            ),
        }
    )
    return registry, tokens


async def _grant_real_tokens(
    session: AsyncSession, user_id: uuid.UUID, cipher: AesGcmTokenCipher, *, scopes: list[str]
) -> None:
    """Gives the account real (encrypted, unexpired) credentials so token
    acquisition reaches the row-locked exact-account check instead of
    failing earlier on "no refresh token stored". Reuses the same
    `(user_id, "google")` row `_seed_google_sourced_proposals` already
    created, bumping `authorisation_revision` exactly like a real OAuth
    callback would."""
    await ConnectedAccountService(session, user_id, cipher).store_tokens(
        provider="google",
        access_token="access-initial",  # pragma: allowlist secret
        refresh_token="refresh-initial",  # pragma: allowlist secret
        granted_scopes=scopes,
        expires_at=NOW + timedelta(hours=1),
    )
    await session.flush()


async def _reconnect(user_id: uuid.UUID, cipher: AesGcmTokenCipher, *, scopes: list[str]) -> None:
    """Simulates a real reconnect through the OAuth callback path (via an
    independent engine/session — a genuinely separate transaction) —
    bumps `authorisation_revision` exactly like `connected_accounts.py`'s
    callback route does."""
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as racing:
            await ConnectedAccountService(racing, user_id, cipher).store_tokens(
                provider="google",
                access_token="access-after-race",  # pragma: allowlist secret
                refresh_token="refresh-after-race",  # pragma: allowlist secret
                granted_scopes=scopes,
                expires_at=NOW + timedelta(hours=1),
            )
            await racing.commit()
    finally:
        await engine.dispose()


async def _remove_scope(user_id: uuid.UUID) -> None:
    """Simulates a scope change racing execution, via an independent
    engine/session."""
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as racing:
            account = await ConnectedAccountRepository(racing, user_id).get_by_provider("google")
            assert account is not None
            account.granted_scopes = []
            await racing.commit()
    finally:
        await engine.dispose()


async def test_reconnect_after_pending_commit_blocks_gmail_execution(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    """Required race sequence (focused remediation §6, steps 1-6), Gmail."""
    user, account, proposals = await _seed_google_sourced_proposals(
        session, granted_scopes=[GMAIL_COMPOSE_SCOPE]
    )
    await _grant_real_tokens(session, user.id, cipher, scopes=[GMAIL_COMPOSE_SCOPE])
    draft = _proposal(proposals, ActionType.create_gmail_draft)

    approve_registry, _ = _google_registry(session, user.id, cipher, _refusing_transport())
    approve_service = ActionProposalService(
        session, user.id, google_executors=approve_registry, now_factory=lambda: NOW
    )
    approved = await _approve(approve_service, draft, session=session, user=user)
    approved_revision = approved.approved_authorisation_revision
    assert approved_revision is not None

    async def barrier() -> None:
        # Step 4: disconnect+reconnect in another transaction — revision
        # N -> N+1 — while `execute()` is paused between its durability
        # commit and token acquisition.
        await _reconnect(user.id, cipher, scopes=[GMAIL_COMPOSE_SCOPE])

    execute_registry, _ = _google_registry(session, user.id, cipher, _refusing_transport())
    execute_service = ActionProposalService(
        session,
        user.id,
        google_executors=execute_registry,
        now_factory=lambda: NOW,
        post_commit_hook=barrier,
    )
    proposal_after, execution = await execute_service.execute(draft.id)

    assert execution.outcome == ExecutionOutcome.failed
    assert execution.error_code == "approval_context_changed"
    assert proposal_after.status == ProposalStatus.failed
    assert "attempted" in execution.result_json["message"].lower()

    refreshed_account = await ConnectedAccountRepository(session, user.id).get(account.id)
    assert refreshed_account is not None
    assert refreshed_account.authorisation_revision == approved_revision + 1

    # Replay must not make any provider call either — the early replay
    # guard returns the existing (failed) execution without re-entering
    # the executor at all.
    replay_registry, _ = _google_registry(session, user.id, cipher, _refusing_transport())
    replay_service = ActionProposalService(
        session, user.id, google_executors=replay_registry, now_factory=lambda: NOW
    )
    _proposal_replay, execution_replay = await replay_service.execute(draft.id)
    assert execution_replay.id == execution.id
    assert execution_replay.outcome == ExecutionOutcome.failed


async def test_scope_removed_after_pending_commit_blocks_gmail_execution(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    """The equivalent scope-removal race (focused remediation §6)."""
    user, account, proposals = await _seed_google_sourced_proposals(
        session, granted_scopes=[GMAIL_COMPOSE_SCOPE]
    )
    await _grant_real_tokens(session, user.id, cipher, scopes=[GMAIL_COMPOSE_SCOPE])
    draft = _proposal(proposals, ActionType.create_gmail_draft)

    approve_registry, _ = _google_registry(session, user.id, cipher, _refusing_transport())
    approve_service = ActionProposalService(
        session, user.id, google_executors=approve_registry, now_factory=lambda: NOW
    )
    await _approve(approve_service, draft, session=session, user=user)

    async def barrier() -> None:
        await _remove_scope(user.id)

    execute_registry, _ = _google_registry(session, user.id, cipher, _refusing_transport())
    execute_service = ActionProposalService(
        session,
        user.id,
        google_executors=execute_registry,
        now_factory=lambda: NOW,
        post_commit_hook=barrier,
    )
    proposal_after, execution = await execute_service.execute(draft.id)

    assert execution.outcome == ExecutionOutcome.failed
    assert execution.error_code == "approval_context_changed"
    assert proposal_after.status == ProposalStatus.failed

    refreshed_account = await ConnectedAccountRepository(session, user.id).get(account.id)
    assert refreshed_account is not None
    assert refreshed_account.granted_scopes == []


async def test_reconnect_after_pending_commit_blocks_calendar_execution(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    """Calendar side of the same race — proves the fix is not Gmail-only."""
    user, account, proposals = await _seed_google_sourced_proposals(
        session, granted_scopes=[CALENDAR_EVENTS_SCOPE]
    )
    await _grant_real_tokens(session, user.id, cipher, scopes=[CALENDAR_EVENTS_SCOPE])
    event = _proposal(proposals, ActionType.create_calendar_event)

    approve_registry, _ = _google_registry(session, user.id, cipher, _refusing_transport())
    approve_service = ActionProposalService(
        session, user.id, google_executors=approve_registry, now_factory=lambda: NOW
    )
    approved = await _approve(approve_service, event, session=session, user=user)
    approved_revision = approved.approved_authorisation_revision
    assert approved_revision is not None

    async def barrier() -> None:
        await _reconnect(user.id, cipher, scopes=[CALENDAR_EVENTS_SCOPE])

    execute_registry, _ = _google_registry(session, user.id, cipher, _refusing_transport())
    execute_service = ActionProposalService(
        session,
        user.id,
        google_executors=execute_registry,
        now_factory=lambda: NOW,
        post_commit_hook=barrier,
    )
    proposal_after, execution = await execute_service.execute(event.id)

    assert execution.outcome == ExecutionOutcome.failed
    assert execution.error_code == "approval_context_changed"
    assert proposal_after.status == ProposalStatus.failed

    refreshed_account = await ConnectedAccountRepository(session, user.id).get(account.id)
    assert refreshed_account is not None
    assert refreshed_account.authorisation_revision == approved_revision + 1


async def test_routine_refresh_during_execution_preparation_succeeds(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    """Regression: an access token that happens to need refreshing during
    the post-commit preparation phase (unchanged revision) must still
    succeed — the fix must not turn every execution into a false
    `approval_context_changed`."""
    user, _account, proposals = await _seed_google_sourced_proposals(
        session, granted_scopes=[GMAIL_COMPOSE_SCOPE]
    )
    await ConnectedAccountService(session, user.id, cipher).store_tokens(
        provider="google",
        access_token="access-expiring",  # pragma: allowlist secret
        refresh_token="refresh-good",  # pragma: allowlist secret
        granted_scopes=[GMAIL_COMPOSE_SCOPE],
        expires_at=NOW + timedelta(seconds=30),  # inside the refresh safety margin
    )
    await session.flush()
    draft = _proposal(proposals, ActionType.create_gmail_draft)

    captured: dict[str, str] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return _token_response(GMAIL_COMPOSE_SCOPE)
        if request.url.path.endswith("/drafts"):
            body = json.loads(request.content)
            captured["raw"] = body["message"]["raw"]
            return httpx.Response(
                200, json={"id": "draft-1", "message": {"id": "msg-1", "threadId": "thread-1"}}
            )
        if request.url.path.endswith("/drafts/draft-1"):
            # Independent re-fetch (Stage 7 focused remediation) — Gmail
            # stores back exactly what was sent to create.
            return httpx.Response(
                200,
                json={
                    "id": "draft-1",
                    "message": {"id": "msg-1", "threadId": "thread-1", "raw": captured["raw"]},
                },
            )
        raise AssertionError(f"unexpected request: {request.url.path}")

    registry, _ = _google_registry(session, user.id, cipher, httpx.MockTransport(handle))
    approve_service = ActionProposalService(
        session, user.id, google_executors=registry, now_factory=lambda: NOW
    )
    await _approve(approve_service, draft, session=session, user=user)

    execute_service = ActionProposalService(
        session, user.id, google_executors=registry, now_factory=lambda: NOW
    )
    _proposal_after, execution = await execute_service.execute(draft.id)

    assert execution.outcome == ExecutionOutcome.succeeded
    account_after = await ConnectedAccountRepository(session, user.id).get_by_provider("google")
    assert account_after is not None
    assert account_after.authorisation_revision == 2  # unchanged by the refresh


async def test_reconnect_before_approval_produces_new_context_normally(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    """Sanity check: a reconnect that happens BEFORE approval is simply
    the new baseline — approval captures whatever revision is current at
    that moment, and nothing is blocked."""
    user, _account, proposals = await _seed_google_sourced_proposals(
        session, granted_scopes=[GMAIL_COMPOSE_SCOPE]
    )
    await _grant_real_tokens(session, user.id, cipher, scopes=[GMAIL_COMPOSE_SCOPE])
    draft = _proposal(proposals, ActionType.create_gmail_draft)

    registry, _ = _google_registry(session, user.id, cipher, _refusing_transport())
    service = ActionProposalService(
        session, user.id, google_executors=registry, now_factory=lambda: NOW
    )
    approved = await _approve(service, draft, session=session, user=user)
    assert approved.status == ProposalStatus.approved
    assert approved.approved_authorisation_revision == 2


async def test_reconnect_after_approval_before_execute_caught_by_precommit_check(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    """The EXISTING pre-commit check (`validate_execution`, before any
    pending row is created) still catches a reconnect that happens well
    before `execute()` is even called — proving the new post-commit layer
    is additive, not a replacement."""
    user, _account, proposals = await _seed_google_sourced_proposals(
        session, granted_scopes=[GMAIL_COMPOSE_SCOPE]
    )
    await _grant_real_tokens(session, user.id, cipher, scopes=[GMAIL_COMPOSE_SCOPE])
    draft = _proposal(proposals, ActionType.create_gmail_draft)

    registry, _ = _google_registry(session, user.id, cipher, _refusing_transport())
    service = ActionProposalService(
        session, user.id, google_executors=registry, now_factory=lambda: NOW
    )
    await _approve(service, draft, session=session, user=user)
    # Commit before the independent `_reconnect()` engine touches the same
    # account row — otherwise it would block indefinitely waiting for this
    # session's still-open transaction to release the row it updated.
    await session.commit()

    await _reconnect(user.id, cipher, scopes=[GMAIL_COMPOSE_SCOPE])

    with pytest.raises(ProposalConflictError) as exc:
        await service.execute(draft.id)
    assert exc.value.code == "approval_context_changed"
    # No durable execution row was ever created for this pre-commit denial.
    existing = await ActionExecutionRepository(session, user.id).get_by_proposal(draft.id)
    assert existing is None


async def test_http_route_level_reconnect_race_blocks_gmail_execution() -> None:
    """One full route-level path (focused remediation §6): the same race,
    driven through `create_app()` -> the real `/execute` route ->
    `GoogleExecutorRegistry` -> `GoogleGmailDraftExecutor` ->
    `GoogleTokenService`, with the deterministic barrier wired through
    `app.state.action_execution_post_commit_hook` (a test-only seam,
    `None`/no-op in every real deployment)."""
    email = f"http-race-{uuid.uuid4()}@example.com"
    user_id = await _seed_google_sourced_route_proposals(
        email, granted_scopes=[GMAIL_COMPOSE_SCOPE]
    )

    settings = _test_settings("development").model_copy(update=GOOGLE_SETTINGS_OVERRIDES)
    app = create_app(settings)
    mock_http = httpx.AsyncClient(transport=_refusing_transport())
    app.state.google_oauth_client = GoogleOAuthClient(mock_http)
    app.state.gmail_client = GmailDraftClient(mock_http)
    app.state.calendar_client = CalendarEventClient(mock_http)

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _dev_login(client, email)
            await _connect_google(client, _token_response(FULL_CONNECTOR_SCOPE).json())

            proposals = await client.get("/action-proposals")
            draft = next(
                p for p in proposals.json()["proposals"] if p["action_type"] == "create_gmail_draft"
            )
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

            async def barrier() -> None:
                cipher = app.state.token_cipher
                engine = create_async_engine(TEST_DB_URL)
                try:
                    maker = async_sessionmaker(engine, expire_on_commit=False)
                    async with maker() as racing:
                        await ConnectedAccountService(racing, user_id, cipher).store_tokens(
                            provider="google",
                            access_token="access-after-race",  # pragma: allowlist secret
                            refresh_token="refresh-after-race",  # pragma: allowlist secret
                            granted_scopes=[GMAIL_COMPOSE_SCOPE],
                            expires_at=datetime.now(UTC) + timedelta(hours=1),
                        )
                        await racing.commit()
                finally:
                    await engine.dispose()

            app.state.action_execution_post_commit_hook = barrier

            execute = await client.post(
                f"/action-proposals/{draft['id']}/execute", headers=CSRF_HEADERS
            )
            assert execute.status_code == 200  # never a raw 500 or silent success
            execution = execute.json()["execution"]
            assert execution["effective_status"] == "failed"
            assert execution["error_code"] == "approval_context_changed"

            replay = await client.post(
                f"/action-proposals/{draft['id']}/execute", headers=CSRF_HEADERS
            )
            assert replay.status_code == 200
            assert replay.json()["execution"]["id"] == execution["id"]
    # `_refusing_transport()`'s handler raises on any non-/token call — a
    # real drafts.create request would have failed the test via that
    # assertion, propagating as a 500 the test would also have caught.
