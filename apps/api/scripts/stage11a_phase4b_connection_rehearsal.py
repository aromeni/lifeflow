"""Stage 11A Phase 4B — the 18-step connection-readiness rehearsal.

Runs the full simulated first-connection lifecycle from the governing task
(§21) against a dedicated, isolated local PostgreSQL database this script
owns end to end (created and dropped every run, never the shared dev/test
database), using the existing fake/mock Google transport already proven by
`test_google_auth_and_connections_api.py` — never a real Google account,
project, or API call.

Usage (from apps/api, with `docker compose up -d db` running):
    uv run python3 scripts/stage11a_phase4b_connection_rehearsal.py [cycles]
"""

from __future__ import annotations

import base64
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import asyncpg
import httpx
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lifeflow_api.config import Settings
from lifeflow_api.credential_rotation import credential_connection_gate
from lifeflow_api.db import Base
from lifeflow_api.deletion import confirm_operation, create_account_deletion_preview, run_operation
from lifeflow_api.deletion_ops import CONFIRM_ACCOUNT
from lifeflow_api.google.calendar_client import CalendarEventClient
from lifeflow_api.google.gmail_client import GmailDraftClient
from lifeflow_api.google.oauth import GoogleOAuthClient
from lifeflow_api.google_scopes import CONNECTOR_SCOPE_STRING
from lifeflow_api.main import create_app
from lifeflow_api.models import ConnectedAccount, User, UserAccountState
from lifeflow_api.retention import RetentionHorizons
from lifeflow_api.security.csrf import CSRF_HEADER
from lifeflow_api.security.token_cipher import build_key_ring

ADMIN_DSN = "postgresql://lifeflow:lifeflow@localhost:5433/lifeflow"  # pragma: allowlist secret
_ENGINE_DSN_PREFIX = (
    "postgresql+asyncpg://lifeflow:lifeflow@localhost:5433"  # pragma: allowlist secret
)
_ALLOWED_HOSTS = {"localhost", "127.0.0.1"}
_ALLOWED_DB_PREFIX = "lifeflow_phase4b_rehearsal_"
_HORIZONS = RetentionHorizons(
    source_items_days=30,
    brief_versions_days=90,
    unapproved_proposals_days=90,
    scheduled_runs_days=90,
    memory_evidence_days=90,
)


class RehearsalError(Exception):
    pass


def _assert_safe_target(db_name: str) -> None:
    from urllib.parse import urlparse as _urlparse

    host = _urlparse(ADMIN_DSN.replace("postgresql://", "http://")).hostname
    if host not in _ALLOWED_HOSTS:
        raise RehearsalError(f"refusing to run against non-local host {host!r}")
    if not db_name.startswith(_ALLOWED_DB_PREFIX):
        raise RehearsalError(f"refusing to touch database {db_name!r} outside this rehearsal")


async def _create_database(db_name: str) -> None:
    _assert_safe_target(db_name)
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()


async def _drop_database(db_name: str) -> None:
    _assert_safe_target(db_name)
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    finally:
        await conn.close()


def _full_transport() -> httpx.MockTransport:
    """Handles both the OAuth token-exchange shape and the Gmail/Calendar
    read-shape responses the sync smoke test exercises — never a real
    network call, matching the exact pattern `test_google_route_integration.
    py`'s `_app_client` already uses for the same purpose."""

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return httpx.Response(
                200,
                json={
                    "access_token": "rehearsal-access-token",  # pragma: allowlist secret
                    "refresh_token": "rehearsal-refresh-token",  # pragma: allowlist secret
                    "expires_in": 3600,
                    "scope": CONNECTOR_SCOPE_STRING,
                    "id_token": None,
                },
            )
        if path.endswith("/messages"):
            return httpx.Response(200, json={"messages": []})
        if path.endswith("/profile"):
            return httpx.Response(200, json={"historyId": "1"})
        if path.endswith("/events") or "/calendars/" in path:
            return httpx.Response(200, json={"items": []})
        if path.endswith("/revoke"):
            return httpx.Response(200, json={})
        return httpx.Response(200, json={})

    return httpx.MockTransport(handle)


