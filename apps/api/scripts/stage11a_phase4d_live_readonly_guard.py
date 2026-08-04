"""Stage 11A Phase 4D — the live read-only transport guard.

This is the one safeguard in this phase whose entire job is to sit between
LifeFlow's real Google clients and the real Google hosts during the single
authorised live connection, and refuse everything the governing task did not
explicitly approve — before a single byte reaches Google. Unlike Phase 4B's
`lifeflow_api.testing.no_live_network` (which blocks ALL non-loopback traffic
for fake-provider rehearsals), this guard's job is the opposite: it exists
only for the one session where reaching real Google hosts is authorised, and
narrows that from "the whole Gmail/Calendar API surface" down to the exact
six method+host+path combinations this phase approved.

Design notes:
  * An exact allowlist of (method, host, path) tuples, not a blocklist of
    dangerous ones — anything not named is refused, including endpoints
    that do not exist yet.
  * A per-key call budget, defaulting to the governing task's §8 numbers.
    Exceeding a budgeted call's limit is refused before transmission, not
    merely counted afterwards.
  * Consults only the outgoing request's own method/host/path — never a
    setting, header, or environment variable — so `GOOGLE_API_ORIGIN_OVERRIDE`
    or any other override cannot silently redirect traffic through this
    guard to a different host and have it pass.
  * A followed redirect is a new request through the same transport, so a
    redirect to an unapproved host is refused exactly like a direct request
    would be.
  * Never logs a query string, header, or response body — violation and
    budget errors report only method/host/path, and `content_free_metrics()`
    reports only call counts keyed by method+path.
"""

from __future__ import annotations

import httpx

TOKEN_HOST = "oauth2.googleapis.com"  # noqa: S105 -- a hostname, not a secret
GMAIL_HOST = "gmail.googleapis.com"
CALENDAR_HOST = "www.googleapis.com"

# The exact six operations this phase approved. Order matches the governing
# task's §7/§8 enumeration.
TOKEN_EXCHANGE = ("POST", TOKEN_HOST, "/token")
TOKEN_REVOKE = ("POST", TOKEN_HOST, "/revoke")
GMAIL_GET_PROFILE = ("GET", GMAIL_HOST, "/gmail/v1/users/me/profile")
GMAIL_MESSAGES_LIST = ("GET", GMAIL_HOST, "/gmail/v1/users/me/messages")
CALENDAR_GET_PRIMARY = ("GET", CALENDAR_HOST, "/calendar/v3/calendars/primary")
CALENDAR_EVENTS_LIST = ("GET", CALENDAR_HOST, "/calendar/v3/calendars/primary/events")

ALLOWED_OPERATIONS = frozenset(
    {
        TOKEN_EXCHANGE,
        TOKEN_REVOKE,
        GMAIL_GET_PROFILE,
        GMAIL_MESSAGES_LIST,
        CALENDAR_GET_PRIMARY,
        CALENDAR_EVENTS_LIST,
    }
)

# The governing task's §8 live call budget. A key absent from this mapping
# is still blocked entirely by `ALLOWED_OPERATIONS` — this only bounds the
# *count* of the six operations that are allowed at all.
DEFAULT_BUDGET: dict[tuple[str, str, str], int] = {
    TOKEN_EXCHANGE: 1,
    TOKEN_REVOKE: 1,
    GMAIL_GET_PROFILE: 1,
    GMAIL_MESSAGES_LIST: 1,
    CALENDAR_GET_PRIMARY: 1,
    CALENDAR_EVENTS_LIST: 1,
}


class LiveGuardViolationError(RuntimeError):
    """Raised for any request outside the exact approved operation set."""


class LiveGuardBudgetExceededError(RuntimeError):
    """Raised when an approved operation's call budget is already spent."""


class LiveReadOnlyGuardTransport(httpx.AsyncBaseTransport):
    """Wraps the real transport; allows only `ALLOWED_OPERATIONS`, each
    bounded by `budget`. Every refusal happens before `handle_async_request`
    ever reaches the wrapped transport — no request this guard refuses is
    ever sent."""

    def __init__(
        self,
        wrapped: httpx.AsyncBaseTransport,
        *,
        budget: dict[tuple[str, str, str], int] | None = None,
    ) -> None:
        self._wrapped = wrapped
        self._budget = dict(DEFAULT_BUDGET if budget is None else budget)
        self._counts: dict[tuple[str, str, str], int] = dict.fromkeys(self._budget, 0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.host, request.url.path)
        if key not in ALLOWED_OPERATIONS:
            raise LiveGuardViolationError(
                f"refusing unapproved operation: {request.method} "
                f"{request.url.host}{request.url.path}"
            )
        limit = self._budget.get(key)
        if limit is not None:
            if self._counts[key] >= limit:
                raise LiveGuardBudgetExceededError(
                    f"call budget exhausted for {request.method} {request.url.host}"
                    f"{request.url.path} (limit {limit})"
                )
            self._counts[key] += 1
        return await self._wrapped.handle_async_request(request)

    async def aclose(self) -> None:
        await self._wrapped.aclose()

    def content_free_metrics(self) -> dict[str, int]:
        """Call counts keyed by `"METHOD /path"` only — no host, no query
        string, no header, no response content."""
        return {f"{method} {path}": count for (method, _host, path), count in self._counts.items()}


__all__ = [
    "ALLOWED_OPERATIONS",
    "CALENDAR_EVENTS_LIST",
    "CALENDAR_GET_PRIMARY",
    "DEFAULT_BUDGET",
    "GMAIL_GET_PROFILE",
    "GMAIL_MESSAGES_LIST",
    "TOKEN_EXCHANGE",
    "TOKEN_REVOKE",
    "LiveGuardBudgetExceededError",
    "LiveGuardViolationError",
    "LiveReadOnlyGuardTransport",
]
