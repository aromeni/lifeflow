"""Signals API: run extraction, list ranked signals with reasons + evidence."""

from datetime import datetime

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from lifeflow_api.deps import CurrentUser, DbSession
from lifeflow_api.extraction import SignalExtractionService
from lifeflow_api.models import Signal
from lifeflow_api.repositories import SignalRepository

router = APIRouter(prefix="/signals")


class ExtractionResponse(BaseModel):
    deterministic: int
    llm_used: bool
    llm_added: int
    llm_rejected: int
    llm_failed: bool
    persisted_new: int
    persisted_updated: int
    persisted_unchanged: int


class SignalResponse(BaseModel):
    id: str
    signal_type: str
    title: str
    summary: str
    evidence_refs: list[str]
    due_at: datetime | None
    confidence: float
    priority_score: float | None
    priority_band: str | None
    reason_codes: list[str]
    extraction_version: str


class SignalListResponse(BaseModel):
    signals: list[SignalResponse]
    count: int


def _to_response(signal: Signal) -> SignalResponse:
    return SignalResponse(
        id=str(signal.id),
        signal_type=signal.signal_type,
        title=signal.title,
        summary=signal.summary,
        evidence_refs=signal.evidence_refs,
        due_at=signal.due_at,
        confidence=signal.confidence,
        priority_score=signal.priority_score,
        priority_band=signal.priority_band,
        reason_codes=signal.reason_codes,
        extraction_version=signal.extraction_version,
    )


@router.post("/extract", response_model=ExtractionResponse)
async def extract_signals(
    request: Request, user: CurrentUser, session: DbSession
) -> ExtractionResponse:
    service = SignalExtractionService(
        session, user.id, llm_provider=getattr(request.app.state, "llm_provider", None)
    )
    summary = await service.extract(timezone=user.timezone)
    return ExtractionResponse(
        deterministic=summary.deterministic,
        llm_used=summary.llm_used,
        llm_added=summary.llm_added,
        llm_rejected=summary.llm_rejected,
        llm_failed=summary.llm_failed,
        persisted_new=summary.persisted_new,
        persisted_updated=summary.persisted_updated,
        persisted_unchanged=summary.persisted_unchanged,
    )


@router.get("", response_model=SignalListResponse)
async def list_signals(
    user: CurrentUser,
    session: DbSession,
    band: str | None = Query(default=None, pattern="^(high|medium|low)$"),
    limit: int = Query(default=100, ge=1, le=500),
) -> SignalListResponse:
    signals = await SignalRepository(session, user.id).list_ranked(band=band, limit=limit)
    responses = [_to_response(signal) for signal in signals]
    return SignalListResponse(signals=responses, count=len(responses))
