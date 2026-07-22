"""Application sign-in (ADR 0001 D3).

Two independent sign-in paths coexist permanently:
- `dev-login` — a development-only seeded session (unchanged), gated to
  `environment == "development"` so production settings are never weakened.
- Google Sign-In (OIDC, ADR 0003 D10) — `openid email profile` only, never
  mailbox/calendar access. Deliberately a separate OAuth client from the
  Google *connector* consent flow (`connected_accounts.py`).
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError

from lifeflow_api.audit import record_audit_event
from lifeflow_api.deps import CurrentUser, DbSession
from lifeflow_api.google.errors import IdTokenVerificationError
from lifeflow_api.google.oauth import build_authorization_url, verify_id_token
from lifeflow_api.models import User
from lifeflow_api.oauth_state import OAuthStateError, begin_oauth_flow, consume_oauth_flow
from lifeflow_api.repositories import UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")

DEV_USER_EMAIL = "dev@lifeflow.local"
OIDC_SCOPE = "openid email profile"
OIDC_PURPOSE = "signin"


class DevLoginRequest(BaseModel):
    email: EmailStr = DEV_USER_EMAIL
    display_name: str = "Dev User"


class SessionResponse(BaseModel):
    user_id: str
    email: str


@router.post("/dev-login", response_model=SessionResponse)
async def dev_login(request: Request, body: DevLoginRequest, session: DbSession) -> SessionResponse:
    if request.app.state.settings.environment != "development":
        # Indistinguishable from a route that does not exist.
        raise HTTPException(status_code=404, detail="Not Found")

    users = UserRepository(session)
    user = await users.get_by_email(body.email)
    if user is None:
        user = User(email=body.email, display_name=body.display_name)
        users.add(user)
        await session.flush()
        record_audit_event(
            session,
            user_id=user.id,
            actor="system:dev-login",
            event_type="user.created",
            entity_type="user",
            entity_id=str(user.id),
        )

    request.session.clear()
    request.session["user_id"] = str(user.id)
    record_audit_event(
        session,
        user_id=user.id,
        actor=f"user:{user.id}",
        event_type="session.created",
        entity_type="user",
        entity_id=str(user.id),
        metadata={"method": "dev-login"},
    )
    return SessionResponse(user_id=str(user.id), email=user.email)


@router.post("/logout", status_code=204)
async def logout(request: Request, user: CurrentUser, session: DbSession) -> None:
    request.session.clear()
    record_audit_event(
        session,
        user_id=user.id,
        actor=f"user:{user.id}",
        event_type="session.ended",
        entity_type="user",
        entity_id=str(user.id),
    )


def _google_oidc_disabled(request: Request) -> bool:
    settings = request.app.state.settings
    return not settings.google_oauth_enabled or request.app.state.google_oauth_client is None


@router.get("/google/login")
async def google_login(request: Request) -> RedirectResponse:
    if _google_oidc_disabled(request):
        # Indistinguishable from a route that does not exist, matching the
        # dev-login convention: real integrations stay invisible when unset.
        raise HTTPException(status_code=404, detail="Not Found")
    settings = request.app.state.settings
    state, pkce, nonce = begin_oauth_flow(request, purpose=OIDC_PURPOSE, include_nonce=True)
    url = build_authorization_url(
        client_id=settings.google_oidc_client_id,
        redirect_uri=settings.google_oidc_redirect_uri,
        scope=OIDC_SCOPE,
        state=state,
        code_challenge=pkce.challenge,
        nonce=nonce,
    )
    return RedirectResponse(url=url, status_code=302)


@router.get("/google/callback")
async def google_callback(
    request: Request, session: DbSession, code: str | None = None, state: str | None = None
) -> RedirectResponse:
    if _google_oidc_disabled(request):
        raise HTTPException(status_code=404, detail="Not Found")
    settings = request.app.state.settings
    web_origin = settings.web_origin
    if code is None or state is None:
        return RedirectResponse(url=f"{web_origin}/?auth_error=missing_code", status_code=302)
    try:
        flow = consume_oauth_flow(request, purpose=OIDC_PURPOSE, state=state)
    except OAuthStateError:
        return RedirectResponse(url=f"{web_origin}/?auth_error=invalid_state", status_code=302)

    oauth_client = request.app.state.google_oauth_client
    try:
        token_response = await oauth_client.exchange_code(
            client_id=settings.google_oidc_client_id,
            client_secret=settings.google_oidc_client_secret,
            redirect_uri=settings.google_oidc_redirect_uri,
            code=code,
            code_verifier=flow.code_verifier,
        )
        if token_response.id_token is None:
            return RedirectResponse(url=f"{web_origin}/?auth_error=no_id_token", status_code=302)
        identity = await verify_id_token(
            token_response.id_token,
            client_id=settings.google_oidc_client_id,
            expected_nonce=flow.nonce,
        )
    except IdTokenVerificationError:
        logger.warning("auth.google_oidc id token verification failed", exc_info=True)
        return RedirectResponse(url=f"{web_origin}/?auth_error=invalid_id_token", status_code=302)
    except Exception:
        logger.warning("auth.google_oidc callback failed", exc_info=True)
        return RedirectResponse(url=f"{web_origin}/?auth_error=oauth_failed", status_code=302)

    users = UserRepository(session)
    user = await users.get_by_google_subject(identity.subject)
    if user is None:
        user = User(
            email=identity.email,
            display_name=identity.email.split("@")[0],
            google_subject=identity.subject,
        )
        users.add(user)
        try:
            await session.flush()
        except IntegrityError:
            # users.email is globally unique (Stage 2); no automatic merge
            # with a pre-existing account (ADR 0003 D15) — a safe, explicit
            # conflict beats a silent merge or a raw 500.
            await session.rollback()
            return RedirectResponse(
                url=f"{web_origin}/?auth_error=email_already_registered", status_code=302
            )
        record_audit_event(
            session,
            user_id=user.id,
            actor="system:google-oidc",
            event_type="user.created",
            entity_type="user",
            entity_id=str(user.id),
        )

    request.session.clear()
    request.session["user_id"] = str(user.id)
    record_audit_event(
        session,
        user_id=user.id,
        actor=f"user:{user.id}",
        event_type="session.created",
        entity_type="user",
        entity_id=str(user.id),
        metadata={"method": "google_oidc"},
    )
    # Sign-in only establishes identity (D10) — a freshly signed-in user has
    # no connected Gmail/Calendar yet, so landing on Today would just be an
    # empty dashboard with no obvious next step. Connections is the actual
    # next step in the flow, and already renders a clear "not connected"
    # state with a working "Connect Google" action.
    return RedirectResponse(url=f"{web_origin}/connections", status_code=302)


__all__ = ["router"]
