"""Application factory.

Run locally with:
    uv run uvicorn --app-dir src lifeflow_api.main:app --reload --port 8010 --forwarded-allow-ips=""

`--forwarded-allow-ips=""` is required: uvicorn's own default trusts
X-Forwarded-For from any loopback connection, which would silently override
this app's own `TRUSTED_PROXY_CIDRS` rate-limiting trust boundary
(ADR 0005 D64/D81) — with the flag unset, any local process could spoof its
rate-limit identity.
"""

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from lifeflow_api.action_proposals import router as action_proposals_router
from lifeflow_api.audit_history import router as audit_history_router
from lifeflow_api.auth import router as auth_router
from lifeflow_api.briefs import router as briefs_router
from lifeflow_api.config import Settings, get_settings
from lifeflow_api.connected_accounts import router as connected_accounts_router
from lifeflow_api.correlation import CORRELATION_HEADER, CorrelationIdMiddleware
from lifeflow_api.db import create_engine
from lifeflow_api.demo_mode import router as demo_router
from lifeflow_api.errors import register_error_handlers
from lifeflow_api.evidence_freshness import router as evidence_freshness_router
from lifeflow_api.google.calendar_client import CalendarEventClient
from lifeflow_api.google.gmail_client import GmailDraftClient
from lifeflow_api.google.oauth import GoogleOAuthClient
from lifeflow_api.health import router as health_router
from lifeflow_api.logging_setup import configure_logging
from lifeflow_api.me import router as me_router
from lifeflow_api.memory import router as memory_router
from lifeflow_api.preferences import router as preferences_router
from lifeflow_api.privacy import router as privacy_router
from lifeflow_api.privacy_deletion import router as privacy_deletion_router
from lifeflow_api.rate_limit_policy import InvalidPolicyOverrideError, parse_policy_overrides
from lifeflow_api.rate_limiter import RateLimiter
from lifeflow_api.scheduled_brief_status import router as scheduled_brief_status_router
from lifeflow_api.security.csrf import CSRF_HEADER, CsrfProtectionMiddleware
from lifeflow_api.security.token_cipher import TokenCipherError, build_key_ring
from lifeflow_api.signals import router as signals_router
from lifeflow_api.source_items import router as source_items_router
from lifeflow_api.timeouts import (
    database_statement_timeout_ms,
    google_httpx_timeout,
    google_httpx_write_timeout,
)

_MIN_PRODUCTION_RATE_LIMIT_SECRET_LENGTH = 32


