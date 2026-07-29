"""Ingestion is idempotent and audited (Stage 3)."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL

from lifeflow_api.connectors.synthetic import SyntheticCalendarConnector, SyntheticEmailConnector
from lifeflow_api.detectors import detect_follow_ups
from lifeflow_api.ingestion import IngestionService
from lifeflow_api.models import SourceItem, User
from lifeflow_api.repositories import SourceItemRepository

pytestmark = pytest.mark.integration

ANCHOR = date(2026, 7, 15)
SINCE = datetime(2026, 7, 1, tzinfo=UTC)
UNTIL = datetime(2026, 8, 31, tzinfo=UTC)

# An anchor well over a year later than ANCHOR, with a window spanning the same
# relative offsets, to prove demo behaviour never depends on the real calendar
# date (the "Waiting for" wall-clock time-bomb, Stage 9 Delivery Phase 1).
LATER_ANCHOR = date(2027, 9, 20)
LATER_SINCE = datetime(2027, 9, 6, tzinfo=UTC)
LATER_UNTIL = datetime(2027, 11, 6, tzinfo=UTC)


async def _import_at(
    session: AsyncSession, user: User, anchor: date, since: datetime, until: datetime
) -> tuple[int, int, int]:
    summary = await IngestionService(session, user.id).import_sources(
        email_connector=SyntheticEmailConnector(anchor),
        calendar_connector=SyntheticCalendarConnector(anchor),
        account_id=None,
        since=since,
        until=until,
    )
    return summary.imported, summary.updated, summary.skipped


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.commit()
    await engine.dispose()


@pytest.fixture
async def user(session: AsyncSession) -> User:
    user = User(email="demo@lifeflow.local", display_name="Demo User")
    session.add(user)
    await session.flush()
    return user


async def _run_import(session: AsyncSession, user: User) -> tuple[int, int, int]:
    summary = await IngestionService(session, user.id).import_sources(
        email_connector=SyntheticEmailConnector(ANCHOR),
        calendar_connector=SyntheticCalendarConnector(ANCHOR),
        account_id=None,
        since=SINCE,
        until=UNTIL,
    )
    return summary.imported, summary.updated, summary.skipped


async def test_first_import_stores_all_items(session: AsyncSession, user: User) -> None:
    imported, updated, skipped = await _run_import(session, user)
    assert imported == 36  # 24 emails + 12 events
    assert updated == 0 and skipped == 0


async def test_reimport_is_idempotent(session: AsyncSession, user: User) -> None:
    await _run_import(session, user)
    imported, updated, skipped = await _run_import(session, user)
    assert imported == 0 and updated == 0 and skipped == 36

    count = (await session.execute(text("SELECT count(*) FROM source_items"))).scalar()
    assert count == 36  # no duplicates


async def test_changed_content_updates_in_place(session: AsyncSession, user: User) -> None:
    await _run_import(session, user)
    repo = SourceItemRepository(session, user.id)
    item = await repo.get_by_external("email", "em-001")
    assert item is not None
    item.content_fingerprint = "stale"
    await session.flush()

    imported, updated, skipped = await _run_import(session, user)
    assert imported == 0 and updated == 1 and skipped == 35

    refreshed = await repo.get_by_external("email", "em-001")
    assert refreshed is not None and refreshed.content_fingerprint != "stale"


async def test_reimport_at_a_new_anchor_moves_occurred_at_forward(
    session: AsyncSession, user: User
) -> None:
    """The demo must always 'look current' — a returning demo user's items
    must re-anchor to the new day, never freeze at their first import. The
    content fingerprint includes the materialised date, so re-importing the
    same demo email a year later is an in-place UPDATE that moves occurred_at
    forward (no duplication). This guards the fix's premise: if the date were
    ever dropped from the fingerprint, demo dates would freeze and the brief
    would drift with wall-clock time (the E2E `demo-brief` time-bomb)."""
    await _run_import(session, user)
    repo = SourceItemRepository(session, user.id)
    invoice = await repo.get_by_external("email", "em-002")  # a sent, no-reply thread
    assert invoice is not None
    first_occurred = invoice.occurred_at

    # Re-import the same dataset over a year later.
    imported, updated, skipped = await _import_at(
        session, user, LATER_ANCHOR, LATER_SINCE, LATER_UNTIL
    )
    assert imported == 0 and updated == 36 and skipped == 0  # re-anchored in place
    count = (await session.execute(text("SELECT count(*) FROM source_items"))).scalar()
    assert count == 36  # no duplication

    refreshed = await repo.get_by_external("email", "em-002")
    assert refreshed is not None
    # occurred_at moved forward to the new anchor (em-002 is day_offset -6).
    assert refreshed.occurred_at > first_occurred
    assert refreshed.occurred_at.astimezone(UTC).date() == LATER_ANCHOR - timedelta(days=6)


async def test_demo_yields_a_waiting_for_signal_regardless_of_calendar_date(
    session: AsyncSession, user: User
) -> None:
    """The demo journey's 'Waiting for' section must be deterministic at any
    real date. Ingest at a far-future anchor and confirm a follow-up
    (waiting-for) signal is produced with the reference clock at that date."""
    await _import_at(session, user, LATER_ANCHOR, LATER_SINCE, LATER_UNTIL)
    items = await SourceItemRepository(session, user.id).list(limit=500)
    reference = datetime.combine(LATER_ANCHOR, time(9, 0), tzinfo=UTC)
    follow_ups = detect_follow_ups(items, reference=reference)
    assert len(follow_ups) >= 1  # e.g. the unanswered invoice thread (em-002)


async def test_import_writes_a_sync_audit_event(session: AsyncSession, user: User) -> None:
    await _run_import(session, user)
    events = (await session.execute(text("SELECT event_type FROM audit_events"))).scalars().all()
    assert "sync.completed" in events


async def test_retention_expiry_is_set(session: AsyncSession, user: User) -> None:
    await _run_import(session, user)
    items = await SourceItemRepository(session, user.id).list(limit=500)
    assert all(item.retention_expires_at is not None for item in items)


async def test_source_items_are_isolated_between_users(session: AsyncSession, user: User) -> None:
    await _run_import(session, user)
    other = User(email="other@example.test", display_name="Other")
    session.add(other)
    await session.flush()

    other_repo = SourceItemRepository(session, other.id)
    assert await other_repo.list(limit=500) == []
    mine = await SourceItemRepository(session, user.id).list(limit=1)
    assert await other_repo.get(mine[0].id) is None

    with pytest.raises(ValueError, match="does not belong"):
        other_repo.add(
            SourceItem(
                user_id=user.id,
                source_type="email",
                external_id="x",
                title="t",
                occurred_at=datetime.now(UTC),
                content_fingerprint="f",
            )
        )
