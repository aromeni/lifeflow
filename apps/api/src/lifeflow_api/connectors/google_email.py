"""GoogleEmailConnector — the real Gmail adapter (ADR 0001 D6, ADR 0003 D21).

Implements `EmailConnector` unchanged: `IngestionService` needed no changes
to consume this alongside `SyntheticEmailConnector`. Content is minimised at
the source — only From/To/Subject/Date/List-Unsubscribe headers (the last
solely as a bulk-mail marker, ADR 0003 D42) and Gmail's own short
`snippet` are ever fetched, never the full message body (threat model T3/
T15). Bounded to the requested window on first sync; subsequent syncs use
Gmail's `historyId` cursor, falling back to a full bounded resync on
HTTP 404 (expired historyId).

Cursor safety (Stage 7 remediation, independent-review blocker #3): the
committed `historyId` only ever advances once pagination has genuinely
completed. Hitting the page bound while a `nextPageToken` remains persists a
`GoogleSyncCursor` continuation instead — never a newly-returned historyId
— so a later sync resumes rather than silently skipping unseen pages.
"""

import json
import re
from datetime import UTC, datetime

from lifeflow_api.connectors.interfaces import EmailFolder, EmailMessage
from lifeflow_api.failure_taxonomy import classify_exception
from lifeflow_api.google.errors import GoogleClientError, GoogleHistoryExpiredError
from lifeflow_api.google.gmail_client import (
    GmailDraftClient,
    GmailHistoryPage,
    GmailMessage,
    GmailMessageSummary,
)
from lifeflow_api.google_sync_cursor import GoogleSyncCursor, decode_window, encode_window
from lifeflow_api.retry import retry_read


# Stage 9 Delivery Phase 5: every Gmail read on this connector's hot path
# (list_history/list_messages/get_current_history_id/get_message) is
# idempotent and safe to retry — `retry_read` only ever retries when
# `_is_retryable` is True, so a `GoogleClientError`/`GoogleHistoryExpiredError`
# (final/resync signal, not transient) still propagates on the first
# attempt exactly as before.
def _is_retryable(exc: BaseException) -> bool:
    return classify_exception(exc).retryable


_MAX_HISTORY_PAGES = 10
_MAX_WINDOW_PAGES = 5
_PAGE_SIZE = 50
# Gmail's History API documents that a `messageAdded` entry may reference a
# message that is no longer retrievable (deleted, or — as observed in real
# sandbox testing — a draft whose underlying message was superseded by a
# later edit). Google's own guidance is to treat this as expected and skip
# it, never to fail the sync: https://developers.google.com/gmail/api/guides/sync
_MESSAGE_NOT_FOUND_STATUS = 404

_FROM_PATTERN = re.compile(r'^"?(?P<name>[^"<]*)"?\s*<(?P<email>[^>]+)>$')


def _parse_from_header(value: str) -> tuple[str, str]:
    match = _FROM_PATTERN.match(value.strip())
    if match:
        name = match.group("name").strip() or match.group("email")
        return name, match.group("email")
    return value.strip(), value.strip()


def _folder_for(message: GmailMessage) -> EmailFolder | None:
    if "SENT" in message.label_ids:
        return EmailFolder.sent
    if "INBOX" in message.label_ids:
        return EmailFolder.inbox
    return None


def _to_email_message(message: GmailMessage) -> EmailMessage | None:
    folder = _folder_for(message)
    if folder is None:
        return None
    sender_name, sender_email = _parse_from_header(message.headers.get("From", ""))
    recipients = tuple(
        address.strip() for address in message.headers.get("To", "").split(",") if address.strip()
    )
    return EmailMessage(
        external_id=message.id,
        folder=folder,
        sender_name=sender_name,
        sender_email=sender_email,
        recipients=recipients,
        subject=message.headers.get("Subject", ""),
        # Deliberately the API's own short snippet, never the full body
        # (content minimisation, ADR 0003 D21) — detectors see less text
        # than in demo mode, a known, accepted Stage 7 trade-off.
        body_text=message.snippet,
        sent_at=datetime.fromtimestamp(message.internal_date_ms / 1000, tz=UTC),
        thread_id=message.thread_id,
        # Header names arrive with the sender's own casing — compare
        # case-insensitively (ADR 0003 D42).
        list_unsubscribe=any(name.lower() == "list-unsubscribe" for name in message.headers),
    )


