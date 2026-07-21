"""Stage 8 Phase 1: the closed, typed preference registry (ADR 0004 D44-D46).

Covers value validation, defaults, the read/update routes (audit + provenance
+ CSRF), cross-user isolation, the never-hidden needs-attention rule, and the
brief actually respecting the user's chosen sections.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL
from tests.helpers import TIMEZONE, demo_source_items

from lifeflow_api.brief_composition import BriefSectionKey, BriefService
from lifeflow_api.models import User
from lifeflow_api.preferences import (
    BRIEF_SECTIONS_KEY,
    BRIEFING_TIME_KEY,
    NEEDS_ATTENTION_SECTION,
    OPTIONAL_BRIEF_SECTIONS,
    PREFERENCE_KEYS,
    WORKING_HOURS_KEY,
    validate_preference_value,
)

pytestmark = pytest.mark.integration


# --- Registry validation (pure) --------------------------------------------


def test_section_literals_match_the_brief_section_enum() -> None:
    """The registry uses literal strings to avoid an import cycle — pin them
    against the real enum so they can never drift apart silently."""
    enum_values = {str(key) for key in BriefSectionKey}
    assert set(OPTIONAL_BRIEF_SECTIONS) | {NEEDS_ATTENTION_SECTION} == enum_values
    assert NEEDS_ATTENTION_SECTION == str(BriefSectionKey.needs_attention)


def test_briefing_time_accepts_valid_and_rejects_invalid_times() -> None:
    assert validate_preference_value(BRIEFING_TIME_KEY, {"value": "07:30"}) == {"value": "07:30"}
    for bad in ("7:30", "25:00", "07:60", "morning", "", "07:30:00"):
        with pytest.raises(ValueError):
            validate_preference_value(BRIEFING_TIME_KEY, {"value": bad})


def test_working_hours_must_start_before_they_end() -> None:
    good = {"start": "09:00", "end": "17:30"}
    assert validate_preference_value(WORKING_HOURS_KEY, good) == good
    with pytest.raises(ValueError, match="start before they end"):
        validate_preference_value(WORKING_HOURS_KEY, {"start": "18:00", "end": "09:00"})
    with pytest.raises(ValueError):
        validate_preference_value(WORKING_HOURS_KEY, {"start": "09:00", "end": "9pm"})


def test_brief_sections_reject_needs_attention_and_unknown_keys() -> None:
    ok = {"sections": ["today_upcoming", "waiting_for"]}
    assert validate_preference_value(BRIEF_SECTIONS_KEY, ok) == ok
    with pytest.raises(ValueError, match="always shown"):
        validate_preference_value(BRIEF_SECTIONS_KEY, {"sections": ["needs_attention"]})
    with pytest.raises(ValueError):
        validate_preference_value(BRIEF_SECTIONS_KEY, {"sections": ["not_a_section"]})
    with pytest.raises(ValueError, match="unique"):
        validate_preference_value(BRIEF_SECTIONS_KEY, {"sections": ["waiting_for", "waiting_for"]})


# --- Routes ----------------------------------------------------------------


async def _login(client: AsyncClient, marker: str) -> uuid.UUID:
    response = await client.post(
        "/auth/dev-login",
        json={"email": f"prefs-{marker}-{uuid.uuid4()}@example.com", "display_name": "Prefs"},
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200
    return uuid.UUID(response.json()["user_id"])


async def test_preferences_list_returns_every_key_with_defaults(dev_client: AsyncClient) -> None:
    await _login(dev_client, "defaults")
    response = await dev_client.get("/preferences")
    assert response.status_code == 200
    items = {item["key"]: item for item in response.json()["preferences"]}
    assert set(items) == set(PREFERENCE_KEYS)
    assert all(item["is_default"] for item in items.values())
    assert items[BRIEFING_TIME_KEY]["value"] == {"value": "07:30"}
    assert items[BRIEF_SECTIONS_KEY]["value"]["sections"] == list(OPTIONAL_BRIEF_SECTIONS)


async def test_update_persists_audits_and_marks_explicit(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "update")
    response = await dev_client.put(
        f"/preferences/{BRIEFING_TIME_KEY}",
        json={"value": {"value": "06:45"}},
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["value"] == {"value": "06:45"}
    assert body["provenance"] == "explicit"
    assert body["is_default"] is False

    listed = await dev_client.get("/preferences")
    items = {item["key"]: item for item in listed.json()["preferences"]}
    assert items[BRIEFING_TIME_KEY]["value"] == {"value": "06:45"}
    assert items[BRIEFING_TIME_KEY]["is_default"] is False

    # No audit-history route exists until Stage 9 — assert the append-only
    # record directly (D46: key, provenance, and value; no other content).
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            from sqlalchemy import select

            from lifeflow_api.models import AuditEvent

            events = (
                (
                    await session.execute(
                        select(AuditEvent).where(
                            AuditEvent.user_id == user_id,
                            AuditEvent.event_type == "preference.updated",
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(events) == 1
            assert events[0].safe_metadata_json["key"] == BRIEFING_TIME_KEY
            assert events[0].safe_metadata_json["provenance"] == "explicit"
            assert events[0].safe_metadata_json["value"] == {"value": "06:45"}
    finally:
        await engine.dispose()


async def test_unknown_key_is_404_and_invalid_value_is_422(dev_client: AsyncClient) -> None:
    await _login(dev_client, "errors")
    missing = await dev_client.put(
        "/preferences/favourite_colour", json={"value": {"value": "teal"}}, headers=CSRF_HEADERS
    )
    assert missing.status_code == 404
    invalid = await dev_client.put(
        f"/preferences/{WORKING_HOURS_KEY}",
        json={"value": {"start": "18:00", "end": "09:00"}},
        headers=CSRF_HEADERS,
    )
    assert invalid.status_code == 422
    assert "start before they end" in invalid.json()["error"]["message"]


async def test_preferences_are_isolated_per_user(dev_client: AsyncClient) -> None:
    await _login(dev_client, "owner")
    await dev_client.put(
        f"/preferences/{BRIEFING_TIME_KEY}",
        json={"value": {"value": "05:15"}},
        headers=CSRF_HEADERS,
    )
    # A different user signs in on the same client (fresh session cookie).
    await _login(dev_client, "other")
    listed = await dev_client.get("/preferences")
    items = {item["key"]: item for item in listed.json()["preferences"]}
    assert items[BRIEFING_TIME_KEY]["is_default"] is True
    assert items[BRIEFING_TIME_KEY]["value"] == {"value": "07:30"}


# --- Brief adaptation (D45) ------------------------------------------------


async def test_brief_respects_chosen_sections_and_never_hides_needs_attention(
    dev_client: AsyncClient,
) -> None:
    user_id = await _login(dev_client, "brief")
    response = await dev_client.put(
        f"/preferences/{BRIEF_SECTIONS_KEY}",
        json={"value": {"sections": ["today_upcoming"]}},
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200

    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            user = await session.get(User, user_id)
            assert user is not None
            from datetime import UTC, datetime

            live_reference = datetime.now(UTC)
            session.add_all(await demo_source_items(user.id, anchor=live_reference.date()))
            await session.flush()
            brief = await BriefService(session, user.id).generate(
                timezone=TIMEZONE, reference=live_reference
            )
            displayed = [section["key"] for section in brief.sections_json["sections"]]
            assert "needs_attention" in displayed  # never hideable (D45)
            assert "today_upcoming" in displayed
            assert "waiting_for" not in displayed
            assert "suggested_actions" not in displayed
            assert "low_confidence_review" not in displayed
            disabled = brief.model_metadata["sections_disabled"]
            assert sorted(disabled) == [
                "low_confidence_review",
                "suggested_actions",
                "waiting_for",
            ]
            # Full extraction still ran: hiding sections never suppresses
            # signals or proposals, only their display in this brief.
            assert brief.model_metadata["signal_count"] > 0
            await session.commit()
    finally:
        await engine.dispose()
