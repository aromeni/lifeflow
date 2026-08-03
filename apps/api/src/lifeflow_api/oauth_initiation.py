"""Default-deny operator gate for starting or completing Google OAuth.

Stage 11A Phase 4C deliberately separates *configuration present* from
*authorised to initiate*. Loading a client ID/secret is not permission to
redirect a browser to Google or exchange a callback code. Both OIDC sign-in
and connector consent call this shared guard so their behaviour cannot drift.
"""

from fastapi import HTTPException, Request

OAUTH_INITIATION_BLOCKED_DETAIL = (
    "Google OAuth is configured, but initiation remains blocked pending "
    "explicit owner authorisation."
)


def require_google_oauth_initiation(request: Request) -> None:
    """Fail closed before state creation, redirects, or code exchange.

    An unconfigured integration remains indistinguishable from an absent
    route (the established Stage 7 behaviour). A configured-but-not-
    authorised integration returns bounded operator guidance without a
    provider URL, client identifier, secret, or callback value.
    """

    settings = request.app.state.settings
    if not settings.google_oauth_enabled or request.app.state.google_oauth_client is None:
        raise HTTPException(status_code=404, detail="Not Found")
    if not settings.google_oauth_initiation_enabled:
        raise HTTPException(status_code=409, detail=OAUTH_INITIATION_BLOCKED_DETAIL)


__all__ = ["OAUTH_INITIATION_BLOCKED_DETAIL", "require_google_oauth_initiation"]
