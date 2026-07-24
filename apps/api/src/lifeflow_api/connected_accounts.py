"""Google connector consent (ADR 0001 D3, ADR 0003 D10) and real sync
(Stage 7 remediation, independent-review blocker #1).

Consent is separate from application sign-in (`auth.py`): requires an
existing LifeFlow session, requests only the four data scopes
(`google_scopes.py`), and is triggered only from the Connections screen —
never implied by sign-in. Sync is the first thing consent actually makes
possible: `POST /connected-accounts/google/sync` is the one route that turns
a connected account into real, persisted `SourceItem` rows.
"""

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from lifeflow_api.accounts import ConnectedAccountService, ReauthorisationRequiredError
from lifeflow_api.deps import ActiveUser, CurrentUser, DbSession
from lifeflow_api.errors import error_response
from lifeflow_api.google.errors import GoogleApiError
from lifeflow_api.google.oauth import build_authorization_url
from lifeflow_api.google_scopes import CONNECTOR_SCOPE_STRING
from lifeflow_api.google_sync import GoogleReadScopeMissingError
from lifeflow_api.google_wiring import build_google_sync_service
from lifeflow_api.oauth_state import OAuthStateError, begin_oauth_flow, consume_oauth_flow
from lifeflow_api.rate_limit_deps import RateLimited
from lifeflow_api.repositories import ConnectedAccountRepository
from lifeflow_api.security.token_cipher import TokenCipher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/connected-accounts")

CONNECTOR_PURPOSE = "connect"
GOOGLE_PROVIDER = "google"
SYNC_WINDOW_PAST_DAYS = 14  # matches demo mode's constrained recent window (assumption BD5)
SYNC_WINDOW_FUTURE_DAYS = 30


class ConnectedAccountView(BaseModel):
    provider: str
    status: str
    granted_scopes: list[str]
    last_sync_at: str | None


class ConnectedAccountsResponse(BaseModel):
    accounts: list[ConnectedAccountView]


@router.get(
    "", response_model=ConnectedAccountsResponse, dependencies=[RateLimited("authenticated_read")]
)
async def list_connected_accounts(
    user: CurrentUser, session: DbSession
) -> ConnectedAccountsResponse:
    accounts = await ConnectedAccountRepository(session, user.id).list()
    return ConnectedAccountsResponse(
        accounts=[
            ConnectedAccountView(
                provider=account.provider,
                status=account.status,
                granted_scopes=list(account.granted_scopes),
                last_sync_at=account.last_sync_at.isoformat() if account.last_sync_at else None,
            )
            for account in accounts
        ]
    )


def _google_connector_disabled(request: Request) -> bool:
    settings = request.app.state.settings
    return not settings.google_oauth_enabled or request.app.state.google_oauth_client is None


@router.get("/google/connect", dependencies=[RateLimited("oauth_connect_callback")])
async def connect_google(request: Request, user: CurrentUser) -> RedirectResponse:
    if _google_connector_disabled(request):
        raise HTTPException(status_code=404, detail="Not Found")
    settings = request.app.state.settings
    state, pkce, _nonce = begin_oauth_flow(
        request, purpose=CONNECTOR_PURPOSE, bind_user_id=str(user.id)
    )
    url = build_authorization_url(
        client_id=settings.google_connector_client_id,
        redirect_uri=settings.google_connector_redirect_uri,
        scope=CONNECTOR_SCOPE_STRING,
        state=state,
        code_challenge=pkce.challenge,
        access_type="offline",
        prompt="consent",
    )
    return RedirectResponse(url=url, status_code=302)


