"""Application configuration loaded from the environment.

Secrets are provided only via environment variables (or a local .env file that
is never committed). See the root .env.example for the documented set.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
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

    # Stage 9 Delivery Phase 1 (ADR 0005): provisional product retention
    # defaults, in days, surfaced read-only by the Privacy Centre. These are
    # *product* defaults for the pilot, not claimed legal mandates, and are
    # NOT yet enforced by any job — enforcement is Delivery Phase 2. Globally
    # configured and validated here (positive integers); there is deliberately
    # no per-user DataRetentionPolicy table at this stage. Two categories have
    # no fixed horizon and are therefore not represented as day counts:
    # Signals follow their supporting SourceItem's lifecycle, and
    # pending/uncertain executions are never auto-deleted before reconciliation
    # (both described in words by the Privacy Centre, never as a duration).
    retention_source_items_days: int = Field(default=30, gt=0)
    retention_brief_versions_days: int = Field(default=90, gt=0)
    retention_unapproved_proposals_days: int = Field(default=90, gt=0)
    retention_approved_terminal_days: int = Field(default=365, gt=0)
    retention_scheduled_runs_days: int = Field(default=90, gt=0)
    retention_memory_evidence_days: int = Field(default=90, gt=0)
    retention_audit_tombstone_days: int = Field(default=365, gt=0)
    retention_operational_logs_days: int = Field(default=30, gt=0)
    retention_aggregated_metrics_days: int = Field(default=90, gt=0)

    # Stage 9 Delivery Phase 2 (ADR 0005): the durable deletion engine. Bounded
    # batch size so no single destructive transaction is unbounded (validated
    # positive). Preview TTL after which a typed confirmation is refused.
    # Heartbeat timeout after which a `running` operation is considered stale
    # and recovered. Daily retention work is bounded (max operations enqueued
    # per tick) so an initial rollout never triggers a multi-year backfill
    # storm. Enforcement is opt-in per deployment exactly like the scheduler:
    # the API (preview/confirm) is always available, but retention only runs
    # when both a worker and this flag are active.
    deletion_batch_size: int = Field(default=200, gt=0)
    deletion_preview_ttl_minutes: int = Field(default=30, gt=0)
    deletion_heartbeat_timeout_minutes: int = Field(default=10, gt=0)
    deletion_max_attempts: int = Field(default=3, gt=0)
    retention_enforcement_enabled: bool = False
    retention_max_operations_per_tick: int = Field(default=50, gt=0)

    # Stage 9 rate-limiting trusted-proxy allowlist (architecture approved in
    # ADR 0005; thresholds and enforcement land in Delivery Phase 4). CIDRs
    # whose immediate-peer proxy may set X-Forwarded-For. Empty (the default)
    # means trust no forwarded headers — the direct peer IP is authoritative.
    trusted_proxy_cidrs: str = ""

    # Stage 9 Delivery Phase 4 (ADR 0005 D64): Redis-backed rate limiting.
    # Off by default, matching every other Stage 8/9 feature flag (scheduled
    # briefs, retention enforcement, LLM extraction, Google OAuth) — existing
    # deployments and the whole test suite are unaffected until a deployment
    # opts in. When enabled, requests are keyed by an HMAC digest (never a raw
    # user id or IP) using this secret; production refuses to start with a
    # missing or short secret, but development/test may leave it blank (an
    # ephemeral secret is generated at startup, exactly like SESSION_SECRET).
    rate_limiting_enabled: bool = False
    rate_limit_key_secret: str = ""
    rate_limit_redis_prefix: str = "ratelimit:v1"
    # A JSON object of {policy_code: {"capacity": int, "refill_amount": int,
    # "refill_window_seconds": int}} overriding individual registered
    # policies' defaults (rate_limit_policy.py). Empty string means no
    # overrides. Unknown policy codes or out-of-range numeric fields fail
    # configuration validation at startup, never silently.
    rate_limit_policy_overrides_json: str = ""
    # A malformed/overlong X-Forwarded-For chain must not grant a caller a
    # fresh identity — bounded so a pathological chain fails safely instead of
    # being walked indefinitely.
    rate_limit_max_forwarded_hops: int = Field(default=10, gt=0)
    rate_limit_redis_timeout_seconds: float = Field(default=0.2, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
