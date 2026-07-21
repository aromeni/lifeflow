"""OAuth flow state: `state` + PKCE persisted in the existing signed session
cookie (threat model T11, ADR 0003 D10). Single-use, short-TTL, and — for the
connector-consent flow — bound to the LifeFlow session that started it, so a
leaked or guessed `state` from one flow is meaningless in the other.
"""

import time
from dataclasses import dataclass
from typing import Any

from starlette.requests import Request

from lifeflow_api.google.oauth import PkcePair, generate_nonce, generate_pkce_pair, generate_state

STATE_TTL_SECONDS = 600
_SESSION_KEY = "google_oauth_pending"


class OAuthStateError(Exception):
    """The state/PKCE/purpose/binding could not be validated. Never carries
    the state or verifier value itself."""


@dataclass(frozen=True)
class ConsumedOAuthFlow:
    code_verifier: str
    # Only set (and only checked) for flows that requested one — the
    # connector-consent flow never exchanges an ID token, so it has no
    # nonce to verify (independent-review non-blocking finding).
    nonce: str | None


def begin_oauth_flow(
    request: Request,
    *,
    purpose: str,
    bind_user_id: str | None = None,
    include_nonce: bool = False,
) -> tuple[str, PkcePair, str | None]:
    """Generate and persist a new pending flow; return (state, pkce, nonce)
    for the caller to build the authorization-URL redirect. `nonce` is only
    generated when `include_nonce=True` (the OIDC sign-in flow) — it binds
    the eventual ID token to this specific attempt (ADR 0003, independent-
    review non-blocking finding)."""
    state = generate_state()
    pkce = generate_pkce_pair()
    nonce = generate_nonce() if include_nonce else None
    request.session[_SESSION_KEY] = {
        "purpose": purpose,
        "state": state,
        "code_verifier": pkce.verifier,
        "nonce": nonce,
        "created_at": time.time(),
        "user_id": bind_user_id,
    }
    return state, pkce, nonce


def consume_oauth_flow(request: Request, *, purpose: str, state: str) -> ConsumedOAuthFlow:
    """Validate the callback's `state` against the pending flow and clear it
    — single-use regardless of outcome."""
    pending: dict[str, Any] | None = request.session.pop(_SESSION_KEY, None)
    if pending is None:
        raise OAuthStateError("No pending OAuth flow for this session.")
    if pending.get("purpose") != purpose:
        raise OAuthStateError("OAuth flow purpose mismatch.")
    if pending.get("state") != state:
        raise OAuthStateError("OAuth state mismatch.")
    if time.time() - float(pending.get("created_at", 0)) > STATE_TTL_SECONDS:
        raise OAuthStateError("OAuth flow expired.")
    bound_user_id = pending.get("user_id")
    if bound_user_id is not None and bound_user_id != request.session.get("user_id"):
        raise OAuthStateError("OAuth flow does not match the current session.")
    verifier = pending.get("code_verifier")
    if not isinstance(verifier, str):
        raise OAuthStateError("OAuth flow is missing its PKCE verifier.")
    nonce = pending.get("nonce")
    return ConsumedOAuthFlow(
        code_verifier=verifier, nonce=nonce if isinstance(nonce, str) else None
    )


__all__ = ["ConsumedOAuthFlow", "OAuthStateError", "begin_oauth_flow", "consume_oauth_flow"]
