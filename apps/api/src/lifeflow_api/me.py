"""Current-user profile and settings (onboarding state, timezone, locale)."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from lifeflow_api.audit import record_audit_event
from lifeflow_api.deps import CurrentUser, DbSession
from lifeflow_api.models import OnboardingState, User

router = APIRouter(prefix="/me")


class MeResponse(BaseModel):
    id: str
    email: str
    display_name: str
    timezone: str
    locale: str
    onboarding_state: str


class MeUpdateRequest(BaseModel):
    timezone: str | None = None
    locale: str | None = None
    onboarding_state: OnboardingState | None = None

    @field_validator("timezone")
    @classmethod
    def timezone_must_exist(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except ZoneInfoNotFoundError:
                raise ValueError(f"Unknown timezone: {value}") from None
        return value


def _to_response(user: User) -> MeResponse:
    return MeResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        timezone=user.timezone,
        locale=user.locale,
        onboarding_state=user.onboarding_state,
    )


@router.get("", response_model=MeResponse)
async def get_me(user: CurrentUser) -> MeResponse:
    return _to_response(user)


@router.patch("", response_model=MeResponse)
async def update_me(body: MeUpdateRequest, user: CurrentUser, session: DbSession) -> MeResponse:
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No settings provided.")
    for field, value in changes.items():
        setattr(user, field, value)
    await session.flush()
    record_audit_event(
        session,
        user_id=user.id,
        actor=f"user:{user.id}",
        event_type="user.settings_updated",
        entity_type="user",
        entity_id=str(user.id),
        metadata={"fields": sorted(changes)},
    )
    return _to_response(user)
