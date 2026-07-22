"""Shared test helpers: materialise the demo dataset as in-memory SourceItems.

Two clocks exist deliberately (and must not be mixed up):

- The frozen ``ANCHOR``/``REFERENCE`` — for suites that pass an explicit
  reference into detection/generation AND validate with a frozen
  ``now_factory``: fully deterministic, assertable absolute dates, never
  touches wall time.
- A live, caller-supplied reference — REQUIRED for suites that approve or
  execute through the real app (route-level tests), because the app checks
  proposal expiry and event start times against ``datetime.now(UTC)``. A
  route-level suite seeded from the frozen clock rots: every proposal it
  generates expires seven days after the frozen reference, regardless of
  when the test runs.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from lifeflow_api.connectors.interfaces import EmailFolder, EmailMessage
from lifeflow_api.connectors.synthetic import SyntheticCalendarConnector, SyntheticEmailConnector
from lifeflow_api.models import SourceItem
from lifeflow_api.normalisation import email_to_source_item, event_to_source_item

ANCHOR = date(2026, 7, 15)  # Wednesday
REFERENCE = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)
TIMEZONE = "Europe/London"
TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def demo_source_items(
    user_id: uuid.UUID = TEST_USER_ID,
    *,
    account_id: uuid.UUID | None = None,
    anchor: date | None = None,
) -> list[SourceItem]:
    """`account_id=None` (the default) matches every existing caller: no
    connected-account linkage, which `execution_context.resolve_execution_context`
    treats as synthetic/simulation-only evidence. Pass a real Google
    `ConnectedAccount.id` to build Google-sourced evidence instead (Stage 7
    remediation blocker #1 tests).

    `anchor=None` keeps the frozen `ANCHOR`; wall-clock (route-level) suites
    must pass today's date so the dataset's relative day-offsets — and the
    proposals generated from them — are valid against the real clock."""
    anchor = anchor or ANCHOR
    since = datetime(anchor.year, anchor.month, anchor.day, tzinfo=UTC) - timedelta(days=30)
    until = datetime(anchor.year, anchor.month, anchor.day, tzinfo=UTC) + timedelta(days=47)
    emails = await SyntheticEmailConnector(anchor).fetch_recent(since=since, until=until)
    events = await SyntheticCalendarConnector(anchor).fetch_events(since=since, until=until)
    return [
        *(email_to_source_item(m, user_id=user_id, account_id=account_id) for m in emails),
        *(event_to_source_item(e, user_id=user_id, account_id=account_id) for e in events),
    ]


def scheduling_email_source(
    user_id: uuid.UUID = TEST_USER_ID,
    *,
    account_id: uuid.UUID | None = None,
    ref: str = "em-sched-helper",
    reference: datetime = REFERENCE,
) -> SourceItem:
    """A fully-specified inbound scheduling request (ADR 0003 D39) — since
    D41 gated the demo "(proposed)" placeholder convention to synthetic
    evidence, this email is THE way Google-sourced fixtures obtain a
    `create_calendar_event` proposal, exactly like a real user.

    The event date is written dynamically, eight days after ``reference``
    (with the matching weekday, which the extractor cross-checks), so the
    fixture is deterministic under the frozen clock and never in the past
    under a live one — no hard-coded date that rots as wall time passes."""
    event_day = (reference.astimezone(ZoneInfo(TIMEZONE)) + timedelta(days=8)).date()
    written_date = event_day.strftime("%A %-d %B %Y")
    message = EmailMessage(
        external_id=ref,
        folder=EmailFolder.inbox,
        sender_name="Rachel Ferris",
        sender_email="rachel@thameside-analytics.example",
        recipients=("me@example.test",),
        subject="Please schedule the LifeFlow sandbox sync",
        body_text=(
            "Please schedule a 30-minute calendar event called "
            f"'LifeFlow sandbox sync' for {written_date}, from 4:00 PM "
            "to 4:30 PM Europe/London. Please add my email address as the "
            "attendee. Thanks, Rachel"
        ),
        sent_at=reference,
        thread_id=f"thread-{ref}",
    )
    return email_to_source_item(message, user_id=user_id, account_id=account_id)
