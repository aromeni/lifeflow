"""Default-deny operator gates for starting or completing Google OAuth.

Stage 11A Phase 4C deliberately separates *configuration present* from
*authorised to initiate*. Loading a client ID/secret is not permission to
redirect a browser to Google or exchange a callback code.

Stage 11A Phase 6A: OIDC sign-in and connector consent originally shared one
gate (`require_google_oauth_initiation`, one flag). A real incident during
Phase 6 showed that was unsafe — enabling it to authorise a connector
reconnection necessarily also armed OIDC sign-in, since the two flows had no
way to be authorised independently. Two separate gates now exist, one per
flow, each backed by its own flag; enabling either one is never sufficient
to enable the other.
"""

from fastapi import HTTPException, Request

GOOGLE_OIDC_SIGNIN_BLOCKED_DETAIL = "Google sign-in is configured, but is not currently authorised."
GOOGLE_CONNECTOR_OAUTH_BLOCKED_DETAIL = (
    "Google account connection is configured, but is not currently authorised."
)


def require_google_oidc_signin(request: Request) -> None:
    """Fail closed before state creation, redirects, or code exchange for
    the OIDC sign-in flow specifically. Never checks, and is never satisfied
    by, `google_connector_oauth_enabled`."""
    settings = request.app.state.settings
    if not settings.google_oauth_enabled or request.app.state.google_oauth_client is None:
        raise HTTPException(status_code=404, detail="Not Found")
    if not settings.google_oidc_signin_enabled:
        raise HTTPException(status_code=409, detail=GOOGLE_OIDC_SIGNIN_BLOCKED_DETAIL)


def require_google_connector_oauth(request: Request) -> None:
    """Fail closed before state creation, redirects, or code exchange for
    the connector-consent flow specifically. Never checks, and is never
    satisfied by, `google_oidc_signin_enabled`."""
    settings = request.app.state.settings
    if not settings.google_oauth_enabled or request.app.state.google_oauth_client is None:
        raise HTTPException(status_code=404, detail="Not Found")
    if not settings.google_connector_oauth_enabled:
        raise HTTPException(status_code=409, detail=GOOGLE_CONNECTOR_OAUTH_BLOCKED_DETAIL)


__all__ = [
    "GOOGLE_CONNECTOR_OAUTH_BLOCKED_DETAIL",
    "GOOGLE_OIDC_SIGNIN_BLOCKED_DETAIL",
    "require_google_connector_oauth",
    "require_google_oidc_signin",
]
