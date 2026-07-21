"""Google OAuth: two independent flows (ADR 0003 D10), PKCE + state helpers,
authorization-code exchange, refresh, revoke, and ID-token verification.

ID-token signature/claim verification goes through the maintained
`google-auth` library (`google.oauth2.id_token.verify_oauth2_token`) — this
module never implements JWT cryptography itself (ADR 0003 D14). The only
code written here is a thin transport adapter so that library can fetch
Google's certs over `httpx` instead of pulling in the `requests` package as
an extra dependency (ADR 0003 D24).
"""

import base64
import hashlib
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from google.auth.transport import Request as GoogleAuthRequest
from google.auth.transport import Response as GoogleAuthResponse
from google.oauth2 import id_token as google_id_token
from starlette.concurrency import run_in_threadpool

from lifeflow_api.google.errors import (
    GoogleAuthError,
    GoogleClientError,
    GoogleTransientError,
    IdTokenVerificationError,
    InvalidGrantError,
)

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105 -- endpoint URL, not a secret
REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"


@dataclass(frozen=True)
class PkcePair:
    verifier: str
    challenge: str


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def generate_nonce() -> str:
    """OIDC `nonce` (independent-review non-blocking finding): binds a
    specific ID token to a specific sign-in attempt, so a token intercepted
    or replayed outside that attempt's session is rejected even if its
    signature, issuer, audience and expiry all check out — `state`/PKCE
    alone don't cover this, since they protect the authorization-code
    exchange, not the ID token's own claims."""
    return secrets.token_urlsafe(32)


def generate_pkce_pair() -> PkcePair:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return PkcePair(verifier=verifier, challenge=challenge)


