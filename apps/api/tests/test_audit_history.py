"""Stage 9 Delivery Phase 3 audit-history projection and privacy boundary."""

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL

from lifeflow_api.models import AuditEvent

pytestmark = pytest.mark.integration

SECRET_METADATA = "SENTINEL-RAW-AUDIT-METADATA"  # pragma: allowlist secret
SECRET_ENTITY = "SENTINEL-RAW-ENTITY-ID"  # pragma: allowlist secret
SECRET_CORRELATION = "SENTINEL-RAW-CORRELATION"  # pragma: allowlist secret


async def _login(client: AsyncClient, marker: str) -> uuid.UUID:
    response = await client.post(
        "/auth/dev-login",
        json={
            "email": f"audit-history-{marker}-{uuid.uuid4()}@example.com",
            "display_name": "Audit History",
        },
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200
    return uuid.UUID(response.json()["user_id"])


async def _replace_events(user_id: uuid.UUID, events: list[AuditEvent]) -> None:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            await session.execute(delete(AuditEvent).where(AuditEvent.user_id == user_id))
            session.add_all(events)
            await session.commit()
    finally:
        await engine.dispose()


def _event(
    user_id: uuid.UUID,
    event_type: str,
    *,
    timestamp: datetime,
    event_id: uuid.UUID | None = None,
    actor: str = "system:test",
    metadata: dict[str, object] | None = None,
) -> AuditEvent:
    return AuditEvent(
        id=event_id or uuid.uuid4(),
        user_id=user_id,
        actor=actor,
        event_type=event_type,
        entity_type="test_entity",
        entity_id=SECRET_ENTITY,
        timestamp=timestamp,
        safe_metadata_json=metadata or {},
        correlation_id=SECRET_CORRELATION,
    )


async def _event_count(user_id: uuid.UUID) -> int:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            result = await session.execute(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.user_id == user_id)
            )
            return int(result.scalar_one())
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_history_is_owner_scoped_read_only_and_requires_auth(
    dev_client: AsyncClient,
) -> None:
    unauthenticated = await dev_client.get("/audit-history")
    assert unauthenticated.status_code == 401

    other_user = await _login(dev_client, "other")
    now = datetime.now(UTC) - timedelta(minutes=1)
    await _replace_events(
        other_user,
        [
            _event(
                other_user,
                "account.deletion_requested",
                timestamp=now,
                metadata={"private": "OTHER-OWNER-SENTINEL"},
            )
        ],
    )

    third_user = await _login(dev_client, "owner")
    await _replace_events(
        third_user,
        [_event(third_user, "proposal.rejected", timestamp=now)],
    )
    before = await _event_count(third_user)
    history = await dev_client.get("/audit-history", params={"period": "all"})
    after = await _event_count(third_user)

    assert history.status_code == 200
    assert [item["title"] for item in history.json()["items"]] == ["Action rejected"]
    assert "OTHER-OWNER-SENTINEL" not in history.text
    assert before == after


@pytest.mark.asyncio
async def test_history_never_exposes_raw_audit_fields_or_unknown_events(
    dev_client: AsyncClient,
) -> None:
    user_id = await _login(dev_client, "privacy")
    now = datetime.now(UTC) - timedelta(minutes=1)
    await _replace_events(
        user_id,
        [
            _event(
                user_id,
                "memory.confirmed",
                timestamp=now,
                actor=f"user:{user_id}",
                metadata={
                    "value": SECRET_METADATA,
                    "reason": "SENTINEL-REJECTION-REASON",
                },
            ),
            _event(
                user_id,
                "unreviewed.new_event",
                timestamp=now,
                metadata={"value": "UNKNOWN-EVENT-SENTINEL"},
            ),
        ],
    )

    response = await dev_client.get("/audit-history", params={"period": "all"})

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "items": [
            {
                "id": body["items"][0]["id"],
                "occurred_at": body["items"][0]["occurred_at"],
                "category": "preferences",
                "actor": "you",
                "title": "Memory suggestion confirmed",
                "summary": "You confirmed a preference suggestion.",
                "tone": "success",
            }
        ],
        "next_cursor": None,
    }
    for sentinel in (
        SECRET_METADATA,
        SECRET_ENTITY,
        SECRET_CORRELATION,
        "SENTINEL-REJECTION-REASON",
        "UNKNOWN-EVENT-SENTINEL",
        str(user_id),
        "memory.confirmed",
        "safe_metadata",
        "entity_id",
        "correlation_id",
    ):
        assert sentinel not in response.text


@pytest.mark.asyncio
async def test_closed_category_and_period_filters(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "filters")
    now = datetime.now(UTC) - timedelta(minutes=1)
    await _replace_events(
        user_id,
        [
            _event(user_id, "proposal.created", timestamp=now),
            _event(user_id, "brief.generated", timestamp=now - timedelta(days=2)),
            _event(user_id, "account.connected", timestamp=now - timedelta(days=8)),
        ],
    )

    actions = await dev_client.get("/audit-history", params={"category": "actions", "period": "7d"})
    recent = await dev_client.get("/audit-history", params={"period": "7d"})
    everything = await dev_client.get("/audit-history", params={"period": "all"})

    assert [item["title"] for item in actions.json()["items"]] == ["Action proposed"]
    assert {item["title"] for item in recent.json()["items"]} == {
        "Action proposed",
        "Brief generated",
    }
    assert len(everything.json()["items"]) == 3
    assert (
        await dev_client.get("/audit-history", params={"category": "metadata"})
    ).status_code == 422
    assert (await dev_client.get("/audit-history", params={"period": "custom"})).status_code == 422


