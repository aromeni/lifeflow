"""Shared test helpers: materialise the demo dataset as in-memory SourceItems."""

import uuid
from datetime import UTC, date, datetime

from lifeflow_api.connectors.synthetic import SyntheticCalendarConnector, SyntheticEmailConnector
from lifeflow_api.models import SourceItem
from lifeflow_api.normalisation import email_to_source_item, event_to_source_item

ANCHOR = date(2026, 7, 15)  # Wednesday
REFERENCE = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)
TIMEZONE = "Europe/London"
TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def demo_source_items(user_id: uuid.UUID = TEST_USER_ID) -> list[SourceItem]:
    since = datetime(2026, 6, 15, tzinfo=UTC)
    until = datetime(2026, 8, 31, tzinfo=UTC)
    emails = await SyntheticEmailConnector(ANCHOR).fetch_recent(since=since, until=until)
    events = await SyntheticCalendarConnector(ANCHOR).fetch_events(since=since, until=until)
    return [
        *(email_to_source_item(m, user_id=user_id, account_id=None) for m in emails),
        *(event_to_source_item(e, user_id=user_id, account_id=None) for e in events),
    ]
