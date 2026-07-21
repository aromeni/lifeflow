"""GoogleSyncCursor — cursor state that survives a page-bounded sync without
ever losing unseen pages (Stage 7 remediation, independent-review blocker
#3).

Gmail and Calendar connectors bound how many pages they fetch per sync call
(`_MAX_HISTORY_PAGES`/`_MAX_WINDOW_PAGES`/`_MAX_PAGES`). Before this module,
hitting that bound while a `nextPageToken` still existed did not stop the
connector from advancing its committed cursor to whatever historyId/
syncToken the last-fetched page happened to report — silently and
permanently skipping every page beyond the bound.

The fix separates two ideas that a single string cursor conflated:

- `committed_cursor` — the historyId/syncToken a sync has fully, genuinely
  completed through. Only ever advanced when pagination truly finished.
- `continuation_page_token`/`continuation_base_cursor` — where an
  incomplete sync left off, so the next sync resumes there instead of
  re-starting from `committed_cursor` (which would re-import already-seen
  pages) or silently skipping ahead (which would lose unseen ones).
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class GoogleSyncCursor:
    committed_cursor: str | None
    continuation_page_token: str | None
    continuation_base_cursor: str | None
    sync_in_progress: bool
    last_complete_sync_at: datetime | None

    @property
    def has_continuation(self) -> bool:
        return self.continuation_page_token is not None


EMPTY_CURSOR = GoogleSyncCursor(
    committed_cursor=None,
    continuation_page_token=None,
    continuation_base_cursor=None,
    sync_in_progress=False,
    last_complete_sync_at=None,
)


def cursor_from_stored(value: Any) -> GoogleSyncCursor:
    """Reads whatever is currently in `ConnectedAccount.sync_cursors[source]`.
    Accepts a bare string too — the pre-remediation shape, where the whole
    value WAS the committed cursor — so upgrading this deployment never
    loses an account's existing sync position."""
    if value is None:
        return EMPTY_CURSOR
    if isinstance(value, str):
        return GoogleSyncCursor(
            committed_cursor=value,
            continuation_page_token=None,
            continuation_base_cursor=None,
            sync_in_progress=False,
            last_complete_sync_at=None,
        )
    last_complete = value.get("last_complete_sync_at")
    return GoogleSyncCursor(
        committed_cursor=value.get("committed_cursor"),
        continuation_page_token=value.get("continuation_page_token"),
        continuation_base_cursor=value.get("continuation_base_cursor"),
        sync_in_progress=bool(value.get("sync_in_progress", False)),
        last_complete_sync_at=datetime.fromisoformat(last_complete) if last_complete else None,
    )


def cursor_to_stored(cursor: GoogleSyncCursor) -> dict[str, Any]:
    document = asdict(cursor)
    document["last_complete_sync_at"] = (
        cursor.last_complete_sync_at.isoformat() if cursor.last_complete_sync_at else None
    )
    return document


def encode_window(since: datetime, until: datetime) -> str:
    """The exact query bounds a windowed (non-incremental) page request used
    — persisted as `continuation_base_cursor` so a resumed page request
    reuses the identical `since`/`until` Gmail's `pageToken` was issued
    against, rather than a freshly-shifted rolling window that would make
    the token's continued validity undefined."""
    return json.dumps([since.isoformat(), until.isoformat()])


def decode_window(value: str) -> tuple[datetime, datetime]:
    since_raw, until_raw = json.loads(value)
    return datetime.fromisoformat(since_raw), datetime.fromisoformat(until_raw)


__all__ = [
    "EMPTY_CURSOR",
    "GoogleSyncCursor",
    "cursor_from_stored",
    "cursor_to_stored",
    "decode_window",
    "encode_window",
]
