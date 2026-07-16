"""Application sign-in (ADR 0001 D3).

Google Sign-In (OIDC) arrives with Stage 7's Google integration. Until then —
and permanently for demo mode — a development-only seeded sign-in creates a
local user and a server-side session. The endpoint returns 404 outside the
development environment, so production settings are never weakened.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

from lifeflow_api.audit import record_audit_event
from lifeflow_api.deps import CurrentUser, DbSession
from lifeflow_api.models import User
from lifeflow_api.repositories import UserRepository

router = APIRouter(prefix="/auth")

DEV_USER_EMAIL = "dev@lifeflow.local"


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
