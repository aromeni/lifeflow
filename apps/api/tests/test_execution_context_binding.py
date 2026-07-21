"""Stage 7 remediation, independent-review blocker #1: approval-bound
execution context. Each test below maps directly to one of the nine
required approval-context scenarios in the remediation brief.
"""

import asyncio
import base64
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
from tests.helpers import TIMEZONE, demo_source_items
from tests.test_action_proposals import (
    NOW,
    CountingExecutor,
    _approve,
    _proposal,
    _seed_google_sourced_proposals,
    _seed_proposals,
    _service,
)
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

from lifeflow_api.accounts import ConnectedAccountService
from lifeflow_api.action_executors import GoogleExecutorRegistry
from lifeflow_api.action_proposal_service import ActionProposalService, ProposalConflictError
from lifeflow_api.brief_composition import BriefService
from lifeflow_api.execution_context import resolve_execution_context
from lifeflow_api.google.calendar_client import CalendarEventClient
from lifeflow_api.google.gmail_client import GmailDraftClient
from lifeflow_api.google.oauth import GoogleOAuthClient
from lifeflow_api.google_scopes import GMAIL_COMPOSE_SCOPE
from lifeflow_api.main import create_app
from lifeflow_api.models import AccountStatus, ActionType, ConnectedAccount, ExecutionMode, User
from lifeflow_api.repositories import ConnectedAccountRepository, SourceItemRepository
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


