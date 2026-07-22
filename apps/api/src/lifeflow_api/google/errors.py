"""Shared error taxonomy for Google API calls.

Every Google client classifies a failed call into exactly one of these, so
callers (ingestion connectors, executors) never have to interpret raw HTTP
status codes themselves. Messages here must never carry token material or
raw request/response bodies (threat model T6).
"""


class GoogleApiError(Exception):
    """Base for all Google API/OAuth failures."""


class GoogleAuthError(GoogleApiError):
    """The access token was rejected (expired/invalid) — caller should
    refresh and retry once, not treat this as final."""


class GoogleClientError(GoogleApiError):
    """A clear, final rejection (bad request, permission denied, not found)
    unrelated to token expiry. Maps to ExecutionOutcome.failed."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class GoogleTransientError(GoogleApiError):
    """Timeout, connection error, 429, or 5xx — the call's true outcome is
    unknown. Maps to ExecutionOutcome.uncertain, never to failed."""


class GoogleHistoryExpiredError(GoogleApiError):
    """Gmail's historyId is too old (HTTP 404 on history.list) — the
    connector must fall back to a full bounded resync."""


class GoogleSyncTokenExpiredError(GoogleApiError):
    """Calendar's syncToken is invalid (HTTP 410 on events.list) — the
    connector must fall back to a full bounded resync."""


class GoogleOAuthError(GoogleApiError):
    """Base for OAuth-flow failures (authorization/token/revoke)."""


class InvalidGrantError(GoogleOAuthError):
    """Refresh token rejected by Google (revoked, expired, or invalid) —
    the account must move to AccountStatus.revoked and the user must
    re-authorise (AC-J2.3)."""


class IdTokenVerificationError(GoogleOAuthError):
    """ID token failed signature, issuer, audience, expiry, or the
    email-verified check."""
