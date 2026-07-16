"""Application configuration loaded from the environment.

Secrets are provided only via environment variables (or a local .env file that
is never committed). See the root .env.example for the documented set.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
