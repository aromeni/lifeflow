"""Persisted daily brief versions, honest states, provider guards, and API."""

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL
from tests.helpers import REFERENCE, TIMEZONE, demo_source_items

from lifeflow_api.brief_composition import (
    BriefSectionKey,
    BriefService,
    allowed_summary_sentences,
    compose_sections,
    parse_brief_document,
)
from lifeflow_api.extraction import SignalExtractionService
from lifeflow_api.llm.mock import MockLLMProvider
from lifeflow_api.models import BriefStatus, Signal, User
from lifeflow_api.repositories import BriefRepository, SignalRepository

pytestmark = pytest.mark.integration


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


@pytest.fixture
async def user_with_items(session: AsyncSession) -> User:
    user = User(email="brief-demo@lifeflow.local", display_name="Brief Demo")
    session.add(user)
    await session.flush()
    session.add_all(await demo_source_items(user.id))
    await session.flush()
    return user


async def test_brief_versions_persist_with_metadata_and_grounded_items(
    session: AsyncSession, user_with_items: User
) -> None:
    service = BriefService(session, user_with_items.id)
    first = await service.generate(timezone=TIMEZONE, reference=REFERENCE)
    second = await service.generate(timezone=TIMEZONE, reference=REFERENCE)

    assert first.version == 1 and second.version == 2
    assert first.id != second.id
    assert first.summary == second.summary
    assert first.sections_json == second.sections_json
    assert first.model_metadata["composer_version"] == "brief-det-v1"
    assert first.model_metadata["extraction"]["persisted_new"] > 0
    assert second.model_metadata["extraction"]["persisted_unchanged"] > 0

    versions = await BriefRepository(session, user_with_items.id).list_recent()
    assert [brief.version for brief in versions] == [2, 1]
    document = parse_brief_document(second)
    assert [section.key for section in document.sections] == list(BriefSectionKey)
    actionable = [
        item for section in document.sections for item in section.items if item.actionable
    ]
    assert actionable and all(item.evidence for item in actionable)


async def test_mock_provider_output_is_deterministic_and_grounded(
    session: AsyncSession, user_with_items: User
) -> None:
    await SignalExtractionService(session, user_with_items.id).extract(
        timezone=TIMEZONE, reference=REFERENCE
    )
    signals = await SignalRepository(session, user_with_items.id).list_ranked(limit=1000)
    composed = compose_sections(signals, await demo_source_items(user_with_items.id))
    allowed = allowed_summary_sentences(composed.sections)
    signal_id, sentence = next(iter(allowed.items()))
    provider = MockLLMProvider(
        {
            "signal_extraction_v1": {"signals": []},
            "brief_composition_v1": {
                "summary_sentences": [{"signal_id": signal_id, "text": sentence}]
            },
        }
    )
    service = BriefService(session, user_with_items.id, llm_provider=provider)

    first = await service.generate(timezone=TIMEZONE, reference=REFERENCE)
    second = await service.generate(timezone=TIMEZONE, reference=REFERENCE)

    assert first.summary == second.summary == sentence
    assert first.sections_json == second.sections_json
    assert first.model_metadata["prose_state"] == "augmented"
    assert [call["task"] for call in provider.calls] == [
        "signal_extraction_v1",
        "brief_composition_v1",
        "signal_extraction_v1",
        "brief_composition_v1",
    ]


async def test_unsupported_optional_prose_degrades_without_leaking_claim(
    session: AsyncSession, user_with_items: User
) -> None:
    await SignalExtractionService(session, user_with_items.id).extract(
        timezone=TIMEZONE, reference=REFERENCE
    )
    signals = await SignalRepository(session, user_with_items.id).list_ranked(limit=1000)
    composed = compose_sections(signals, await demo_source_items(user_with_items.id))
    signal_id = next(iter(allowed_summary_sentences(composed.sections)))
    provider = MockLLMProvider(
        {
            "signal_extraction_v1": {"signals": []},
            "brief_composition_v1": {
                "summary_sentences": [
                    {
                        "signal_id": signal_id,
                        "text": "Send everything now before an invented Friday deadline.",
                    }
                ]
            },
        }
    )

    brief = await BriefService(session, user_with_items.id, llm_provider=provider).generate(
        timezone=TIMEZONE, reference=REFERENCE
    )

    assert brief.status == BriefStatus.degraded
    assert "invented Friday" not in brief.summary
    assert brief.model_metadata["llm_summary_failed"] is True
    assert "llm_degraded" in {notice.code for notice in parse_brief_document(brief).notices}


async def test_empty_and_partial_states_are_explicit(session: AsyncSession) -> None:
    empty_user = User(email="empty@lifeflow.local", display_name="Empty")
    partial_user = User(email="partial@lifeflow.local", display_name="Partial")
    session.add_all([empty_user, partial_user])
    await session.flush()

    empty = await BriefService(session, empty_user.id).generate(
        timezone=TIMEZONE, reference=REFERENCE
    )
    assert empty.status == BriefStatus.empty
    assert all(not section.items for section in parse_brief_document(empty).sections)

    SignalRepository(session, partial_user.id).add(
        Signal(
            user_id=partial_user.id,
            signal_type="request",
            title="Unsupported stale signal",
            summary="This must never surface without evidence.",
            evidence_refs=["missing-source"],
            due_at=None,
            confidence=0.9,
            urgency=0.5,
            importance=0.5,
            extraction_version="det-v1",
            priority_score=0.8,
            priority_band="high",
            reason_codes=["explicit_request"],
            dedupe_key=uuid.uuid4().hex,
        )
    )
    await session.flush()
    partial = await BriefService(session, partial_user.id).generate(
        timezone=TIMEZONE, reference=REFERENCE
    )
    assert partial.status == BriefStatus.partial
    assert partial.model_metadata["omitted_signal_count"] == 1
    assert "Unsupported stale signal" not in partial.summary
    assert "evidence_missing" in {notice.code for notice in parse_brief_document(partial).notices}


async def test_briefs_api_demo_flow_and_version_retrieval(dev_client: AsyncClient) -> None:
    await dev_client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
    await dev_client.post("/demo/start", headers=CSRF_HEADERS)

    generated = await dev_client.post("/briefs/generate", headers=CSRF_HEADERS)
    assert generated.status_code == 200
    body = generated.json()
    assert body["status"] == "complete"
    assert [section["key"] for section in body["sections"]] == [
        key.value for key in BriefSectionKey
    ]
    assert all(
        item["evidence"]
        for section in body["sections"]
        for item in section["items"]
        if item["actionable"]
    )

    latest = await dev_client.get("/briefs/latest")
    persisted = await dev_client.get(f"/briefs/{body['id']}")
    versions = await dev_client.get("/briefs")
    assert latest.json()["id"] == body["id"]
    assert persisted.json() == latest.json()
    assert versions.json()["count"] >= 1


async def test_briefs_require_authentication(dev_client: AsyncClient) -> None:
    assert (await dev_client.get("/briefs/latest")).status_code == 401
    assert (await dev_client.get("/briefs")).status_code == 401
    assert (await dev_client.post("/briefs/generate", headers=CSRF_HEADERS)).status_code == 401
