"""Application factory.

Run locally with:
    uv run uvicorn --app-dir src lifeflow_api.main:app --reload --port 8010
"""

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from lifeflow_api.action_proposals import router as action_proposals_router
from lifeflow_api.auth import router as auth_router
from lifeflow_api.briefs import router as briefs_router
from lifeflow_api.config import Settings, get_settings
from lifeflow_api.correlation import CORRELATION_HEADER, CorrelationIdMiddleware
from lifeflow_api.db import create_engine
from lifeflow_api.demo_mode import router as demo_router
from lifeflow_api.errors import register_error_handlers
from lifeflow_api.health import router as health_router
from lifeflow_api.logging_setup import configure_logging
from lifeflow_api.me import router as me_router
from lifeflow_api.security.csrf import CSRF_HEADER, CsrfProtectionMiddleware
from lifeflow_api.signals import router as signals_router
from lifeflow_api.source_items import router as source_items_router


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
        app.state.engine = create_engine(settings.database_url)
        app.state.sessionmaker = async_sessionmaker(app.state.engine, expire_on_commit=False)
        try:
            yield
        finally:
            await app.state.engine.dispose()

    app = FastAPI(
        title="LifeFlow AI API",
        version="0.1.0",
        lifespan=lifespan,
        # API docs stay available in development; revisit exposure before deployment.
        docs_url="/docs" if settings.environment != "production" else None,
    )
    app.state.settings = settings
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
    app.include_router(demo_router)
    app.include_router(source_items_router)
    app.include_router(signals_router)
    app.include_router(briefs_router)
    app.include_router(action_proposals_router)
    return app


app = create_app()
