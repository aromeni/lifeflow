"""Narrow Gmail transport client (ADR 0003 D13).

Exactly seven methods exist: six reads (five used by ingestion/execution
verification, one — `get_profile_email`, Stage 11A Phase 4D — used only for
one-time live identity verification) and exactly one write — `create_draft`,
which POSTs to exactly one fixed path. There is no generic `request()`
method. `gmail.compose` is a broad scope that *permits* sending (threat
model T22) — this client is the enforcement point that never constructs a
request to `/messages/send` or `/drafts/send`, checked directly by the
allow-list assertion below and proven by transport-level tests that inspect
every HTTP call actually made.
"""

import base64
import email
import email.policy
import email.utils
from dataclasses import dataclass
from typing import Any

import httpx

from lifeflow_api.google.errors import (
    GoogleApiError,
    GoogleAuthError,
    GoogleClientError,
    GoogleHistoryExpiredError,
    GoogleTransientError,
)
from lifeflow_api.metrics import observe_provider_call

_BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"
# The complete set of paths this client may ever request. Enforced before
# every dispatch — an unexpected path raises rather than sends.
_ALLOWED_READ_PATHS = {"messages", "messages/{id}", "history", "profile", "drafts/{id}"}
_ALLOWED_WRITE_PATHS = {"drafts"}


@dataclass(frozen=True)
class GmailMessageSummary:
    id: str
    thread_id: str


@dataclass(frozen=True)
class GmailMessage:
    id: str
    thread_id: str
    headers: dict[str, str]
    snippet: str
    internal_date_ms: int
    label_ids: tuple[str, ...]


@dataclass(frozen=True)
class GmailHistoryPage:
    message_ids: tuple[str, ...]
    next_page_token: str | None
    history_id: str


@dataclass(frozen=True)
class GmailDraftResult:
    """`drafts.create`'s own response — identifiers only. Gmail does not
    guarantee a fully parsed `message.payload` on this response, so it is
    never trusted for verification content (see `GmailDraftContent`/
    `get_draft`, Stage 7 focused remediation)."""

    draft_id: str
    message_id: str
    thread_id: str