def _session_secret(settings: Settings) -> str:
    if settings.session_secret:
        return settings.session_secret
    if settings.environment == "production":
        raise RuntimeError("SESSION_SECRET must be set in production.")
    # Dev/test convenience: ephemeral secret; sessions reset on restart.
    return secrets.token_urlsafe(32)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = create_engine(
            settings.database_url,
            statement_timeout_ms=database_statement_timeout_ms(settings),
        )
        app.state.sessionmaker = async_sessionmaker(app.state.engine, expire_on_commit=False)
        try:
            yield
        finally:
            await app.state.engine.dispose()
            if app.state.google_http_client is not None:
                await app.state.google_http_client.aclose()
            if app.state.rate_limiter is not None:
                await app.state.rate_limiter.aclose()

    app = FastAPI(
        title="LifeFlow AI API",
        version="0.1.0",
        lifespan=lifespan,
        # API docs stay available in development; revisit exposure before deployment.
        docs_url="/docs" if settings.environment != "production" else None,
    )
    app.state.settings = settings
    # Stage 9 Delivery Phase 5 (§20): the test-only provider-control boundary
    # must never be reachable in production — checked unconditionally, not
    # only when a fake origin happens to be configured, so a stray `true` in
    # a production environment fails startup outright rather than silently
    # doing nothing.
    if settings.e2e_test_controls_enabled and settings.environment == "production":
        raise RuntimeError("E2E_TEST_CONTROLS_ENABLED=true must never be set in production.")
    # LLM provider is off by default (ADR 0001 D4, ADR 0002): a key alone must
    # not enable real model calls — LLM_EXTRACTION_ENABLED=true is required too,
    # and stays false until a real-provider evaluation satisfies ADR 0002.
    app.state.llm_provider = None
    if settings.llm_extraction_enabled:
        if not settings.anthropic_api_key:
            raise RuntimeError("LLM_EXTRACTION_ENABLED=true requires ANTHROPIC_API_KEY to be set.")
        from lifeflow_api.llm.anthropic_provider import AnthropicProvider

        app.state.llm_provider = AnthropicProvider(
            settings.anthropic_api_key, model=settings.anthropic_model
        )

    # Token encryption (threat model T1): required once any real tokens are
    # stored. Demo mode and dev-login never construct a ConnectedAccount
    # with real tokens, so this stays None until TOKEN_KEY is configured.
    # `app.state.token_cipher` holds a `TokenKeyRing` (Stage 11A Phase 4A,
    # F-P3-03), never a bare `AesGcmTokenCipher` — it implements the same
    # `TokenCipher` protocol, so every existing caller is unaffected, but it
    # also carries zero or more legacy keys the rotation service needs to
    # decrypt not-yet-migrated rows.
    app.state.token_cipher = None
    if settings.token_key:
        # The literal `.env.example` development default must never protect
        # a real credential in production — an established guard in the same
        # style as the E2E-test-controls check above.
        if settings.environment == "production" and settings.token_key_id == "dev-1":  # noqa: S105
            raise RuntimeError(
                "TOKEN_KEY_ID must not be the development default ('dev-1') in production."
            )
        try:
            app.state.token_cipher = build_key_ring(
                settings.token_key, settings.token_key_id, settings.token_key_legacy_json
            )
        except TokenCipherError as exc:
            raise RuntimeError(f"Invalid TOKEN_KEY configuration: {exc}") from exc

    # Real Google integration (Stage 7, ADR 0003 D23) is off by default.
    # Demo mode, dev-login, and the synthetic connectors never depend on any
    # of this; when enabled, both separate OAuth client configs (D10) and a
    # token-encryption key are required, or the app refuses to start.
    app.state.google_http_client = None
    app.state.google_oauth_client = None
    app.state.gmail_client = None
    app.state.calendar_client = None
    if settings.google_oauth_initiation_enabled and not settings.google_oauth_enabled:
        raise RuntimeError(
            "GOOGLE_OAUTH_INITIATION_ENABLED=true requires GOOGLE_OAUTH_ENABLED=true."
        )
    if settings.google_oauth_enabled:
        missing = [
            name
            for name, value in {
                "GOOGLE_OIDC_CLIENT_ID": settings.google_oidc_client_id,
                "GOOGLE_OIDC_CLIENT_SECRET": settings.google_oidc_client_secret,
                "GOOGLE_OIDC_REDIRECT_URI": settings.google_oidc_redirect_uri,
                "GOOGLE_CONNECTOR_CLIENT_ID": settings.google_connector_client_id,
                "GOOGLE_CONNECTOR_CLIENT_SECRET": settings.google_connector_client_secret,
                "GOOGLE_CONNECTOR_REDIRECT_URI": settings.google_connector_redirect_uri,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "GOOGLE_OAUTH_ENABLED=true requires " + ", ".join(missing) + " to be set."
            )
        if app.state.token_cipher is None:
            raise RuntimeError("GOOGLE_OAUTH_ENABLED=true requires TOKEN_KEY to be set.")
        app.state.google_http_client = httpx.AsyncClient(timeout=google_httpx_timeout(settings))
        app.state.google_oauth_client = GoogleOAuthClient(app.state.google_http_client)
        write_timeout = google_httpx_write_timeout(settings)
        gmail_kwargs: dict[str, str] = {}
        calendar_kwargs: dict[str, str] = {}
        # Stage 9 Delivery Phase 5 (§20): only ever honoured when the
        # test-controls flag is explicitly on (see the production guard
        # above) — an origin override left in the environment by mistake is
        # otherwise inert.
        if settings.e2e_test_controls_enabled and settings.google_api_origin_override:
            origin = settings.google_api_origin_override.rstrip("/")
            gmail_kwargs["base_url"] = f"{origin}/gmail/v1/users/me"
            calendar_kwargs["base_url"] = f"{origin}/calendar/v3/calendars/primary/events"
        app.state.gmail_client = GmailDraftClient(
            app.state.google_http_client, write_timeout=write_timeout, **gmail_kwargs
        )
        app.state.calendar_client = CalendarEventClient(
            app.state.google_http_client, write_timeout=write_timeout, **calendar_kwargs
        )

    # Stage 9 Delivery Phase 4 (ADR 0005 D64/D81): off by default, matching
    # every other Stage 8/9 feature flag. A missing/short key secret in
    # production is a hard failure (a weak or empty HMAC key would make the
    # bucket digest guessable or collide across subjects); development/test
    # may leave it blank — an ephemeral secret is generated, exactly like
    # SESSION_SECRET, since rate-limit buckets are not required to survive a
    # restart.
    app.state.rate_limiter = None
    app.state.rate_limit_key_secret = ""
    app.state.rate_limit_policy_overrides = {}
    if settings.rate_limiting_enabled:
        if (
            settings.environment == "production"
            and len(settings.rate_limit_key_secret) < _MIN_PRODUCTION_RATE_LIMIT_SECRET_LENGTH
        ):
            raise RuntimeError(
                "RATE_LIMITING_ENABLED=true in production requires RATE_LIMIT_KEY_SECRET "
                f"to be at least {_MIN_PRODUCTION_RATE_LIMIT_SECRET_LENGTH} characters."
            )
        try:
            app.state.rate_limit_policy_overrides = parse_policy_overrides(
                settings.rate_limit_policy_overrides_json
            )
        except InvalidPolicyOverrideError as exc:
            raise RuntimeError(f"Invalid RATE_LIMIT_POLICY_OVERRIDES_JSON: {exc}") from exc
        app.state.rate_limit_key_secret = settings.rate_limit_key_secret or secrets.token_urlsafe(
            32
        )
        redis_client: aioredis.Redis = aioredis.from_url(settings.redis_url)  # type: ignore[no-untyped-call]
        app.state.rate_limiter = RateLimiter(
            redis_client, socket_timeout_seconds=settings.rate_limit_redis_timeout_seconds
        )

    # Middleware runs outermost-last-added: correlation IDs wrap everything,
    # then CSRF rejects forged writes, then the session is available inside.
    app.add_middleware(
        SessionMiddleware,
        secret_key=_session_secret(settings),
        session_cookie="lifeflow_session",
        same_site="lax",
        https_only=settings.environment == "production",
        max_age=60 * 60 * 8,  # 8 hours
    )
    app.add_middleware(CsrfProtectionMiddleware)
    # Only our own web origin may call the API from a browser; credentials
    # (session cookie) and the CSRF header are allowed for it alone.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", CSRF_HEADER, CORRELATION_HEADER],
    )
    app.add_middleware(CorrelationIdMiddleware)
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(me_router)
    app.include_router(preferences_router)
    app.include_router(memory_router)
    app.include_router(scheduled_brief_status_router)
    app.include_router(evidence_freshness_router)
    app.include_router(demo_router)
    app.include_router(source_items_router)
    app.include_router(signals_router)
    app.include_router(briefs_router)
    app.include_router(action_proposals_router)
    app.include_router(audit_history_router)
    app.include_router(connected_accounts_router)
    app.include_router(privacy_router)
    app.include_router(privacy_deletion_router)
    return app


app = create_app()