def build_authorization_url(
    *,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
    code_challenge: str,
    access_type: str | None = None,
    prompt: str | None = None,
    nonce: str | None = None,
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if access_type:
        params["access_type"] = access_type
    if prompt:
        params["prompt"] = prompt
    if nonce:
        params["nonce"] = nonce
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


@dataclass(frozen=True)
class GoogleTokenResponse:
    access_token: str
    refresh_token: str | None  # None means "unchanged" — never treat as "clear" (D18)
    expires_in: int
    scope: str
    id_token: str | None


# OAuth error codes (RFC 6749 §5.2) that mean "the provider itself is having
# trouble right now" — the call's true outcome is unknown, same as a
# transport timeout or a 5xx (independent-review blocker #2).
_TRANSIENT_OAUTH_ERROR_CODES = {"server_error", "temporarily_unavailable"}
# Codes that mean this deployment's own OAuth client configuration was
# rejected — a definite, final failure, never "uncertain" merely because the
# response was non-200.
_AUTH_REJECTED_OAUTH_ERROR_CODES = {"invalid_client", "unauthorized_client"}


def _classify_token_error(response: httpx.Response) -> Exception:
    """Classify a non-200 token-endpoint response into exactly one typed
    error (independent-review blocker #2) — never a generic
    `GoogleOAuthError` that callers have no way to react to safely. Never
    includes Google's raw error description or the token endpoint URL
    (threat model T6)."""
    code = _error_code(response)
    is_transient_status = response.status_code == 429 or response.status_code >= 500
    if is_transient_status or code in _TRANSIENT_OAUTH_ERROR_CODES:
        return GoogleTransientError(
            f"Google token endpoint returned a transient error (HTTP {response.status_code})."
        )
    if code == "invalid_grant":
        return InvalidGrantError("Google rejected the refresh token.")
    if code in _AUTH_REJECTED_OAUTH_ERROR_CODES:
        return GoogleAuthError(f"Google rejected the OAuth client (HTTP {response.status_code}).")
    # invalid_request, unsupported_grant_type, invalid_scope, and any other
    # definitive 4xx not covered above — a clear client/configuration
    # failure, mapped like the Gmail/Calendar clients' own 4xx handling.
    return GoogleClientError(
        f"Google token endpoint rejected the request (HTTP {response.status_code}).",
        status_code=response.status_code,
    )


def _parse_token_response(response: httpx.Response) -> GoogleTokenResponse:
    if response.status_code != 200:
        raise _classify_token_error(response)
    body = response.json()
    return GoogleTokenResponse(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token"),
        expires_in=int(body["expires_in"]),
        scope=body.get("scope", ""),
        id_token=body.get("id_token"),
    )


class GoogleOAuthClient:
    """Narrow wrapper around Google's token/revoke endpoints. Every method
    builds exactly one fixed request; there is no generic request passthrough
    (ADR 0003 D13's narrow-client rule applied to the OAuth transport too)."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client

    async def exchange_code(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code: str,
        code_verifier: str,
    ) -> GoogleTokenResponse:
        response = await self._post(
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
            }
        )
        return _parse_token_response(response)

    async def refresh_access_token(
        self, *, client_id: str, client_secret: str, refresh_token: str
    ) -> GoogleTokenResponse:
        response = await self._post(
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        )
        return _parse_token_response(response)

    async def _post(self, *, data: dict[str, str]) -> httpx.Response:
        """A raw transport failure (timeout, dropped connection — no
        response ever received) is classified `GoogleTransientError`
        immediately, same as the Gmail/Calendar clients (independent-review
        blocker #5) — callers refreshing a token mid-execution must see an
        `uncertain` outcome, never an unclassified crash."""
        try:
            return await self._http.post(TOKEN_ENDPOINT, data=data)
        except httpx.HTTPError as exc:
            raise GoogleTransientError(
                f"Google token endpoint request failed before a response was received "
                f"({type(exc).__name__})."
            ) from exc

    async def revoke_token(self, *, token: str) -> None:
        """Best-effort: local disconnect must never be blocked by Google
        being unreachable (D20)."""
        try:
            await self._http.post(REVOKE_ENDPOINT, data={"token": token})
        except httpx.HTTPError:
            pass


def _error_code(response: httpx.Response) -> str | None:
    try:
        body: dict[str, Any] = response.json()
    except ValueError:
        return None
    error = body.get("error")
    return error if isinstance(error, str) else None


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    email_verified: bool


class _HttpxAuthResponse(GoogleAuthResponse):
    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    @property
    def status(self) -> int:
        return self._response.status_code

    @property
    def headers(self) -> Mapping[str, str]:
        return self._response.headers

    @property
    def data(self) -> bytes:
        return self._response.content


class _HttpxAuthRequest(GoogleAuthRequest):
    """Adapts google-auth's synchronous transport interface to httpx, so
    JWKS fetching for ID-token verification never needs the `requests`
    package as an extra dependency (ADR 0003 D24)."""

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=10.0)

    def __call__(
        self,
        url: str,
        method: str = "GET",
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> _HttpxAuthResponse:
        response = self._client.request(
            method, url, content=body, headers=headers, timeout=timeout or 10.0
        )
        return _HttpxAuthResponse(response)


IdTokenVerifier = Callable[[str, str], dict[str, Any]]


#  google-auth's `verify_oauth2_token` defaults to zero tolerance for clock
# skew between this machine and Google's token-issuing server. Real-world
# clocks (even NTP-synced ones) routinely drift by a few seconds, which is
# enough to fail verification with "Token used too early" despite the token
# being entirely valid. 10 seconds matches the tolerance Google's own client
# libraries commonly use elsewhere and does not meaningfully weaken
# expiry/issuance checking.
_CLOCK_SKEW_TOLERANCE_SECONDS = 10


def _default_verifier(token: str, client_id: str) -> dict[str, Any]:
    # google-auth ships no inline types for this function.
    result = google_id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
        token,
        _HttpxAuthRequest(),
        audience=client_id,
        clock_skew_in_seconds=_CLOCK_SKEW_TOLERANCE_SECONDS,
    )
    return dict(result)


async def verify_id_token(
    token: str,
    *,
    client_id: str,
    expected_nonce: str | None = None,
    verifier: IdTokenVerifier | None = None,
) -> GoogleIdentity:
    """Verify a Google ID token. Signature (JWKS), issuer, audience, and
    expiry are all handled by `google-auth`'s maintained
    `verify_oauth2_token` — `verify_oauth2_token` does not check `nonce`, so
    this function adds that check itself alongside `email_verified` (ADR
    0003 D15), plus the injectable `verifier` seam tests use to avoid real
    network/cryptographic verification.
    """
    verify = verifier or _default_verifier
    try:
        claims = await run_in_threadpool(verify, token, client_id)
    except Exception as exc:
        raise IdTokenVerificationError("Google ID token verification failed.") from exc
    if not claims.get("email_verified"):
        raise IdTokenVerificationError("Google account email is not verified.")
    if expected_nonce is not None and claims.get("nonce") != expected_nonce:
        raise IdTokenVerificationError("Google ID token nonce does not match this sign-in attempt.")
    subject = claims.get("sub")
    email = claims.get("email")
    if not isinstance(subject, str) or not isinstance(email, str):
        raise IdTokenVerificationError("Google ID token is missing required claims.")
    return GoogleIdentity(subject=subject, email=email, email_verified=True)


__all__ = [
    "AUTHORIZATION_ENDPOINT",
    "REVOKE_ENDPOINT",
    "TOKEN_ENDPOINT",
    "GoogleIdentity",
    "GoogleOAuthClient",
    "GoogleTokenResponse",
    "PkcePair",
    "build_authorization_url",
    "generate_nonce",
    "generate_pkce_pair",
    "generate_state",
    "verify_id_token",
]
