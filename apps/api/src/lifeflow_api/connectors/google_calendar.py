"""GoogleCalendarConnector — the real Calendar adapter (ADR 0001 D6, ADR 0003 D21).

Implements `CalendarConnector` unchanged. Bounded to the requested window on
first sync; subsequent syncs use Calendar's native `syncToken`, falling back
to a full bounded resync on HTTP 410 (invalid syncToken).

Cursor safety (Stage 7 remediation, independent-review blocker #3): Calendar
only ever returns a genuine `nextSyncToken` on the true final page — a
response still carrying `nextPageToken` must not be treated as final. The
committed sync token only ever advances once pagination has genuinely
completed; hitting the page bound first persists a `GoogleSyncCursor`
continuation instead, so a later sync resumes rather than silently skipping
unseen pages.
"""

import json
from datetime import UTC, datetime

from lifeflow_api.connectors.interfaces import CalendarEvent
from lifeflow_api.failure_taxonomy import classify_exception
from lifeflow_api.google.calendar_client import (
    CalendarEventClient,
    CalendarEventsPage,
    CalendarEventSummary,
)
from lifeflow_api.google.errors import GoogleClientError, GoogleSyncTokenExpiredError
from lifeflow_api.google_sync_cursor import GoogleSyncCursor, decode_window, encode_window
from lifeflow_api.retry import retry_read

_MAX_PAGES = 10
_PAGE_SIZE = 100


def _is_retryable(exc: BaseException) -> bool:
    return classify_exception(exc).retryable


def _to_calendar_event(summary: CalendarEventSummary) -> CalendarEvent | None:
    if summary.status == "cancelled":
        return None
    starts_at = _parse_event_time(summary.start)
    ends_at = _parse_event_time(summary.end)
    if starts_at is None or ends_at is None:
        return None
    all_day = "T" not in summary.start
    return CalendarEvent(
        external_id=summary.id,
        title=summary.summary,
        organiser_email=summary.attendees[0] if summary.attendees else "",
        starts_at=starts_at,
        ends_at=ends_at,
        all_day=all_day,
        location=None,
        description="",
        attendees=summary.attendees,
    )


def _parse_event_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # All-day events carry a bare date (e.g. "2026-07-20"), never a UTC
        # offset — timed events always do. Left naive, a page mixing both
        # (any real calendar) fails to sort in `_convert` below with
        # "can't compare offset-naive and offset-aware datetimes". Normalise
        # to UTC midnight (A2: UTC storage everywhere) so every `CalendarEvent`
        # is always aware, regardless of source shape.
        return parsed.replace(tzinfo=UTC)
    return parsed