@router.get("/google/callback", dependencies=[RateLimited("oauth_connect_callback")])
async def google_connector_callback(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    if _google_connector_disabled(request):
        raise HTTPException(status_code=404, detail="Not Found")
    settings = request.app.state.settings
    web_origin = settings.web_origin
    if code is None or state is None:
        return RedirectResponse(url=f"{web_origin}/?connect_error=missing_code", status_code=302)
    try:
        flow = consume_oauth_flow(request, purpose=CONNECTOR_PURPOSE, state=state)
    except OAuthStateError:
        return RedirectResponse(url=f"{web_origin}/?connect_error=invalid_state", status_code=302)

    oauth_client = request.app.state.google_oauth_client
    try:
        token_response = await oauth_client.exchange_code(
            client_id=settings.google_connector_client_id,
            client_secret=settings.google_connector_client_secret,
            redirect_uri=settings.google_connector_redirect_uri,
            code=code,
            code_verifier=flow.code_verifier,
        )
    except Exception:
        logger.warning("connected_accounts.google callback failed", exc_info=True)
        return RedirectResponse(url=f"{web_origin}/?connect_error=oauth_failed", status_code=302)

    cipher: TokenCipher = request.app.state.token_cipher
    # Persist exactly the scopes Google's response reports as granted, never
    # the requested set — a partial grant must be recorded honestly (T20).
    granted_scopes = token_response.scope.split() if token_response.scope else []
    await ConnectedAccountService(session, user.id, cipher).store_tokens(
        provider=GOOGLE_PROVIDER,
        access_token=token_response.access_token,
        refresh_token=token_response.refresh_token,
        granted_scopes=granted_scopes,
        expires_at=datetime.now(UTC) + timedelta(seconds=token_response.expires_in),
    )
    return RedirectResponse(url=f"{web_origin}/connections?connected=google", status_code=302)


@router.post(
    "/google/disconnect", status_code=204, dependencies=[RateLimited("oauth_connect_callback")]
)
async def disconnect_google(request: Request, user: CurrentUser, session: DbSession) -> None:
    cipher: TokenCipher = request.app.state.token_cipher
    oauth_client = (
        None if _google_connector_disabled(request) else request.app.state.google_oauth_client
    )
    await ConnectedAccountService(session, user.id, cipher).disconnect(
        GOOGLE_PROVIDER, oauth_client=oauth_client
    )


class GoogleSyncResponse(BaseModel):
    imported: int
    updated: int
    unchanged: int
    # Deliberately separate, not one combined "incomplete" count (Stage 7
    # focused remediation): `gmail_excluded` messages were read successfully
    # and excluded only for being outside Inbox/Sent (by design, D21) — a
    # normal outcome, never a failure. `gmail_incomplete` messages genuinely
    # could not be fetched (HTTP 404 on a history-referenced id, D38).
    # `calendar_incomplete` events genuinely could not be parsed. The latter
    # two are worth the user's attention; the first is not.
    gmail_excluded: int
    gmail_incomplete: int
    calendar_incomplete: int
    gmail_synced: bool
    gmail_cursor_status: str
    # False when the page bound was reached with more pages still
    # remaining — the sync is genuinely partial, not just slow (Stage 7
    # remediation blocker #3). A later sync resumes automatically.
    gmail_sync_complete: bool
    calendar_synced: bool
    calendar_cursor_status: str
    calendar_sync_complete: bool


@router.post(
    "/google/sync", response_model=GoogleSyncResponse, dependencies=[RateLimited("provider_sync")]
)
async def sync_google(
    request: Request, user: ActiveUser, session: DbSession
) -> GoogleSyncResponse | JSONResponse:
    """User-triggered, on-demand sync (never automatic on page load — see
    threat model and ADR 0003): pulls the connected user's own Gmail/Calendar
    data through the narrow real clients into persisted `SourceItem` rows,
    exactly as `IngestionService` already does for the synthetic connectors.
    """
    if _google_connector_disabled(request):
        raise HTTPException(status_code=404, detail="Not Found")
    sync_service = build_google_sync_service(request, session, user.id)
    if sync_service is None:  # pragma: no cover — same guard as the line above, defensive
        raise HTTPException(status_code=404, detail="Not Found")

    now_local = datetime.now(ZoneInfo(user.timezone))
    try:
        summary = await sync_service.sync(
            since=now_local - timedelta(days=SYNC_WINDOW_PAST_DAYS),
            until=now_local + timedelta(days=SYNC_WINDOW_FUTURE_DAYS),
        )
    except ReauthorisationRequiredError:
        return error_response(
            409, "reauthorisation_required", "Connect (or reconnect) Google before syncing."
        )
    except GoogleReadScopeMissingError:
        return error_response(
            409, "read_scope_missing", "Grant Gmail or Calendar read access before syncing."
        )
    except GoogleApiError:
        # Never surface a raw provider exception/URL to the client (T6).
        logger.warning("connected_accounts.google sync failed", exc_info=True)
        return error_response(502, "google_sync_failed", "Google sync could not complete.")

    return GoogleSyncResponse(
        imported=summary.imported,
        updated=summary.updated,
        unchanged=summary.unchanged,
        gmail_excluded=summary.gmail_excluded,
        gmail_incomplete=summary.gmail_incomplete,
        calendar_incomplete=summary.calendar_incomplete,
        gmail_synced=summary.gmail_synced,
        gmail_cursor_status=summary.gmail_cursor_status,
        gmail_sync_complete=summary.gmail_sync_complete,
        calendar_synced=summary.calendar_synced,
        calendar_cursor_status=summary.calendar_cursor_status,
        calendar_sync_complete=summary.calendar_sync_complete,
    )


__all__ = ["router"]
