"""End-to-end extraction pipeline: dedupe, idempotency, degraded mode, API."""

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL
from tests.helpers import ANCHOR, REFERENCE, TIMEZONE, demo_source_items

from lifeflow_api.detectors import run_deterministic_detectors
from lifeflow_api.extraction import SignalExtractionService, dedupe_key, deduplicate
from lifeflow_api.ingestion import IngestionService
from lifeflow_api.llm.mock import FailingLLMProvider, MockLLMProvider
from lifeflow_api.models import User
from lifeflow_api.repositories import SignalRepository

pytestmark = pytest.mark.integration

LLM_SIGNAL = {
    "signal_type": "request",
    "title": "Book the follow-up coaching session",
    "summary": "James assigned one action: book before the end of the month.",
    "evidence_refs": ["em-019"],
    "due_at": "2026-07-31T22:59:00+00:00",
    "confidence": 0.75,
}


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.commit()
    await engine.dispose()


@pytest.fixture
async def user_with_items(session: AsyncSession) -> User:
    user = User(email="demo@lifeflow.local", display_name="Demo User")
    session.add(user)
    await session.flush()
    from datetime import UTC, datetime

    from lifeflow_api.connectors.synthetic import (
        SyntheticCalendarConnector,
        SyntheticEmailConnector,
    )

    await IngestionService(session, user.id).import_sources(
        email_connector=SyntheticEmailConnector(ANCHOR),
        calendar_connector=SyntheticCalendarConnector(ANCHOR),
        account_id=None,
        since=datetime(2026, 6, 15, tzinfo=UTC),
        until=datetime(2026, 8, 31, tzinfo=UTC),
    )
    return user


async def test_dedupe_prefers_deterministic_signals() -> None:
    items = await demo_source_items()
    detected = run_deterministic_detectors(items, reference=REFERENCE, timezone=TIMEZONE)
    duplicate = detected[0]
    assert deduplicate([*detected, duplicate]) == deduplicate(detected)
    assert dedupe_key(duplicate) == dedupe_key(detected[0])


async def test_extraction_persists_and_is_idempotent(
    session: AsyncSession, user_with_items: User
) -> None:
    service = SignalExtractionService(session, user_with_items.id)
    first = await service.extract(timezone=TIMEZONE, reference=REFERENCE)
    assert first.deterministic > 0
    assert first.persisted_new == first.deterministic
    assert not first.llm_used

    second = await service.extract(timezone=TIMEZONE, reference=REFERENCE)
    assert second.persisted_new == 0  # re-extraction updates, never duplicates
    count = (await session.execute(text("SELECT count(*) FROM signals"))).scalar()
    assert count == first.persisted_new


async def test_llm_augments_without_replacing(session: AsyncSession, user_with_items: User) -> None:
    provider = MockLLMProvider({"signal_extraction_v1": {"signals": [LLM_SIGNAL]}})
    service = SignalExtractionService(session, user_with_items.id, llm_provider=provider)
    summary = await service.extract(timezone=TIMEZONE, reference=REFERENCE)
    assert summary.llm_used and not summary.llm_failed
    assert summary.llm_added == 1
    assert summary.persisted_new == summary.deterministic + 1

    signals = await SignalRepository(session, user_with_items.id).list_ranked(limit=500)
    versions = {s.extraction_version for s in signals}
    assert versions == {"det-v1", "llm-v1"}


async def test_provider_outage_degrades_to_deterministic_baseline(
    session: AsyncSession, user_with_items: User
) -> None:
    service = SignalExtractionService(
        session, user_with_items.id, llm_provider=FailingLLMProvider()
    )
    summary = await service.extract(timezone=TIMEZONE, reference=REFERENCE)
    assert summary.llm_failed and not summary.llm_used
    assert summary.persisted_new == summary.deterministic  # baseline intact

    events = (
        (
            await session.execute(
                text(
                    "SELECT safe_metadata_json->>'llm_failed' FROM audit_events "
                    "WHERE event_type = 'extraction.completed'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert "true" in events  # failure is visible, not silent


async def test_signals_are_isolated_between_users(
    session: AsyncSession, user_with_items: User
) -> None:
    await SignalExtractionService(session, user_with_items.id).extract(
        timezone=TIMEZONE, reference=REFERENCE
    )
    other = User(email="other@example.test", display_name="Other")
    session.add(other)
    await session.flush()
    assert await SignalRepository(session, other.id).list_ranked(limit=500) == []


async def test_signals_api_extract_and_list(dev_client: AsyncClient) -> None:
    await dev_client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
    await dev_client.post("/demo/start", headers=CSRF_HEADERS)

    extract = await dev_client.post("/signals/extract", headers=CSRF_HEADERS)
    assert extract.status_code == 200
    body = extract.json()
    assert body["deterministic"] > 0 and body["llm_used"] is False

    listing = (await dev_client.get("/signals", params={"limit": 500})).json()
    assert listing["count"] == body["persisted_new"]
    top = listing["signals"][0]
    assert top["priority_band"] == "high"
    assert top["reason_codes"] and top["evidence_refs"]

    high_only = (await dev_client.get("/signals", params={"band": "high"})).json()
    assert all(s["priority_band"] == "high" for s in high_only["signals"])


async def test_signals_require_authentication(dev_client: AsyncClient) -> None:
    assert (await dev_client.get("/signals")).status_code == 401
    assert (await dev_client.post("/signals/extract", headers=CSRF_HEADERS)).status_code == 401
