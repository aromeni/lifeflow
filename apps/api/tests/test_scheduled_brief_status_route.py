"""Stage 8 Phase 2: GET /scheduled-briefs/status (ADR 0004 D48-D50).

Route-level behaviour: defaults, enable/next-run reflection, the latest
linked brief, truthful scheduler-capability reporting in both directions
(including that Redis being unreachable never breaks the route), and that
merely reading status never dispatches anything.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL, _make_client, _test_settings

from lifeflow_api.models import AuditEvent, Brief, ScheduledBriefRun, ScheduledRunStatus, User
from lifeflow_api.preferences import BRIEFING_TIME_KEY

pytestmark = pytest.mark.integration


@pytest.fixture
async def dev_client_unreachable_redis() -> AsyncIterator[AsyncClient]:
    """A client whose scheduler Redis is deliberately unreachable, to prove
    the route degrades honestly instead of failing (test matrix: Redis
    unavailable does not break ordinary API routes)."""
    settings = _test_settings("development").model_copy(
        update={"redis_url": "redis://localhost:1/0"}
    )
    async for c in _make_client(settings):
        yield c


@pytest.fixture
async def dev_client_real_redis() -> AsyncIterator[AsyncClient]:
    settings = _test_settings("development").model_copy(
        update={"redis_url": "redis://localhost:6380/0"}
    )
    async for c in _make_client(settings):
        yield c


async def _login(client: AsyncClient, marker: str) -> uuid.UUID:
    response = await client.post(
        "/auth/dev-login",
        json={
            "email": f"sched-status-{marker}-{uuid.uuid4()}@example.com",
            "display_name": "Sched",
        },
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200
    return uuid.UUID(response.json()["user_id"])


async def test_status_defaults_when_scheduling_has_never_been_enabled(
    dev_client: AsyncClient,
) -> None:
    await _login(dev_client, "defaults")
    response = await dev_client.get("/scheduled-briefs/status")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["timezone"] == "Europe/London"
    assert body["briefing_time"] == "07:30"
    assert body["next_run_at"] is None
    assert body["latest_run_status"] is None
    assert body["latest_brief_id"] is None
    assert isinstance(body["scheduler_available"], bool)


async def test_enabling_reflects_a_next_run_in_the_users_timezone(dev_client: AsyncClient) -> None:
    await _login(dev_client, "enable")
    await dev_client.put(
        "/preferences/scheduled_briefs_enabled",
        json={"value": {"enabled": True}},
        headers=CSRF_HEADERS,
    )
    await dev_client.put(
        f"/preferences/{BRIEFING_TIME_KEY}",
        json={"value": {"value": "06:15"}},
        headers=CSRF_HEADERS,
    )
    response = await dev_client.get("/scheduled-briefs/status")
    body = response.json()
    assert body["enabled"] is True
    assert body["briefing_time"] == "06:15"
    assert body["next_run_at"] is not None


async def test_invalid_value_is_422_and_does_not_overwrite_the_stored_setting(
    dev_client: AsyncClient,
) -> None:
    await _login(dev_client, "invalid")
    await dev_client.put(
        "/preferences/scheduled_briefs_enabled",
        json={"value": {"enabled": True}},
        headers=CSRF_HEADERS,
    )
    invalid = await dev_client.put(
        "/preferences/scheduled_briefs_enabled",
        json={"value": {"enabled": "yes"}},
        headers=CSRF_HEADERS,
    )
    assert invalid.status_code == 422
    status = await dev_client.get("/scheduled-briefs/status")
    assert status.json()["enabled"] is True  # untouched by the rejected write


async def test_status_reports_the_latest_run_and_its_linked_brief(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "latest")
    await dev_client.put(
        "/preferences/scheduled_briefs_enabled",
        json={"value": {"enabled": True}},
        headers=CSRF_HEADERS,
    )

    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            user = await session.get(User, user_id)
            assert user is not None
            brief = Brief(
                user_id=user_id,
                briefing_date=datetime(2026, 7, 21, tzinfo=UTC),
                version=3,
                status="complete",
                summary="scheduled test brief",
                sections_json={"sections": [], "notices": []},
                source_window="test",
                generation_trigger="scheduled",
            )
            session.add(brief)
            await session.flush()
            run = ScheduledBriefRun(
                user_id=user_id,
                local_brief_date=datetime(2026, 7, 21, tzinfo=UTC).date(),
                scheduled_for_utc=datetime(2026, 7, 21, 6, 30, tzinfo=UTC),
                timezone_snapshot="Europe/London",
                briefing_time_snapshot="07:30",
                status=ScheduledRunStatus.succeeded,
                brief_id=brief.id,
                completed_at=datetime(2026, 7, 21, 6, 30, 5, tzinfo=UTC),
            )
            session.add(run)
            await session.flush()
            await session.commit()
    finally:
        await engine.dispose()

    response = await dev_client.get("/scheduled-briefs/status")
    body = response.json()
    assert body["latest_run_status"] == "succeeded"
    assert body["latest_brief_id"] is not None
    assert body["latest_brief_version"] == 3


async def test_refreshing_status_repeatedly_enqueues_and_records_nothing(
    dev_client: AsyncClient,
) -> None:
    user_id = await _login(dev_client, "refresh")
    await dev_client.put(
        "/preferences/scheduled_briefs_enabled",
        json={"value": {"enabled": True}},
        headers=CSRF_HEADERS,
    )
    for _ in range(5):
        response = await dev_client.get("/scheduled-briefs/status")
        assert response.status_code == 200

    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            runs = (
                (
                    await session.execute(
                        select(ScheduledBriefRun).where(ScheduledBriefRun.user_id == user_id)
                    )
                )
                .scalars()
                .all()
            )
            assert runs == []
            audits = (
                (
                    await session.execute(
                        select(AuditEvent).where(
                            AuditEvent.user_id == user_id,
                            AuditEvent.event_type.like("scheduled_brief.%"),
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert audits == []
    finally:
        await engine.dispose()


async def test_status_reports_scheduler_unavailable_without_breaking_the_route(
    dev_client_unreachable_redis: AsyncClient,
) -> None:
    await _login(dev_client_unreachable_redis, "no-redis")
    response = await dev_client_unreachable_redis.get("/scheduled-briefs/status")
    assert response.status_code == 200
    assert response.json()["scheduler_available"] is False

    # An ordinary route must also remain entirely unaffected.
    me = await dev_client_unreachable_redis.get("/me")
    assert me.status_code == 200


async def test_status_reports_scheduler_available_with_a_real_redis(
    dev_client_real_redis: AsyncClient,
) -> None:
    await _login(dev_client_real_redis, "with-redis")
    response = await dev_client_real_redis.get("/scheduled-briefs/status")
    assert response.status_code == 200
    if response.json()["scheduler_available"] is False:
        pytest.skip("Redis is not running (docker compose up -d redis --wait)")
    assert response.json()["scheduler_available"] is True
