"""FastAPI dependencies: database session and authenticated user."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.models import User
from lifeflow_api.repositories import UserRepository


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One transaction per request: commit on success, roll back on error."""
    async with request.app.state.sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(request: Request, session: DbSession) -> User:
    raw_user_id = request.session.get("user_id")
    if raw_user_id is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    try:
        user_id = uuid.UUID(raw_user_id)
    except ValueError:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Invalid session.") from None
    user = await UserRepository(session).get(user_id)
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Unknown user.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
