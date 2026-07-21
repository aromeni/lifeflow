"""GoogleSyncService — orchestrates a real Gmail + Calendar sync.

Resolves a valid access token (refreshing under a row lock if needed),
constructs the two connector adapters with the account's current cursors,
runs the existing `IngestionService` unchanged, then persists whatever
cursors the connectors advanced to. `IngestionService` itself needed no
changes for real data (ADR 0001 D6) — this module only adds the
cursor-persistence step the synthetic connectors never needed.

Each source is synced only if its read scope was actually granted (a
partial grant, e.g. Calendar declined, must not fail the whole sync or call
an endpoint without permission) — a `_NullConnector` stands in for the
declined side so `IngestionService.import_sources` needs no changes either.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.accounts import GoogleTokenService, ReauthorisationRequiredError
from lifeflow_api.connectors.google_calendar import GoogleCalendarConnector
from lifeflow_api.connectors.google_email import GoogleEmailConnector
from lifeflow_api.connectors.interfaces import CalendarEvent, EmailMessage
from lifeflow_api.google.calendar_client import CalendarEventClient
from lifeflow_api.google.gmail_client import GmailDraftClient
from lifeflow_api.google.oauth import GoogleOAuthClient
from lifeflow_api.google_scopes import CALENDAR_READONLY_SCOPE, GMAIL_READONLY_SCOPE
from lifeflow_api.google_sync_cursor import cursor_from_stored, cursor_to_stored
from lifeflow_api.ingestion import IngestionService
from lifeflow_api.models import AccountStatus
from lifeflow_api.repositories import ConnectedAccountRepository
from lifeflow_api.security.token_cipher import TokenCipher

GOOGLE_PROVIDER = "google"


class GoogleReadScopeMissingError(Exception):
    """Neither Gmail nor Calendar read access was granted — there is nothing
    this sync could do (distinct from `ReauthorisationRequiredError`, which
    means no usable account/token exists at all)."""


class _NullEmailConnector:
    """Stands in for Gmail when `gmail.readonly` wasn't granted — never
    calls the Gmail API, never blocks the Calendar half of the sync."""

    async def fetch_recent(self, *, since: datetime, until: datetime) -> list[EmailMessage]:
        return []


class _NullCalendarConnector:
    """Stands in for Calendar when `calendar.readonly` wasn't granted."""

    async def fetch_events(self, *, since: datetime, until: datetime) -> list[CalendarEvent]:
        return []


@dataclass(frozen=True)
class GoogleSyncSummary:
    imported: int
    updated: int
    unchanged: int
    # Deliberately separate counts, not one combined "incomplete" — they
    # mean very different things and conflating them misreports a normal
    # outcome as a failure (Stage 7 focused remediation): `gmail_excluded`
    # is messages read successfully but outside Inbox/Sent (by design, D21);
    # `gmail_incomplete` is Gmail messages that genuinely could not be
    # fetched (HTTP 404 on a history-referenced id, D38); `calendar_incomplete`
    # is events that genuinely could not be parsed.
    gmail_excluded: int
    gmail_incomplete: int
    calendar_incomplete: int
    gmail_synced: bool
    gmail_cursor_status: str
    gmail_sync_complete: bool
    calendar_synced: bool
    calendar_cursor_status: str
    calendar_sync_complete: bool


class GoogleSyncService:
    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        cipher: TokenCipher,
        oauth_client: GoogleOAuthClient,
        gmail_client: GmailDraftClient,
        calendar_client: CalendarEventClient,
        client_id: str,
        client_secret: str,
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._accounts = ConnectedAccountRepository(session, user_id)
        self._tokens = GoogleTokenService(
            session,
            user_id,
            cipher,
            oauth_client,
            client_id=client_id,
            client_secret=client_secret,
        )
        self._gmail_client = gmail_client
        self._calendar_client = calendar_client

    async def sync(self, *, since: datetime, until: datetime) -> GoogleSyncSummary:
        account = await self._accounts.get_by_provider(GOOGLE_PROVIDER)
        if account is None or account.status != AccountStatus.active:
            raise ReauthorisationRequiredError("No active Google account is connected.")

        granted = set(account.granted_scopes)
        sync_gmail = GMAIL_READONLY_SCOPE in granted
        sync_calendar = CALENDAR_READONLY_SCOPE in granted
        if not sync_gmail and not sync_calendar:
            raise GoogleReadScopeMissingError(
                "Neither Gmail nor Calendar read access has been granted."
            )

        access_token = await self._tokens.get_valid_access_token(GOOGLE_PROVIDER)
        cursors = dict(account.sync_cursors)

        email_connector: GoogleEmailConnector | _NullEmailConnector
        if sync_gmail:
            email_connector = GoogleEmailConnector(
                self._gmail_client,
                access_token=access_token,
                cursor=cursor_from_stored(cursors.get("gmail")),
            )
        else:
            email_connector = _NullEmailConnector()

        calendar_connector: GoogleCalendarConnector | _NullCalendarConnector
        if sync_calendar:
            calendar_connector = GoogleCalendarConnector(
                self._calendar_client,
                access_token=access_token,
                cursor=cursor_from_stored(cursors.get("calendar")),
            )
        else:
            calendar_connector = _NullCalendarConnector()

        import_summary = await IngestionService(self._session, self._user_id).import_sources(
            email_connector=email_connector,
            calendar_connector=calendar_connector,
            account_id=account.id,
            since=since,
            until=until,
        )

        updated_cursors = dict(account.sync_cursors)
        gmail_excluded = 0
        gmail_incomplete = 0
        gmail_cursor_status = "not_granted"
        gmail_sync_complete = True
        if isinstance(email_connector, GoogleEmailConnector):
            updated_cursors["gmail"] = cursor_to_stored(email_connector.result_cursor)
            gmail_excluded = email_connector.excluded_count
            gmail_incomplete = email_connector.incomplete_count
            gmail_cursor_status = email_connector.cursor_status
            gmail_sync_complete = email_connector.sync_complete

        calendar_incomplete = 0
        calendar_cursor_status = "not_granted"
        calendar_sync_complete = True
        if isinstance(calendar_connector, GoogleCalendarConnector):
            updated_cursors["calendar"] = cursor_to_stored(calendar_connector.result_cursor)
            calendar_incomplete = calendar_connector.incomplete_count
            calendar_cursor_status = calendar_connector.cursor_status
            calendar_sync_complete = calendar_connector.sync_complete

        account.sync_cursors = updated_cursors
        await self._session.flush()

        return GoogleSyncSummary(
            imported=import_summary.imported,
            updated=import_summary.updated,
            unchanged=import_summary.skipped,
            gmail_excluded=gmail_excluded,
            gmail_incomplete=gmail_incomplete,
            calendar_incomplete=calendar_incomplete,
            gmail_synced=sync_gmail,
            gmail_cursor_status=gmail_cursor_status,
            gmail_sync_complete=gmail_sync_complete,
            calendar_synced=sync_calendar,
            calendar_cursor_status=calendar_cursor_status,
            calendar_sync_complete=calendar_sync_complete,
        )


__all__ = [
    "GOOGLE_PROVIDER",
    "GoogleReadScopeMissingError",
    "GoogleSyncService",
    "GoogleSyncSummary",
]
