"""Application configuration loaded from the environment.

Secrets are provided only via environment variables (or a local .env file that
is never committed). See the root .env.example for the documented set.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# `.env` lives at the repo root, but this module is imported with the process
# CWD set to wherever uvicorn/pytest was launched from (commonly `apps/api`,
# per the documented dev command) — a plain relative "`.env`" would silently
# resolve against that CWD and find nothing there. Anchor it to this file's
# location instead so `.env` loads correctly regardless of invocation CWD.
_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    # Development default; real deployments override via DATABASE_URL.
    database_url: str = (
        "postgresql+asyncpg://lifeflow:lifeflow@localhost:5433/lifeflow"  # pragma: allowlist secret
    )
    # Signs the session cookie. Empty is tolerated outside production (an
    # ephemeral secret is generated at startup — sessions reset on restart);
    # production refuses to start without it.
    session_secret: str = ""
    # Base64-encoded 32-byte key for encrypting OAuth tokens at rest
    # (see security/token_cipher.py). Only required once tokens are stored.
    token_key: str = ""
    token_key_id: str = "dev-1"  # noqa: S105 — key *identifier*, not a secret
    # Browser origin allowed to call this API with credentials (CORS).
    web_origin: str = "http://localhost:3000"
    # LLM-assisted extraction (optional — mock/deterministic paths never need it).
    # A key alone is NOT enough: real-provider calls stay disabled until
    # LLM_EXTRACTION_ENABLED=true is set explicitly. ADR 0002 requires a
    # real-provider evaluation before this is enabled outside evals.
    llm_extraction_enabled: bool = False
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"

    # Real Google integration (Stage 7, ADR 0003) — disabled by default. Demo
    # mode, dev-login, and the synthetic connectors never depend on any of
    # these being set. When enabled, BOTH client configs below are required
    # or the app refuses to start (ADR 0003 D23).
    google_oauth_enabled: bool = False
    # App sign-in (OIDC): openid+email+profile only, never mailbox access
    # (ADR 0003 D10). Deliberately a separate client from the one below.
    google_oidc_client_id: str = ""
    google_oidc_client_secret: str = ""
    google_oidc_redirect_uri: str = ""
    # Connector consent (Gmail/Calendar data scopes), requested only from the
    # Connections screen after the user already has a LifeFlow session.
    google_connector_client_id: str = ""
    google_connector_client_secret: str = ""
    google_connector_redirect_uri: str = ""

    # Stage 8 Phase 2: the scheduled brief (ADR 0004 D47-D50). Optional for
    # demo/CI exactly like the LLM provider — the web API is fully usable
    # (including manual brief generation) with Redis absent; only the
    # scheduled-brief status surface reports reduced capability, and no
    # scheduling happens without a running worker regardless.
    redis_url: str = "redis://localhost:6380/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
