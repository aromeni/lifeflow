"""Constructs the real-Google service objects a request needs from
`app.state` (Stage 7 remediation, independent-review blocker #1/#2).

Before this module existed, `google_sync.py` and the Google executors in
`action_executors.py` were fully built and unit-tested but never constructed
anywhere the running application could reach — every route that touched
`ActionProposalService` or ingestion always used the synthetic/simulated
path regardless of what the user had connected. This module is the single
place both the sync route (`connected_accounts.py`) and the execute route
(`action_proposals.py`) ask "is Google wired for this deployment, and if so,
build the request-scoped service" — so the two call sites can never drift.
"""

import uuid

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.accounts import GoogleTokenService
from lifeflow_api.action_executors import (
    ExecutorRegistry,
    GoogleCalendarEventExecutor,
    GoogleExecutorRegistry,
    GoogleGmailDraftExecutor,
)
from lifeflow_api.google_sync import GoogleSyncService
from lifeflow_api.models import ActionType


def google_integration_ready(request: Request) -> bool:
    """True only when `GOOGLE_OAUTH_ENABLED=true` and every dependency
    `create_app` requires alongside it was actually constructed."""
    state = request.app.state
    return (
        state.google_oauth_client is not None
        and state.gmail_client is not None
        and state.calendar_client is not None
        and state.token_cipher is not None
    )


def build_google_token_service(
    request: Request, session: AsyncSession, user_id: uuid.UUID
) -> GoogleTokenService:
    settings = request.app.state.settings
    return GoogleTokenService(
        session,
        user_id,
        request.app.state.token_cipher,
        request.app.state.google_oauth_client,
        client_id=settings.google_connector_client_id,
        client_secret=settings.google_connector_client_secret,
    )


def build_google_executor_registry(
    request: Request, session: AsyncSession, user_id: uuid.UUID
) -> ExecutorRegistry | None:
    """None when Google integration isn't configured for this deployment —
    callers must treat that as "real execution unavailable", never fall back
    to simulating silently."""
    if not google_integration_ready(request):
        return None
    tokens = build_google_token_service(request, session, user_id)
    state = request.app.state
    return GoogleExecutorRegistry(
        {
            ActionType.create_gmail_draft: GoogleGmailDraftExecutor(state.gmail_client, tokens),
            ActionType.create_calendar_event: GoogleCalendarEventExecutor(
                state.calendar_client, tokens
            ),
        }
    )


def build_google_sync_service(
    request: Request, session: AsyncSession, user_id: uuid.UUID
) -> GoogleSyncService | None:
    if not google_integration_ready(request):
        return None
    settings = request.app.state.settings
    state = request.app.state
    return GoogleSyncService(
        session,
        user_id,
        cipher=state.token_cipher,
        oauth_client=state.google_oauth_client,
        gmail_client=state.gmail_client,
        calendar_client=state.calendar_client,
        client_id=settings.google_connector_client_id,
        client_secret=settings.google_connector_client_secret,
    )


__all__ = [
    "build_google_executor_registry",
    "build_google_sync_service",
    "build_google_token_service",
    "google_integration_ready",
]