async def _reconnect(session: AsyncSession, user_id: uuid.UUID, cipher: AesGcmTokenCipher) -> None:
    """Simulates a real reconnect through the OAuth callback path — bumps
    `authorisation_revision` exactly like `connected_accounts.py`'s callback
    route does via `ConnectedAccountService.store_tokens`."""
    await ConnectedAccountService(session, user_id, cipher).store_tokens(
        provider="google",
        access_token="new-access-token",  # pragma: allowlist secret
        refresh_token="new-refresh-token",  # pragma: allowlist secret
        granted_scopes=[GMAIL_COMPOSE_SCOPE],
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await session.flush()


async def test_scenario_1_synthetic_approval_stays_simulation_after_connecting_google() -> None:
    """1. Approve simulation -> connect Google -> execution is blocked [from
    using Google] and no Google request occurs."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return _token_response(FULL_CONNECTOR_SCOPE)
        raise AssertionError(f"unexpected Google HTTP call: {request.url.path} (must never fire)")

    email = f"scenario1-{uuid.uuid4()}@example.com"
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as seed_session:
            user = User(email=email, display_name="Scenario 1")
            seed_session.add(user)
            await seed_session.flush()
            seed_session.add(
                ConnectedAccount(
                    user_id=user.id,
                    provider="synthetic",
                    granted_scopes=["demo"],
                    status=AccountStatus.active,
                )
            )
            # This scenario approves/executes through the REAL app (wall
            # clock), so seeding anchors to now — a frozen reference would
            # give every proposal a fixed absolute expiry that wall time
            # eventually passes.
            live_reference = datetime.now(UTC)
            seed_session.add_all(await demo_source_items(user.id, anchor=live_reference.date()))
            await seed_session.flush()
            await BriefService(seed_session, user.id).generate(
                timezone=TIMEZONE, reference=live_reference
            )
            await seed_session.commit()
    finally:
        await engine.dispose()

    settings = _test_settings("development").model_copy(update=GOOGLE_SETTINGS_OVERRIDES)
    app = create_app(settings)
    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    app.state.google_oauth_client = GoogleOAuthClient(mock_http)
    app.state.gmail_client = GmailDraftClient(mock_http)
    app.state.calendar_client = CalendarEventClient(mock_http)

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _dev_login(client, email)
            proposals = (await client.get("/action-proposals")).json()["proposals"]
            draft = next(p for p in proposals if p["action_type"] == "create_gmail_draft")
            assert draft["execution_mode"] == "simulation"

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
            assert approve.json()["execution_mode"] == "simulation"

            # Connect Google AFTER approval — must never upgrade this proposal.
            await _connect_google(client, _token_response(FULL_CONNECTOR_SCOPE).json())

            refreshed = await client.get(f"/action-proposals/{draft['id']}")
            assert refreshed.json()["execution_mode"] == "simulation"
            assert refreshed.json()["execution_context_changed"] is False

            execute = await client.post(
                f"/action-proposals/{draft['id']}/execute", headers=CSRF_HEADERS
            )
            assert execute.status_code == 200
            execution = execute.json()["execution"]
            assert execution["execution_mode"] == "simulation"
            assert execution["result"]["status"] == "simulated"
    # `handle` raises on any request other than /token — a real Gmail call
    # would have failed the test via that assertion.


async def test_scenario_2_real_approval_blocked_when_google_disconnected(
    session: AsyncSession,
) -> None:
    """2. Approve real -> disconnect Google while synthetic account remains
    -> execution is blocked and no simulation occurs."""
    user, account, proposals = await _seed_google_sourced_proposals(
        session, granted_scopes=[GMAIL_COMPOSE_SCOPE]
    )
    draft = _proposal(proposals, ActionType.create_gmail_draft)
    executor = CountingExecutor()
    service = _service(
        session,
        user,
        google_executors=GoogleExecutorRegistry({ActionType.create_gmail_draft: executor}),
    )
    approved = await _approve(service, draft, session=session, user=user)
    assert approved.approved_execution_mode == "real"

    account.status = AccountStatus.disconnected
    await session.flush()

    with pytest.raises(ProposalConflictError) as exc:
        await service.execute(draft.id)
    assert exc.value.code == "approval_context_changed"
    assert executor.calls == 0  # no simulation fallback, no real call either


async def test_scenario_3_and_8_reconnected_account_blocks_execution(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    """3/8. Approve using Google account/revision A -> reconnect (which this
    product represents as a revision bump on the same account row, since
    OAuth alone can't distinguish "the same Google account re-consenting"
    from "a different Google account connecting") -> execution is blocked;
    a stale approval can never ride a later, different authorisation."""
    user, account, proposals = await _seed_google_sourced_proposals(
        session, granted_scopes=[GMAIL_COMPOSE_SCOPE]
    )
    draft = _proposal(proposals, ActionType.create_gmail_draft)
    executor = CountingExecutor()
    service = _service(
        session,
        user,
        google_executors=GoogleExecutorRegistry({ActionType.create_gmail_draft: executor}),
    )
    approved = await _approve(service, draft, session=session, user=user)
    assert approved.approved_authorisation_revision == 1

    await _reconnect(session, user.id, cipher)
    refreshed_account = await ConnectedAccountRepository(session, user.id).get(account.id)
    assert refreshed_account is not None
    assert refreshed_account.authorisation_revision == 2

    with pytest.raises(ProposalConflictError) as exc:
        await service.execute(draft.id)
    assert exc.value.code == "approval_context_changed"
    assert executor.calls == 0


async def test_scenario_4_routine_token_refresh_does_not_invalidate_approval(
    session: AsyncSession,
) -> None:
    """4. Approve real -> routine access-token refresh WITHOUT an
    authorisation-revision change -> execution remains valid."""
    user, account, proposals = await _seed_google_sourced_proposals(
        session, granted_scopes=[GMAIL_COMPOSE_SCOPE]
    )
    draft = _proposal(proposals, ActionType.create_gmail_draft)
    executor = CountingExecutor()
    service = _service(
        session,
        user,
        google_executors=GoogleExecutorRegistry({ActionType.create_gmail_draft: executor}),
    )
    await _approve(service, draft, session=session, user=user)

    # A routine access-token refresh touches only the token/expiry fields —
    # never `authorisation_revision` (that's `store_tokens`'s job, reached
    # only from the OAuth callback, never from a silent refresh).
    account.expires_at = datetime.now(UTC) - timedelta(minutes=5)
    await session.flush()
    assert account.authorisation_revision == 1

    _proposal_after, execution = await service.execute(draft.id)
    assert execution.execution_mode == "real"
    assert executor.calls == 1


async def test_scenario_5_scope_removed_after_approval_blocks_execution(
    session: AsyncSession,
) -> None:
    """5. Scope removed after approval -> execution is blocked."""
    user, account, proposals = await _seed_google_sourced_proposals(
        session, granted_scopes=[GMAIL_COMPOSE_SCOPE]
    )
    draft = _proposal(proposals, ActionType.create_gmail_draft)
    executor = CountingExecutor()
    service = _service(
        session,
        user,
        google_executors=GoogleExecutorRegistry({ActionType.create_gmail_draft: executor}),
    )
    await _approve(service, draft, session=session, user=user)

    account.granted_scopes = []  # scope revoked/changed out from under the approval
    await session.flush()

    with pytest.raises(ProposalConflictError) as exc:
        await service.execute(draft.id)
    assert exc.value.code == "approval_context_changed"
    assert executor.calls == 0


async def test_scenario_6_stale_preview_returns_controlled_409_on_approve() -> None:
    """6. Execution context changes between preview and approval -> approval
    returns a controlled stale-context 409 through the real HTTP route."""
    email = f"scenario6-{uuid.uuid4()}@example.com"
    await _seed_google_sourced_route_proposals(email, granted_scopes=[GMAIL_COMPOSE_SCOPE])

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return _token_response(FULL_CONNECTOR_SCOPE)
        raise AssertionError(f"unexpected Google HTTP call: {request.url.path}")

    settings = _test_settings("development").model_copy(update=GOOGLE_SETTINGS_OVERRIDES)
    app = create_app(settings)
    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    app.state.google_oauth_client = GoogleOAuthClient(mock_http)
    app.state.gmail_client = GmailDraftClient(mock_http)
    app.state.calendar_client = CalendarEventClient(mock_http)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await _dev_login(client, email)
            await _connect_google(client, _token_response(FULL_CONNECTOR_SCOPE).json())

            preview = (await client.get("/action-proposals")).json()["proposals"]
            draft = next(p for p in preview if p["action_type"] == "create_gmail_draft")
            stale_context_hash = draft["execution_context_hash"]

            # The context changes (reconnect) after the preview was fetched
            # but before the user clicks approve.
            await _connect_google(client, _token_response(FULL_CONNECTOR_SCOPE).json())

            approve = await client.post(
                f"/action-proposals/{draft['id']}/approve",
                json={
                    "expected_version": draft["version"],
                    "action_type": "create_gmail_draft",
                    "displayed_payload_hash": draft["payload_hash"],
                    "displayed_execution_context_hash": stale_context_hash,
                },
                headers=CSRF_HEADERS,
            )
            assert approve.status_code == 409
            assert approve.json()["error"]["code"] == "stale_execution_context"


async def test_scenario_7_synthetic_source_stays_simulation_even_with_google_connected(
    session: AsyncSession,
) -> None:
    """7. Synthetic-source proposals remain simulation even when Google is
    connected — a direct unit-level check on the resolver itself."""
    user, proposals = await _seed_proposals(session)
    draft = _proposal(proposals, ActionType.create_gmail_draft)

    # A fully-scoped, active Google account exists for this user — but the
    # proposal's evidence never referenced it.
    google_account = ConnectedAccount(
        user_id=user.id,
        provider="google",
        granted_scopes=[GMAIL_COMPOSE_SCOPE],
        status=AccountStatus.active,
    )
    session.add(google_account)
    await session.flush()

    accounts = await ConnectedAccountRepository(session, user.id).list()
    evidence_sources = await SourceItemRepository(session, user.id).list_by_external_ids(
        list(draft.source_refs)
    )
    context = resolve_execution_context(
        ActionType.create_gmail_draft, accounts=accounts, evidence_sources=evidence_sources
    )
    assert context.mode is ExecutionMode.simulation
    assert context.provider == "synthetic"


async def test_scenario_9_concurrent_disconnect_never_yields_undisclosed_provider_call(
    session: AsyncSession,
) -> None:
    """9. A concurrent account-state change racing an execute() call can
    never produce an undisclosed provider call: the outcome is always
    either the disclosed real call or a controlled block — never a silent
    downgrade to simulation and never an unhandled error."""
    user, account, proposals = await _seed_google_sourced_proposals(
        session, granted_scopes=[GMAIL_COMPOSE_SCOPE]
    )
    draft = _proposal(proposals, ActionType.create_gmail_draft)
    executor = CountingExecutor()
    approve_service = _service(
        session,
        user,
        google_executors=GoogleExecutorRegistry({ActionType.create_gmail_draft: executor}),
    )
    await _approve(approve_service, draft, session=session, user=user)
    await session.commit()

    async def disconnect_racing() -> None:
        engine = create_async_engine(TEST_DB_URL)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as racing:
                racing_account = await ConnectedAccountRepository(racing, user.id).get(account.id)
                assert racing_account is not None
                racing_account.status = AccountStatus.disconnected
                await racing.commit()
        finally:
            await engine.dispose()

    async def execute_racing() -> object:
        engine = create_async_engine(TEST_DB_URL)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as racing:
                racing_executor = CountingExecutor()
                racing_service = ActionProposalService(
                    racing,
                    user.id,
                    google_executors=GoogleExecutorRegistry(
                        {ActionType.create_gmail_draft: racing_executor}
                    ),
                    now_factory=lambda: NOW,
                )
                try:
                    _proposal_after, execution = await racing_service.execute(draft.id)
                    await racing.commit()
                    return execution.execution_mode
                except ProposalConflictError as exc:
                    await racing.commit()
                    return exc.code
        finally:
            await engine.dispose()

    results = await asyncio.gather(disconnect_racing(), execute_racing(), return_exceptions=True)
    execute_outcome = results[1]
    assert not isinstance(execute_outcome, BaseException)
    # Either the disclosed real path ran (win the race, or lose it and fail
    # cleanly via `google_reauthorisation_required` — either way `execution_
    # mode` stays "real"), or execution was controllably blocked before any
    # attempt — "simulation" must never appear for this Google-sourced,
    # real-approved proposal.
    assert execute_outcome in {"real", "approval_context_changed"}
