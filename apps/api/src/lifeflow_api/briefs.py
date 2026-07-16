"""Daily brief API: on-demand generation and persisted version retrieval."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from lifeflow_api.brief_composition import (
    BriefNotice,
    BriefSection,
    BriefService,
    parse_brief_document,
)
from lifeflow_api.deps import CurrentUser, DbSession
from lifeflow_api.models import Brief, BriefStatus
from lifeflow_api.repositories import BriefRepository

router = APIRouter(prefix="/briefs")


class BriefResponse(BaseModel):
    id: str
    briefing_date: datetime
    generated_at: datetime
    version: int
    status: BriefStatus
    summary: str
    sections: list[BriefSection]
    notices: list[BriefNotice]
    source_window: str
    prompt_version: str | None
    generation_metadata: dict[str, Any]


class BriefVersionResponse(BaseModel):
    id: str
    briefing_date: datetime
    generated_at: datetime
    version: int
    status: BriefStatus


class BriefVersionListResponse(BaseModel):
    briefs: list[BriefVersionResponse]
    count: int


def _to_response(brief: Brief) -> BriefResponse:
    document = parse_brief_document(brief)
    return BriefResponse(
        id=str(brief.id),
        briefing_date=brief.briefing_date,
        generated_at=brief.generated_at,
        version=brief.version,
        status=BriefStatus(brief.status),
        summary=brief.summary,
        sections=document.sections,
        notices=document.notices,
        source_window=brief.source_window,
        prompt_version=brief.prompt_version,
        generation_metadata=brief.model_metadata,
    )


def _to_version_response(brief: Brief) -> BriefVersionResponse:
    return BriefVersionResponse(
        id=str(brief.id),
        briefing_date=brief.briefing_date,
        generated_at=brief.generated_at,
        version=brief.version,
        status=BriefStatus(brief.status),
    )


@router.post("/generate", response_model=BriefResponse)
async def generate_brief(request: Request, user: CurrentUser, session: DbSession) -> BriefResponse:
    brief = await BriefService(
        session,
        user.id,
        llm_provider=getattr(request.app.state, "llm_provider", None),
    ).generate(timezone=user.timezone)
    return _to_response(brief)


@router.get("/latest", response_model=BriefResponse)
async def get_latest_brief(user: CurrentUser, session: DbSession) -> BriefResponse:
    brief = await BriefRepository(session, user.id).latest()
    if brief is None:
        raise HTTPException(status_code=404, detail="No brief has been generated yet.")
    return _to_response(brief)


@router.get("", response_model=BriefVersionListResponse)
async def list_brief_versions(
    user: CurrentUser,
    session: DbSession,
    limit: int = Query(default=30, ge=1, le=100),
) -> BriefVersionListResponse:
    briefs = await BriefRepository(session, user.id).list_recent(limit=limit)
    responses = [_to_version_response(brief) for brief in briefs]
    return BriefVersionListResponse(briefs=responses, count=len(responses))


@router.get("/{brief_id}", response_model=BriefResponse)
async def get_brief(brief_id: uuid.UUID, user: CurrentUser, session: DbSession) -> BriefResponse:
    brief = await BriefRepository(session, user.id).get(brief_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="Brief not found.")
    return _to_response(brief)
