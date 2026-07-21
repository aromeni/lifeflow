"""The exact Google connector scopes (ADR 0003 D11) — one constant, one
place. Used to build the connector-consent authorization URL and to check
what was actually granted in `action_policy.py`. Never the sign-in scope
(`openid email profile`, defined alongside the OIDC routes in `auth.py`) —
the two are deliberately separate (D10)."""

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"

CONNECTOR_SCOPES = (
    GMAIL_READONLY_SCOPE,
    GMAIL_COMPOSE_SCOPE,
    CALENDAR_READONLY_SCOPE,
    CALENDAR_EVENTS_SCOPE,
)
CONNECTOR_SCOPE_STRING = " ".join(CONNECTOR_SCOPES)

__all__ = [
    "CALENDAR_EVENTS_SCOPE",
    "CALENDAR_READONLY_SCOPE",
    "CONNECTOR_SCOPES",
    "CONNECTOR_SCOPE_STRING",
    "GMAIL_COMPOSE_SCOPE",
    "GMAIL_READONLY_SCOPE",
]