def _is_encoded_window(value: str) -> bool:
    """Distinguishes a persisted windowed-continuation marker (a JSON
    `[since, until]` pair) from a bare Calendar `syncToken` (an opaque
    Google-issued string that never happens to decode as a two-element
    JSON sequence)."""
    try:
        decode_window(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return True


class GoogleCalendarConnector:
    """One connector instance per sync: construct, call `fetch_events` once,
    then read `result_cursor` to persist the updated cursor state.

    `cursor_status`, `sync_complete`, and `incomplete_count` exist purely to
    give `GoogleSyncService`/the sync API something honest to report back
    (Stage 7 remediation) — they don't affect ingestion behaviour.
    `incomplete_count` is a genuine "could not be processed" count (a
    non-cancelled event whose start/end couldn't be parsed) — unlike
    `GoogleEmailConnector.excluded_count`, this is never routine scope
    filtering, so it stays reported to the user as worth noticing."""

    def __init__(
        self,
        client: CalendarEventClient,
        *,
        access_token: str,
        cursor: GoogleSyncCursor,
    ) -> None:
        self._client = client
        self._access_token = access_token
        self._cursor = cursor
        self.result_cursor: GoogleSyncCursor = cursor
        self.cursor_status: str = "initial"
        self.sync_complete = True
        self.incomplete_count = 0

    async def fetch_events(self, *, since: datetime, until: datetime) -> list[CalendarEvent]:
        cursor = self._cursor
        if cursor.has_continuation:
            base = cursor.continuation_base_cursor
            assert base is not None  # noqa: S101 -- has_continuation implies a base
            if _is_encoded_window(base):
                resume_since, resume_until = decode_window(base)
                try:
                    return await self._fetch_windowed(
                        resume_since,
                        resume_until,
                        page_token=cursor.continuation_page_token,
                        status_if_complete="incremental",
                    )
                except GoogleClientError:
                    # The persisted continuation page token itself is no
                    # longer valid — clear it safely and restart the
                    # windowed resync fresh rather than skip the pages it
                    # would have covered.
                    return await self._fetch_windowed(
                        since, until, page_token=None, status_if_complete="resynced"
                    )
            try:
                return await self._fetch_sync_token(
                    base,
                    page_token=cursor.continuation_page_token,
                    status_if_complete="incremental",
                )
            except (GoogleSyncTokenExpiredError, GoogleClientError):
                return await self._fetch_windowed(
                    since, until, page_token=None, status_if_complete="resynced"
                )
        if cursor.committed_cursor:
            try:
                return await self._fetch_sync_token(
                    cursor.committed_cursor, page_token=None, status_if_complete="incremental"
                )
            except GoogleSyncTokenExpiredError:
                return await self._fetch_windowed(
                    since, until, page_token=None, status_if_complete="resynced"
                )
        return await self._fetch_windowed(
            since, until, page_token=None, status_if_complete="initial"
        )

    async def _fetch_sync_token(
        self, base_sync_token: str, *, page_token: str | None, status_if_complete: str
    ) -> list[CalendarEvent]:
        summaries: list[CalendarEventSummary] = []
        current_page_token = page_token
        final_sync_token: str | None = None
        completed = False
        for _ in range(_MAX_PAGES):

            async def _fetch_page(token: str | None = current_page_token) -> CalendarEventsPage:
                return await self._client.list_events(
                    access_token=self._access_token,
                    time_min=None,
                    time_max=None,
                    sync_token=None if token else base_sync_token,
                    page_token=token,
                    max_results=_PAGE_SIZE,
                )

            page = await retry_read(_fetch_page, is_retryable=_is_retryable)
            summaries.extend(page.events)
            current_page_token = page.next_page_token
            if not current_page_token:
                # True final page: only here is `nextSyncToken` authoritative.
                final_sync_token = page.next_sync_token
                completed = True
                break
        events, incomplete = _convert(summaries)
        self.incomplete_count += incomplete
        self._finish(
            completed=completed,
            final_cursor=final_sync_token,
            continuation_page_token=current_page_token,
            continuation_base_cursor=base_sync_token,
            status_if_complete=status_if_complete,
        )
        return events

    async def _fetch_windowed(
        self,
        since: datetime,
        until: datetime,
        *,
        page_token: str | None,
        status_if_complete: str,
    ) -> list[CalendarEvent]:
        summaries: list[CalendarEventSummary] = []
        current_page_token = page_token
        final_sync_token: str | None = None
        completed = False
        for _ in range(_MAX_PAGES):

            async def _fetch_page(token: str | None = current_page_token) -> CalendarEventsPage:
                return await self._client.list_events(
                    access_token=self._access_token,
                    time_min=since,
                    time_max=until,
                    sync_token=None,
                    page_token=token,
                    max_results=_PAGE_SIZE,
                )

            page = await retry_read(_fetch_page, is_retryable=_is_retryable)
            summaries.extend(page.events)
            current_page_token = page.next_page_token
            if not current_page_token:
                final_sync_token = page.next_sync_token
                completed = True
                break
        events, incomplete = _convert(summaries)
        self.incomplete_count += incomplete
        self._finish(
            completed=completed,
            final_cursor=final_sync_token,
            continuation_page_token=current_page_token,
            continuation_base_cursor=encode_window(since, until),
            status_if_complete=status_if_complete,
        )
        return events

    def _finish(
        self,
        *,
        completed: bool,
        final_cursor: str | None,
        continuation_page_token: str | None,
        continuation_base_cursor: str,
        status_if_complete: str,
    ) -> None:
        if completed:
            self.cursor_status = status_if_complete
            self.sync_complete = True
            self.result_cursor = GoogleSyncCursor(
                committed_cursor=final_cursor or self._cursor.committed_cursor,
                continuation_page_token=None,
                continuation_base_cursor=None,
                sync_in_progress=False,
                last_complete_sync_at=datetime.now(UTC),
            )
        else:
            self.cursor_status = "incomplete"
            self.sync_complete = False
            self.result_cursor = GoogleSyncCursor(
                # Never advance past unseen pages — the previously committed
                # syncToken is preserved exactly.
                committed_cursor=self._cursor.committed_cursor,
                continuation_page_token=continuation_page_token,
                continuation_base_cursor=continuation_base_cursor,
                sync_in_progress=True,
                last_complete_sync_at=self._cursor.last_complete_sync_at,
            )


def _convert(summaries: list[CalendarEventSummary]) -> tuple[list[CalendarEvent], int]:
    events: list[CalendarEvent] = []
    incomplete = 0
    for summary in summaries:
        event = _to_calendar_event(summary)
        if event is None:
            if summary.status != "cancelled":
                incomplete += 1
        else:
            events.append(event)
    return sorted(events, key=lambda e: (e.starts_at, e.external_id)), incomplete


__all__ = ["GoogleCalendarConnector"]