@dataclass(frozen=True)
class GmailDraftContent:
    """The created draft's actual stored content, independently re-fetched
    via `get_draft` and parsed from its raw RFC822 MIME — this, not
    `drafts.create`'s response, is what verification compares against the
    approved payload (Stage 7 focused remediation: a real sandbox account
    surfaced that the create response's `payload` is frequently absent or
    minimal, producing false-negative `uncertain` outcomes for drafts that
    Gmail had, in fact, created correctly)."""

    draft_id: str
    message_id: str
    thread_id: str
    to: tuple[str, ...]
    subject: str
    body: str


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def _get(http: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
    """Every read goes through this so a raw transport failure — no response
    ever received, e.g. a timeout or a dropped connection — is classified as
    `GoogleTransientError` (→ `uncertain`) immediately, the same way a 5xx
    response already is (independent-review blocker #5). `_raise_for_error`
    alone cannot catch this: it only ever runs once a response exists."""
    try:
        return await http.get(url, **kwargs)
    except httpx.HTTPError as exc:
        raise GoogleTransientError(
            f"Gmail API request failed before a response was received ({type(exc).__name__})."
        ) from exc


async def _post(http: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
    try:
        return await http.post(url, **kwargs)
    except httpx.HTTPError as exc:
        raise GoogleTransientError(
            f"Gmail API request failed before a response was received ({type(exc).__name__})."
        ) from exc


def _raise_for_error(response: httpx.Response) -> None:
    if response.status_code == 200:
        return
    if response.status_code in (401, 403):
        raise GoogleAuthError(f"Gmail API rejected the access token (HTTP {response.status_code}).")
    if response.status_code in (429, 500, 502, 503, 504):
        raise GoogleTransientError(f"Gmail API returned HTTP {response.status_code}.")
    raise GoogleClientError(
        f"Gmail API returned HTTP {response.status_code}.", status_code=response.status_code
    )


class GmailDraftClient:
    """Reads bounded/cursor-aware message metadata; writes exactly one draft
    per call. Takes an injected `httpx.AsyncClient` so tests substitute
    `httpx.MockTransport` — no live network call is possible in tests."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        write_timeout: httpx.Timeout | None = None,
        base_url: str = _BASE_URL,
    ) -> None:
        self._http = http_client
        # Stage 9 Delivery Phase 5 (§20): configurable so a local Playwright
        # run can point this client at an in-process fake Gmail server
        # instead of the real host — never used outside
        # `e2e_test_controls_enabled` (see `main.py`); defaults to the real
        # Gmail API and is never overridden by ordinary configuration.
        self._base_url = base_url
        # Stage 9 Delivery Phase 5: the one write this client performs gets a
        # longer, separately-configured read budget than the client's default
        # (`timeouts.google_httpx_write_timeout`) — a local timeout here must
        # never be mistaken for "Google didn't receive the request" (see
        # `timeouts.py` module docstring). `None` (the default, used by every
        # existing test) keeps the client's own default timeout.
        self._write_timeout = write_timeout

    async def list_messages(
        self, *, access_token: str, query: str, page_token: str | None, max_results: int
    ) -> tuple[tuple[GmailMessageSummary, ...], str | None]:
        assert "messages" in _ALLOWED_READ_PATHS  # noqa: S101 -- allow-list self-check
        params: dict[str, Any] = {"q": query, "maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token
        async with observe_provider_call("gmail", "list_messages"):
            response = await _get(
                self._http,
                f"{self._base_url}/messages",
                params=params,
                headers=_headers(access_token),
            )
            _raise_for_error(response)
        body = response.json()
        summaries = tuple(
            GmailMessageSummary(id=item["id"], thread_id=item["threadId"])
            for item in body.get("messages", [])
        )
        return summaries, body.get("nextPageToken")

    async def get_message(self, *, access_token: str, message_id: str) -> GmailMessage:
        assert "messages/{id}" in _ALLOWED_READ_PATHS  # noqa: S101
        async with observe_provider_call("gmail", "get_message"):
            response = await _get(
                self._http,
                f"{self._base_url}/messages/{message_id}",
                params={
                    "format": "metadata",
                    # List-Unsubscribe (RFC 2369/8058) is fetched solely as a
                    # bulk-mail marker (ADR 0003 D42) — its value is a fact
                    # about the message, and metadata-only minimisation is
                    # unchanged.
                    "metadataHeaders": ["From", "To", "Subject", "Date", "List-Unsubscribe"],
                },
                headers=_headers(access_token),
            )
            _raise_for_error(response)
        body = response.json()
        headers = {
            item["name"]: item["value"] for item in body.get("payload", {}).get("headers", [])
        }
        return GmailMessage(
            id=body["id"],
            thread_id=body["threadId"],
            headers=headers,
            snippet=body.get("snippet", ""),
            internal_date_ms=int(body.get("internalDate", "0")),
            label_ids=tuple(body.get("labelIds", ())),
        )

    async def list_history(
        self, *, access_token: str, start_history_id: str, page_token: str | None
    ) -> GmailHistoryPage:
        """Raises GoogleHistoryExpiredError on HTTP 404 (stale historyId) —
        the connector must fall back to a full bounded resync (ADR 0003 D21)."""
        assert "history" in _ALLOWED_READ_PATHS  # noqa: S101
        params: dict[str, Any] = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
        }
        if page_token:
            params["pageToken"] = page_token
        async with observe_provider_call("gmail", "list_history"):
            response = await _get(
                self._http,
                f"{self._base_url}/history",
                params=params,
                headers=_headers(access_token),
            )
            if response.status_code == 404:
                raise GoogleHistoryExpiredError("Gmail historyId has expired.")
            _raise_for_error(response)
        body = response.json()
        message_ids = tuple(
            added["message"]["id"]
            for record in body.get("history", [])
            for added in record.get("messagesAdded", [])
        )
        return GmailHistoryPage(
            message_ids=message_ids,
            next_page_token=body.get("nextPageToken"),
            history_id=body.get("historyId", start_history_id),
        )

    async def get_current_history_id(self, *, access_token: str) -> str:
        """The mailbox's current historyId — the baseline cursor a full
        resync establishes for the next incremental sync."""
        assert "profile" in _ALLOWED_READ_PATHS  # noqa: S101
        async with observe_provider_call("gmail", "get_current_history_id"):
            response = await _get(
                self._http, f"{self._base_url}/profile", headers=_headers(access_token)
            )
            _raise_for_error(response)
        return str(response.json()["historyId"])

    async def get_profile_email(self, *, access_token: str) -> str:
        """Stage 11A Phase 4D: the same `users.getProfile` endpoint
        `get_current_history_id` already calls, reading `emailAddress`
        instead of `historyId` — used only to verify the connected
        account's identity during the one-time live read-only smoke
        sequence. Callers must never print or persist the returned value
        (see `docs/evaluation/stage-11/owner-validation/phase-4d/
        official-requirements-recheck.md`)."""
        assert "profile" in _ALLOWED_READ_PATHS  # noqa: S101
        async with observe_provider_call("gmail", "get_profile_email"):
            response = await _get(
                self._http, f"{self._base_url}/profile", headers=_headers(access_token)
            )
            _raise_for_error(response)
        return str(response.json()["emailAddress"])

    async def create_draft(
        self,
        *,
        access_token: str,
        to: list[str],
        subject: str,
        body: str,
        thread_id: str | None,
    ) -> GmailDraftResult:
        """The one write this client can perform. Builds exactly one fixed
        request to `POST /gmail/v1/users/me/drafts` — never `.../send`.
        Returns only the identifiers this response actually guarantees;
        call `get_draft()` afterwards to verify content."""
        if "drafts" not in _ALLOWED_WRITE_PATHS:  # pragma: no cover -- defensive, unreachable
            raise GoogleApiError("Draft creation path is not allow-listed.")
        raw_message = _build_rfc822_message(to=to, subject=subject, body=body)
        payload: dict[str, Any] = {"message": {"raw": raw_message}}
        if thread_id:
            payload["message"]["threadId"] = thread_id
        extra: dict[str, Any] = (
            {"timeout": self._write_timeout} if self._write_timeout is not None else {}
        )
        async with observe_provider_call("gmail", "create_draft"):
            response = await _post(
                self._http,
                f"{self._base_url}/drafts",
                json=payload,
                headers=_headers(access_token),
                **extra,
            )
            _raise_for_error(response)
        result = response.json()
        message = result.get("message", {})
        return GmailDraftResult(
            draft_id=result["id"],
            message_id=message.get("id", ""),
            thread_id=message.get("threadId", ""),
        )

    async def get_draft(self, *, access_token: str, draft_id: str) -> GmailDraftContent:
        """Independently re-fetches the just-created draft's raw RFC822
        content (`format=raw`) so verification compares against what Gmail
        actually stored, not `create_draft`'s own (frequently minimal)
        response (Stage 7 focused remediation)."""
        assert "drafts/{id}" in _ALLOWED_READ_PATHS  # noqa: S101
        async with observe_provider_call("gmail", "get_draft"):
            response = await _get(
                self._http,
                f"{self._base_url}/drafts/{draft_id}",
                params={"format": "raw"},
                headers=_headers(access_token),
            )
            _raise_for_error(response)
        body = response.json()
        message = body.get("message", {})
        parsed = _parse_raw_message(message.get("raw", ""))
        return GmailDraftContent(
            draft_id=body["id"],
            message_id=message.get("id", ""),
            thread_id=message.get("threadId", ""),
            to=parsed.to,
            subject=parsed.subject,
            body=parsed.body,
        )


@dataclass(frozen=True)
class _ParsedRawMessage:
    to: tuple[str, ...]
    subject: str
    body: str


def _parse_raw_message(raw: str) -> _ParsedRawMessage:
    """Decodes Gmail's base64url RFC822 raw message through the standard
    library's MIME parser rather than hand-rolled parsing (Stage 7 focused
    remediation). `email.policy.default` gives case-insensitive header
    lookup, transparently decodes MIME-encoded-word Unicode subjects, and
    normalises CRLF/LF; `email.utils.getaddresses` normalises recipient
    formatting (display names, surrounding whitespace, comma-separated
    lists) down to bare addresses."""
    if not raw:
        return _ParsedRawMessage(to=(), subject="", body="")
    padded = raw + "=" * (-len(raw) % 4)
    raw_bytes = base64.urlsafe_b64decode(padded)
    parsed = email.message_from_bytes(raw_bytes, policy=email.policy.default)
    to = tuple(
        address.strip().lower()
        for _, address in email.utils.getaddresses([str(parsed.get("To", ""))])
        if address.strip()
    )
    subject = str(parsed.get("Subject", "")).strip()
    body_part = parsed.get_body(preferencelist=("plain",))
    content = body_part.get_content() if body_part is not None else ""
    body = content.replace("\r\n", "\n").strip()
    return _ParsedRawMessage(to=to, subject=subject, body=body)


def _build_rfc822_message(*, to: list[str], subject: str, body: str) -> str:
    lines = [
        f"To: {', '.join(to)}",
        f"Subject: {subject}",
        "Content-Type: text/plain; charset=UTF-8",
        "",
        body,
    ]
    raw = "\r\n".join(lines).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


__all__ = [
    "GmailDraftClient",
    "GmailDraftContent",
    "GmailDraftResult",
    "GmailHistoryPage",
    "GmailMessage",
    "GmailMessageSummary",
]
