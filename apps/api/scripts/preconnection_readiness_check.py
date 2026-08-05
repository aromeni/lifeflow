"""Stage 11A Phase 4B — the content-free preconnection readiness command.

A single command a future connection task (or an operator) can run
immediately before attempting a real Google OAuth connection, to confirm
every mandatory prerequisite this repository can check for itself. It never
displays a secret, a token, or any private content — only bounded
pass/fail facts and, where relevant, non-secret configuration values
(environment name, key id, redirect URI) that are already documented as
safe-to-display in `.env.example` and the Phase 4A/4B evidence pack.

Usage (from apps/api):
    uv run python3 scripts/preconnection_readiness_check.py
    uv run python3 scripts/preconnection_readiness_check.py --json

Exit code 0 only if every mandatory check passes; 1 otherwise.

This script does not create a Google account, a Google Cloud project, or an
OAuth connection. It only inspects the current local configuration and
database/Redis state.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from lifeflow_api.config import get_settings
from lifeflow_api.credential_rotation import credential_connection_gate
from lifeflow_api.db import check_database, create_engine
from lifeflow_api.health import check_redis
from lifeflow_api.models import ConnectedAccount, User
from lifeflow_api.security.token_cipher import TokenCipherError, build_key_ring

_DEV_KEY_ID = "dev-1"
_EXPECTED_OIDC_REDIRECT_URI = "http://localhost:8010/auth/google/callback"
_EXPECTED_CONNECTOR_REDIRECT_URI = "http://localhost:8010/connected-accounts/google/callback"


def _is_placeholder(value: str) -> bool:
    """Classify known-safe placeholder shapes without exposing the value."""

    lowered = value.casefold()
    return not value or "your-" in lowered or "placeholder" in lowered


@dataclass
class ReadinessCheck:
    name: str
    passed: bool
    detail: str


async def _run_checks() -> list[ReadinessCheck]:
    checks: list[ReadinessCheck] = []
    settings = get_settings()

    checks.append(
        ReadinessCheck(
            "environment_not_production",
            settings.environment != "production",
            f"environment={settings.environment}",
        )
    )
    checks.append(
        ReadinessCheck(
            "e2e_test_controls_disabled",
            not settings.e2e_test_controls_enabled,
            f"e2e_test_controls_enabled={settings.e2e_test_controls_enabled}",
        )
    )
    checks.append(
        ReadinessCheck(
            "fake_provider_override_unset",
            settings.google_api_origin_override == "",
            "google_api_origin_override is set" if settings.google_api_origin_override else "unset",
        )
    )

    alembic_result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    heads = [line for line in alembic_result.stdout.splitlines() if line.strip()]
    checks.append(
        ReadinessCheck(
            "single_alembic_head",
            alembic_result.returncode == 0 and len(heads) == 1,
            f"{len(heads)} head(s) reported" if heads else "alembic heads failed",
        )
    )
    checks.append(
        ReadinessCheck(
            "migration_0012_applied",
            any("0012" in line for line in heads),
            heads[0] if heads else "no head reported",
        )
    )

    if not settings.token_key:
        checks.append(ReadinessCheck("active_key_configured", False, "TOKEN_KEY is not set"))
        checks.append(
            ReadinessCheck(
                "dev_key_id_rejected_in_production", True, "not applicable — no key configured"
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                "active_key_configured",
                True,
                f"active key id={settings.token_key_id}",
            )
        )
        dev_default_would_be_rejected = not (
            settings.environment == "production" and settings.token_key_id == _DEV_KEY_ID
        )
        checks.append(
            ReadinessCheck(
                "dev_key_id_rejected_in_production",
                dev_default_would_be_rejected,
                "safe"
                if dev_default_would_be_rejected
                else "dev-1 key id would be rejected at startup",
            )
        )

    engine = create_engine(settings.database_url)
    try:
        try:
            await check_database(engine)
            checks.append(ReadinessCheck("database_reachable", True, "PostgreSQL reachable"))
        except Exception as exc:
            checks.append(
                ReadinessCheck("database_reachable", False, f"unreachable: {type(exc).__name__}")
            )
            gate_check = ReadinessCheck(
                "connection_gate_clear", False, "skipped — database unreachable"
            )
            checks.append(gate_check)
        else:
            try:
                key_ring = build_key_ring(
                    settings.token_key, settings.token_key_id, settings.token_key_legacy_json
                )
            except TokenCipherError as exc:
                checks.append(
                    ReadinessCheck("connection_gate_clear", False, f"key ring invalid: {exc}")
                )
            else:
                maker = async_sessionmaker(engine, expire_on_commit=False)
                async with maker() as session:
                    report = await credential_connection_gate(session, key_ring)
                    google_identity_bindings = int(
                        await session.scalar(
                            select(func.count())
                            .select_from(User)
                            .where(User.google_subject.is_not(None))
                        )
                        or 0
                    )
                    stored_credential_rows = int(
                        await session.scalar(
                            select(func.count())
                            .select_from(ConnectedAccount)
                            .where(
                                or_(
                                    ConnectedAccount.encrypted_access_token.is_not(None),
                                    ConnectedAccount.encrypted_refresh_token.is_not(None),
                                )
                            )
                        )
                        or 0
                    )
                checks.append(
                    ReadinessCheck(
                        "connection_gate_clear",
                        report.clear_to_connect,
                        f"unversioned={report.unversioned} legacy_known={report.legacy_known} "
                        f"legacy_unknown={report.legacy_unknown}",
                    )
                )
                checks.append(
                    ReadinessCheck(
                        "google_identity_bindings_zero",
                        google_identity_bindings == 0,
                        f"google_identity_bindings={google_identity_bindings}",
                    )
                )
                checks.append(
                    ReadinessCheck(
                        "stored_credential_rows_zero",
                        stored_credential_rows == 0,
                        f"stored_credential_rows={stored_credential_rows}",
                    )
                )
    finally:
        await engine.dispose()

    redis_ok = await check_redis(settings.redis_url, timeout_seconds=1.0)
    checks.append(
        ReadinessCheck("redis_reachable", redis_ok, "reachable" if redis_ok else "unreachable")
    )

    client_values = (
        settings.google_oidc_client_id,
        settings.google_oidc_client_secret,
        settings.google_connector_client_id,
        settings.google_connector_client_secret,
    )
    clients_configured = settings.google_oauth_enabled and all(
        not _is_placeholder(value) for value in client_values
    )
    checks.append(
        ReadinessCheck(
            "oauth_client_configuration_present",
            clients_configured,
            "configured (values not displayed)"
            if clients_configured
            else "unset or placeholder configuration",
        )
    )

    single_client_mapping = clients_configured and (
        settings.google_oidc_client_id == settings.google_connector_client_id
        and settings.google_oidc_client_secret == settings.google_connector_client_secret
    )
    checks.append(
        ReadinessCheck(
            "single_web_client_mapping",
            single_client_mapping,
            "one physical client mapped to both logical flows"
            if single_client_mapping
            else "single physical client mapping not confirmed",
        )
    )

    callbacks_approved = (
        settings.google_oidc_redirect_uri == _EXPECTED_OIDC_REDIRECT_URI
        and settings.google_connector_redirect_uri == _EXPECTED_CONNECTOR_REDIRECT_URI
    )
    checks.append(
        ReadinessCheck(
            "callback_configuration_approved",
            callbacks_approved,
            "exact Phase 4C localhost callbacks configured"
            if callbacks_approved
            else "callback configuration differs from the approved values",
        )
    )

    # Stage 11A Phase 6A: the original single `oauth_initiation_blocked`
    # check covered one flag shared by both Google flows — exactly the
    # coupling a real incident showed was unsafe. Four independent states
    # are reported now, matching the four independent flags that actually
    # exist: GOOGLE_PROVIDER_CONFIGURED (informational — client
    # configuration is complete) and three safety states that must each be
    # blocked by default (PASS = disabled), never inferred from one another.
    checks.append(
        ReadinessCheck(
            "GOOGLE_PROVIDER_CONFIGURED",
            clients_configured,
            "configured" if clients_configured else "not configured",
        )
    )
    oidc_signin_blocked = not settings.google_oidc_signin_enabled
    checks.append(
        ReadinessCheck(
            "GOOGLE_OIDC_SIGNIN_ENABLED",
            oidc_signin_blocked,
            "blocked pending explicit owner authorisation"
            if oidc_signin_blocked
            else "enabled — must be blocked outside an explicitly authorised sign-in window",
        )
    )
    connector_oauth_blocked = not settings.google_connector_oauth_enabled
    checks.append(
        ReadinessCheck(
            "GOOGLE_CONNECTOR_OAUTH_ENABLED",
            connector_oauth_blocked,
            "blocked pending explicit owner authorisation"
            if connector_oauth_blocked
            else "enabled — must be blocked outside an explicitly authorised connection window",
        )
    )
    provider_writes_blocked = not settings.google_provider_writes_enabled
    checks.append(
        ReadinessCheck(
            "GOOGLE_PROVIDER_WRITES_ENABLED",
            provider_writes_blocked,
            "blocked pending explicit owner authorisation"
            if provider_writes_blocked
            else "enabled — must be blocked outside an explicitly authorised write window",
        )
    )

    return checks


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    args = parser.parse_args()

    checks = await _run_checks()
    all_passed = all(check.passed for check in checks)

    if args.json:
        print(
            json.dumps(
                {
                    "clear_to_connect": all_passed,
                    "checks": [
                        {"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks
                    ],
                },
                indent=2,
            )
        )
    else:
        for check in checks:
            status = "PASS" if check.passed else "FAIL"
            print(f"[{status}] {check.name}: {check.detail}")
        print()
        print("READY" if all_passed else "NOT READY")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
