"""Read access to normalised source items (Today shell and debug view)."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from lifeflow_api.deps import CurrentUser, DbSession
from lifeflow_api.models import SourceItem, SourceType
from lifeflow_api.repositories import SourceItemRepository

router = APIRouter(prefix="/source-items")


class SourceItemResponse(BaseModel):
    id: str
    source_type: str
    external_id: str
    title: str
    sender_or_organiser: str | None
    occurred_at: datetime
    metadata: dict[str, Any]


class SourceItemListResponse(BaseModel):
    items: list[SourceItemResponse]
    count: int


def _to_response(item: SourceItem) -> SourceItemResponse:
    return SourceItemResponse(
        id=str(item.id),
        source_type=item.source_type,
        external_id=item.external_id,
        title=item.title,
        sender_or_organiser=item.sender_or_organiser,
        occurred_at=item.occurred_at,
        metadata=item.metadata_json,
    )


@router.get("", response_model=SourceItemListResponse)
async def list_source_items(
    user: CurrentUser,
    session: DbSession,
    source_type: SourceType | None = None,
    occurring_after: datetime | None = None,
    occurring_before: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> SourceItemListResponse:
    items = await SourceItemRepository(session, user.id).list(
        source_type=source_type,
        occurring_after=occurring_after,
        occurring_before=occurring_before,
        limit=limit,
        offset=offset,
    )
    responses = [_to_response(item) for item in items]
    return SourceItemListResponse(items=responses, count=len(responses))