@pytest.mark.asyncio
async def test_keyset_pagination_is_stable_and_cursor_is_filter_bound(
    dev_client: AsyncClient,
) -> None:
    user_id = await _login(dev_client, "pagination")
    timestamp = datetime.now(UTC) - timedelta(hours=1)
    event_ids = [uuid.UUID(int=value) for value in (4, 3, 2, 1)]
    await _replace_events(
        user_id,
        [
            _event(
                user_id,
                "proposal.created",
                timestamp=timestamp,
                event_id=event_id,
            )
            for event_id in event_ids
        ],
    )

    first = await dev_client.get(
        "/audit-history",
        params={"category": "actions", "period": "all", "limit": 2},
    )
    assert first.status_code == 200
    first_body = first.json()
    assert [item["id"] for item in first_body["items"]] == [
        str(event_ids[0]),
        str(event_ids[1]),
    ]
    assert first_body["next_cursor"]

    # A later insert is outside the cursor's frozen as-of window.
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            session.add(
                _event(
                    user_id,
                    "proposal.approved",
                    timestamp=datetime.now(UTC) + timedelta(minutes=1),
                )
            )
            await session.commit()
    finally:
        await engine.dispose()

    second = await dev_client.get(
        "/audit-history",
        params={
            "category": "actions",
            "period": "all",
            "limit": 2,
            "cursor": first_body["next_cursor"],
        },
    )
    assert second.status_code == 200
    second_body = second.json()
    assert [item["id"] for item in second_body["items"]] == [
        str(event_ids[2]),
        str(event_ids[3]),
    ]
    assert second_body["next_cursor"] is None
    assert not (
        {item["id"] for item in first_body["items"]} & {item["id"] for item in second_body["items"]}
    )

    mismatch = await dev_client.get(
        "/audit-history",
        params={
            "category": "briefs",
            "period": "all",
            "cursor": first_body["next_cursor"],
        },
    )
    invalid = await dev_client.get("/audit-history", params={"cursor": "not-a-cursor!"})
    wrong_types = base64.urlsafe_b64encode(
        json.dumps(
            {
                "v": True,
                "as_of": timestamp.isoformat(),
                "before_timestamp": timestamp.isoformat(),
                "before_id": 7,
                "category": "all",
                "period": "7d",
            }
        ).encode()
    ).decode()
    invalid_types = await dev_client.get("/audit-history", params={"cursor": wrong_types})
    assert mismatch.status_code == 422
    assert invalid.status_code == 422
    assert invalid_types.status_code == 422


@pytest.mark.asyncio
async def test_privacy_events_render_plain_language_without_operation_details(
    dev_client: AsyncClient,
) -> None:
    user_id = await _login(dev_client, "deletion")
    now = datetime.now(UTC) - timedelta(minutes=1)
    await _replace_events(
        user_id,
        [
            _event(
                user_id,
                "data.import_deletion_completed",
                timestamp=now,
                metadata={
                    "deleted_counts": {"source_items": 42},
                    "error_code": "SENTINEL-ERROR-CODE",
                },
            )
        ],
    )

    response = await dev_client.get(
        "/audit-history", params={"category": "privacy", "period": "all"}
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["title"] == "Imported-data deletion completed"
    assert "deleted_counts" not in response.text
    assert "SENTINEL-ERROR-CODE" not in response.text


@pytest.mark.asyncio
async def test_cancelled_retention_operation_renders_through_the_api(
    dev_client: AsyncClient,
) -> None:
    """A user can cancel a still-pending retention operation (existing Phase 2
    cancel route, reachable regardless of operation type); that event must stay
    visible rather than silently vanishing because no presentation was registered."""
    user_id = await _login(dev_client, "retention-cancel")
    now = datetime.now(UTC) - timedelta(minutes=1)
    await _replace_events(
        user_id,
        [_event(user_id, "retention.operation_cancelled", timestamp=now)],
    )

    response = await dev_client.get(
        "/audit-history", params={"category": "privacy", "period": "all"}
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["title"] == "Retention cleanup cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "expected_title", "expected_summary"),
    [
        (
            "sync.completed",
            "Connection sync completed",
            "LifeFlow refreshed imported evidence.",
        ),
        (
            "execution.uncertain",
            "Execution needs review",
            "LifeFlow could not confirm the outcome and did not retry automatically.",
        ),
    ],
)
async def test_sync_and_execution_events_render_safely(
    dev_client: AsyncClient, event_type: str, expected_title: str, expected_summary: str
) -> None:
    """Connection-sync and execution-lifecycle events go through the same
    registry/API path as the categories covered above; this locks in the exact
    accurate uncertain-execution wording end-to-end (no automatic retry), not
    just as a static string in the registry."""
    user_id = await _login(dev_client, "sync-execution")
    now = datetime.now(UTC) - timedelta(minutes=1)
    await _replace_events(user_id, [_event(user_id, event_type, timestamp=now)])

    response = await dev_client.get("/audit-history", params={"period": "all"})

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["title"] == expected_title
    assert item["summary"] == expected_summary


@pytest.mark.asyncio
async def test_history_query_is_supported_by_the_user_time_index(
    dev_client: AsyncClient,
) -> None:
    """`list_history_page` filters by user_id and orders by timestamp; this
    pins that the existing `ix_audit_events_user_time` index still exists and
    still covers (user_id, timestamp), so the query has real index support as
    the log grows. A live EXPLAIN is not used here: the test database's tables
    are near-empty per test, so the planner would prefer a sequential scan
    regardless of the index, making a live-plan assertion flaky rather than
    meaningful."""
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            result = await session.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE tablename = 'audit_events' "
                    "AND indexname = 'ix_audit_events_user_time'"
                )
            )
            indexdef = result.scalar_one_or_none()
    finally:
        await engine.dispose()
    assert indexdef is not None, "expected index ix_audit_events_user_time to exist"
    assert "user_id" in indexdef
    assert "timestamp" in indexdef