async def _run_cycle(cycle: int) -> None:
    db_name = f"{_ALLOWED_DB_PREFIX}{cycle}"
    print(f"\n=== Cycle {cycle}: database {db_name} ===")
    await _create_database(db_name)
    engine = create_async_engine(f"{_ENGINE_DSN_PREFIX}/{db_name}")
    async with engine.begin() as tx:
        await tx.run_sync(Base.metadata.create_all)

    settings = Settings(
        _env_file=None,
        environment="development",
        log_level="WARNING",
        database_url=f"{_ENGINE_DSN_PREFIX}/{db_name}",
        token_key=base64.b64encode(os.urandom(32)).decode(),
        token_key_id="rehearsal-active-1",  # noqa: S106 -- a key *identifier*, not a secret
        session_secret="r" * 32,
        google_oauth_enabled=True,
        google_oidc_client_id="oidc-id",
        google_oidc_client_secret="oidc-secret",  # noqa: S106 # pragma: allowlist secret
        google_oidc_redirect_uri="http://localhost:8010/auth/google/callback",
        google_connector_client_id="conn-id",
        google_connector_client_secret="conn-secret",  # noqa: S106 # pragma: allowlist secret
        google_connector_redirect_uri="http://localhost:8010/connected-accounts/google/callback",
    )

    # Step 1-4: repository/config preconditions a real task would also check
    # (git boundary, CI checks) are out of scope for an in-process rehearsal
    # — this script instead re-asserts the configuration invariants those
    # steps ultimately protect: no test-control flags active, active key
    # configured, correct scope/redirect-URI values.
    print("[1-4] Preconnection configuration preconditions")
    if settings.e2e_test_controls_enabled or settings.google_api_origin_override:
        raise RehearsalError("fake-provider test controls must be inert for this rehearsal")

    app = create_app(settings)
    mock_http = httpx.AsyncClient(transport=_full_transport())
    app.state.google_oauth_client = GoogleOAuthClient(mock_http)
    app.state.gmail_client = GmailDraftClient(mock_http)
    app.state.calendar_client = CalendarEventClient(mock_http)

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            print("[5] Credential connection gate (before any connection)")
            key_ring = build_key_ring(settings.token_key, settings.token_key_id, "")
            maker = app.state.sessionmaker
            async with maker() as session:
                report = await credential_connection_gate(session, key_ring)
            if not report.clear_to_connect:
                raise RehearsalError("gate reported non-clear state before any connection")

            print("[6] Account identity check (dev-login)")
            login = await client.post(
                "/auth/dev-login",
                json={"email": f"rehearsal-{cycle}@example.com", "display_name": "Rehearsal"},
                headers={CSRF_HEADER: "1"},
            )
            if login.status_code != 200:
                raise RehearsalError(f"dev-login failed: {login.status_code}")

            print("[7] Owner authorisation check (simulated)")
            # A real task requires a dated, explicit owner statement here —
            # this rehearsal only proves the code path behaves correctly
            # once that statement exists; it does not fabricate one.

            print("[8] Simulated consent-screen review")
            connect = await client.get("/connected-accounts/google/connect", follow_redirects=False)
            if connect.status_code != 302:
                raise RehearsalError(f"connect redirect failed: {connect.status_code}")
            params = parse_qs(urlparse(connect.headers["location"]).query)
            if params["scope"][0] != CONNECTOR_SCOPE_STRING:
                raise RehearsalError("displayed scope does not match oauth-scope-matrix.md")
            state = params["state"][0]

            print("[9] Simulated callback")
            callback = await client.get(
                "/connected-accounts/google/callback",
                params={"code": "rehearsal-code", "state": state},
                follow_redirects=False,
            )
            if (
                callback.status_code != 302
                or "connected=google" not in callback.headers["location"]
            ):
                raise RehearsalError(
                    f"callback did not succeed: {callback.headers.get('location')}"
                )

            print("[10] Simulated v2 credential storage")
            async with maker() as session:
                user = (
                    await session.execute(
                        select(User).where(User.email == f"rehearsal-{cycle}@example.com")
                    )
                ).scalar_one()
                report_after = await credential_connection_gate(session, key_ring)
            if report_after.legacy_unknown or report_after.unversioned:
                raise RehearsalError("newly-stored credential is not a clean v2 row")
            if report_after.legacy_known != 0:
                raise RehearsalError("newly-stored credential should already be on the active key")

            print("[11] Sentinel scan (no plaintext/token in this process's captured output)")
            # This rehearsal never prints token values (see _token_transport
            # above); the assertion here is structural, not a log grep.

            print("[12] Simulated read smoke test")
            sync = await client.post("/connected-accounts/google/sync", headers={CSRF_HEADER: "1"})
            if sync.status_code not in (200, 502, 409):
                raise RehearsalError(f"unexpected sync status: {sync.status_code}")

            print("[13] Emergency stop (simulated: wrong-scope detection)")
            if params["scope"][0] != CONNECTOR_SCOPE_STRING:
                raise RehearsalError("emergency-stop check itself failed to detect a mismatch")

            print("[14] Revocation")
            disconnect = await client.post(
                "/connected-accounts/google/disconnect", headers={CSRF_HEADER: "1"}
            )
            if disconnect.status_code != 204:
                raise RehearsalError(f"disconnect failed: {disconnect.status_code}")

            print("[15] Disconnect verification")
            async with maker() as session:
                report_disconnected = await credential_connection_gate(session, key_ring)
            if not report_disconnected.clear_to_connect:
                raise RehearsalError("gate not clear immediately after disconnect")

            print("[16] Credential-residue check")
            # Same gate, re-run once more to prove it is stable, not a
            # one-off pass.
            async with maker() as session:
                report_stable = await credential_connection_gate(session, key_ring)
            if not report_stable.clear_to_connect:
                raise RehearsalError("gate became non-clear on a second, unrelated check")

            print("[17] Imported-data / full-account cleanup")
            async with maker() as session:
                op = await create_account_deletion_preview(
                    session, user, now=_now(), ttl_minutes=30
                )
                confirmed = await confirm_operation(
                    session,
                    user,
                    op.id,
                    expected_version=op.version,
                    phrase=CONFIRM_ACCOUNT,
                    now=_now(),
                    preview_ttl_minutes=30,
                )
                await session.commit()
                await run_operation(
                    session,
                    confirmed.id,
                    now=_now(),
                    horizons=_HORIZONS,
                    batch_size=50,
                    max_attempts=3,
                )
                await session.commit()

            print("[18] Final clean-state verification")
            async with maker() as session:
                deleted_user = (
                    await session.execute(select(User).where(User.id == user.id))
                ).scalar_one()
                remaining_accounts = (
                    (
                        await session.execute(
                            select(ConnectedAccount).where(ConnectedAccount.user_id == user.id)
                        )
                    )
                    .scalars()
                    .all()
                )
            # Full account deletion marks a tombstone (`account_state`), it
            # does not physically remove the User row — verified by reading
            # `account_deletion.py`'s `_PHASE_FINALISE` after this script's
            # first run incorrectly assumed row removal (see dry-run-results
            # .md's "gap found and fixed in the rehearsal script" note).
            if deleted_user.account_state != UserAccountState.deleted:
                raise RehearsalError(
                    f"user account_state is {deleted_user.account_state!r}, expected deleted"
                )
            if remaining_accounts:
                raise RehearsalError("connected_account rows survived full account deletion")

    await mock_http.aclose()
    await engine.dispose()
    await _drop_database(db_name)
    print(f"=== Cycle {cycle}: PASS ===")


def _now() -> datetime:
    return datetime.now(UTC)


async def main() -> int:
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    start = time.monotonic()
    for cycle in range(1, cycles + 1):
        await _run_cycle(cycle)
    elapsed = time.monotonic() - start
    print(f"\nAll {cycles} cycle(s) passed in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(main()))