def _is_encoded_window(value: str) -> bool:
    """Distinguishes a persisted windowed-continuation marker (a JSON
    `[since, until]` pair) from a bare Gmail `historyId` (always a plain
    decimal string, which never unpacks as a two-element sequence)."""
    try:
        decode_window(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return True


class GoogleEmailConnector:
    """One connector instance per sync: construct, call `fetch_recent`
    once, then read `result_cursor` to persist the updated cursor state.

    `cursor_status`, `sync_complete`, `excluded_count`, and `incomplete_count`
    exist purely to give `GoogleSyncService`/the sync API something honest to
    report back (Stage 7 remediation) — they don't affect ingestion
    behaviour. `excluded_count` is *not* a failure count: every message it
    counts was read successfully and deliberately excluded for being outside
    Inbox/Sent (D21) — a normal, expected outcome for any real mailbox with
    Archived/Spam/Promotions/Social traffic in the sync window, never
    surfaced as an error. `incomplete_count` is the genuine failure count: a
    message id Gmail's history/list API returned could not be fetched
    (HTTP 404 — real sandbox finding, D38) because the message no longer
    exists or is no longer accessible; that one message is skipped, never
    the rest of the sync."""

    def __init__(
        self,
        client: GmailDraftClient,
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
        self.excluded_count = 0
        self.incomplete_count = 0

    async def fetch_recent(self, *, since: datetime, until: datetime) -> list[EmailMessage]:
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
                return await self._fetch_history(
                    base,
                    page_token=cursor.continuation_page_token,
                    status_if_complete="incremental",
                )
            except (GoogleHistoryExpiredError, GoogleClientError):
                return await self._fetch_windowed(
                    since, until, page_token=None, status_if_complete="resynced"
                )
        if cursor.committed_cursor:
            try:
                return await self._fetch_history(
                    cursor.committed_cursor, page_token=None, status_if_complete="incremental"
                )
            except GoogleHistoryExpiredError:
                return await self._fetch_windowed(
                    since, until, page_token=None, status_if_complete="resynced"
                )
        return await self._fetch_windowed(
            since, until, page_token=None, status_if_complete="initial"
        )

    async def _fetch_history(
        self, base_history_id: str, *, page_token: str | None, status_if_complete: str
    ) -> list[EmailMessage]:
        message_ids: list[str] = []
        latest_history_id = base_history_id
        current_page_token = page_token
        completed = False
        for _ in range(_MAX_HISTORY_PAGES):

            async def _fetch_page(token: str | None = current_page_token) -> GmailHistoryPage:
                return await self._client.list_history(
                    access_token=self._access_token,
                    start_history_id=base_history_id,
                    page_token=token,
                )

            page = await retry_read(_fetch_page, is_retryable=_is_retryable)
            message_ids.extend(page.message_ids)
            latest_history_id = page.history_id
            current_page_token = page.next_page_token
            if not current_page_token:
                completed = True
                break
        messages = await self._resolve_messages(message_ids)
        if completed:
            self.cursor_status = status_if_complete
            self.sync_complete = True
            self.result_cursor = GoogleSyncCursor(
                committed_cursor=latest_history_id,
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
                # historyId is preserved exactly.
                committed_cursor=self._cursor.committed_cursor,
                continuation_page_token=current_page_token,
                continuation_base_cursor=base_history_id,
                sync_in_progress=True,
                last_complete_sync_at=self._cursor.last_complete_sync_at,
            )
        return messages

    async def _fetch_windowed(
        self,
        since: datetime,
        until: datetime,
        *,
        page_token: str | None,
        status_if_complete: str,
    ) -> list[EmailMessage]:
        query = f"after:{int(since.timestamp())} before:{int(until.timestamp())}"
        message_ids: list[str] = []
        current_page_token = page_token
        completed = False
        for _ in range(_MAX_WINDOW_PAGES):

            async def _fetch_page(
                token: str | None = current_page_token,
            ) -> tuple[tuple[GmailMessageSummary, ...], str | None]:
                return await self._client.list_messages(
                    access_token=self._access_token,
                    query=query,
                    page_token=token,
                    max_results=_PAGE_SIZE,
                )

            summaries, next_token = await retry_read(_fetch_page, is_retryable=_is_retryable)
            message_ids.extend(summary.id for summary in summaries)
            current_page_token = next_token
            if not current_page_token:
                completed = True
                break
        messages = await self._resolve_messages(message_ids)
        if completed:
            new_history_id = await retry_read(
                lambda: self._client.get_current_history_id(access_token=self._access_token),
                is_retryable=_is_retryable,
            )
            self.cursor_status = status_if_complete
            self.sync_complete = True
            self.result_cursor = GoogleSyncCursor(
                committed_cursor=new_history_id,
                continuation_page_token=None,
                continuation_base_cursor=None,
                sync_in_progress=False,
                last_complete_sync_at=datetime.now(UTC),
            )
        else:
            self.cursor_status = "incomplete"
            self.sync_complete = False
            self.result_cursor = GoogleSyncCursor(
                # A full resync in progress never advances the (possibly
                # already-expired) prior committed cursor early.
                committed_cursor=self._cursor.committed_cursor,
                continuation_page_token=current_page_token,
                continuation_base_cursor=encode_window(since, until),
                sync_in_progress=True,
                last_complete_sync_at=self._cursor.last_complete_sync_at,
            )
        return messages

    async def _resolve_messages(self, message_ids: list[str]) -> list[EmailMessage]:
        messages = []
        for message_id in message_ids:
            try:

                async def _fetch_message(mid: str = message_id) -> GmailMessage:
                    return await self._client.get_message(
                        access_token=self._access_token, message_id=mid
                    )

                raw = await retry_read(_fetch_message, is_retryable=_is_retryable)
            except GoogleClientError as exc:
                if exc.status_code != _MESSAGE_NOT_FOUND_STATUS:
                    raise
                # Expected per Gmail's own documentation: a history/list
                # entry can reference a message no longer retrievable. Skip
                # just this one message rather than failing the whole sync
                # (real sandbox finding, D38).
                self.incomplete_count += 1
                continue
            converted = _to_email_message(raw)
            if converted is not None:
                messages.append(converted)
            else:
                self.excluded_count += 1
        return sorted(messages, key=lambda m: (m.sent_at, m.external_id))


__all__ = ["GoogleEmailConnector"]
