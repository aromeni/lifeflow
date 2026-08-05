"""Stage 11A Phase 4D — the fake-provider connection-and-cleanup rehearsal.

Runs the exact controlled sequence the live checkpoint will follow —
connect, verify the stored credential, four read-only smoke calls, verify
the write kill switch, revoke, disconnect, verify zero residue — against a
dedicated, isolated local PostgreSQL database this script owns end to end
(created and dropped every run), using `httpx.MockTransport` for every
Google-facing call, exactly like Phase 4B's own connection rehearsal. Never
a real Google account, project, or API call.

Usage (from apps/api, with `docker compose up -d db` running):
    uv run python3 scripts/stage11a_phase4d_connection_rehearsal.py [cycles]
"""

from __future__ import annotations

import base64
import os
import sys
import time
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
from lifeflow_api.google.calendar_client import CalendarEventClient
from lifeflow_api.google.gmail_client import GmailDraftClient
from lifeflow_api.google.oauth import GoogleOAuthClient
from lifeflow_api.google_scopes import CONNECTOR_SCOPE_STRING
from lifeflow_api.main import create_app
from lifeflow_api.models import AuditEvent, ConnectedAccount, User
from lifeflow_api.security.credential_context import ACCESS_TOKEN_FIELD, credential_context
from lifeflow_api.security.csrf import CSRF_HEADER
from lifeflow_api.security.token_cipher import build_key_ring
from lifeflow_api.testing.no_live_network import block_live_google_network

ADMIN_DSN = "postgresql://lifeflow:lifeflow@localhost:5433/lifeflow"  # pragma: allowlist secret
_ENGINE_DSN_PREFIX = (
    "postgresql+asyncpg://lifeflow:lifeflow@localhost:5433"  # pragma: allowlist secret
)
_ALLOWED_HOSTS = {"localhost", "127.0.0.1"}
_ALLOWED_DB_PREFIX = "lifeflow_phase4d_rehearsal_"


class RehearsalError(Exception):
    pass


def _assert_safe_target(db_name: str) -> None:
    host = urlparse(ADMIN_DSN.replace("postgresql://", "http://")).hostname
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
        if path.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress": "rehearsal@example.com"})
        if path.endswith("/messages"):
            return httpx.Response(200, json={"messages": []})
        if path.endswith("/drafts"):
            raise AssertionError("write attempted: Gmail drafts endpoint must never be reached")
        if path == "/calendar/v3/calendars/primary":
            return httpx.Response(200, json={"id": "rehearsal@example.com"})
        if path.endswith("/events"):
            if request.method == "POST":
                raise AssertionError("write attempted: Calendar events endpoint must never POST")
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
        google_connector_oauth_enabled=True,
        # The one flag this whole rehearsal exists to prove: even with a
        # real (fake-transport) connected account, writes stay blocked.
        google_provider_writes_enabled=False,
        google_oidc_client_id="oidc-id",
        google_oidc_client_secret="oidc-secret",  # noqa: S106 # pragma: allowlist secret
        google_oidc_redirect_uri="http://localhost:8010/auth/google/callback",
        google_connector_client_id="conn-id",
        google_connector_client_secret="conn-secret",  # noqa: S106 # pragma: allowlist secret
        google_connector_redirect_uri="http://localhost:8010/connected-accounts/google/callback",
    )

    print("[1] Preconnection configuration preconditions")
    if settings.e2e_test_controls_enabled or settings.google_api_origin_override:
        raise RehearsalError("fake-provider test controls must be inert for this rehearsal")
    if settings.google_provider_writes_enabled:
        raise RehearsalError("provider writes must be disabled for this rehearsal")

    app = create_app(settings)

    # Safety net identical to Phase 4B's rehearsal: replace the shared real
    # Google HTTP client with a loopback-only guard before installing the
    # per-cycle mocks, so a forgotten mock assignment is refused, not real.
    await app.state.google_http_client.aclose()
    app.state.google_http_client = httpx.AsyncClient(
        transport=block_live_google_network(httpx.AsyncHTTPTransport())
    )
    app.state.google_oauth_client = GoogleOAuthClient(app.state.google_http_client)
    app.state.gmail_client = GmailDraftClient(app.state.google_http_client)
    app.state.calendar_client = CalendarEventClient(app.state.google_http_client)

    mock_http = httpx.AsyncClient(transport=_full_transport())
    app.state.google_oauth_client = GoogleOAuthClient(mock_http)
    app.state.gmail_client = GmailDraftClient(mock_http)
    app.state.calendar_client = CalendarEventClient(mock_http)

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            print("[2] Credential connection gate (before any connection)")
            key_ring = build_key_ring(settings.token_key, settings.token_key_id, "")
            maker = app.state.sessionmaker
            async with maker() as session:
                report = await credential_connection_gate(session, key_ring)
            if not report.clear_to_connect:
                raise RehearsalError("gate reported non-clear state before any connection")

            print("[3] Account identity (dev-login)")
            email = f"rehearsal-{cycle}@example.com"
            login = await client.post(
                "/auth/dev-login",
                json={"email": email, "display_name": "Rehearsal"},
                headers={CSRF_HEADER: "1"},
            )
            if login.status_code != 200:
                raise RehearsalError(f"dev-login failed: {login.status_code}")

            print("[4] Consent-screen scope review")
            connect = await client.get("/connected-accounts/google/connect", follow_redirects=False)
            if connect.status_code != 302:
                raise RehearsalError(f"connect redirect failed: {connect.status_code}")
            params = parse_qs(urlparse(connect.headers["location"]).query)
            if params["scope"][0] != CONNECTOR_SCOPE_STRING:
                raise RehearsalError("displayed scope does not match the approved four-scope set")
            if "code_challenge" not in params or params["code_challenge_method"][0] != "S256":
                raise RehearsalError("PKCE parameters missing from the connector redirect")
            state = params["state"][0]

            print("[5] Callback")
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

            print("[6] Credential storage verification (v2, active key, single row)")
            async with maker() as session:
                user = (await session.execute(select(User).where(User.email == email))).scalar_one()
                report_after = await credential_connection_gate(session, key_ring)
            if report_after.legacy_unknown or report_after.unversioned:
                raise RehearsalError("newly-stored credential is not a clean v2 row")
            if report_after.legacy_known != 0:
                raise RehearsalError("newly-stored credential should already be on the active key")

            print(
                "[7] Read-only smoke sequence (getProfile, messages.list, "
                "calendars.get primary, events.list primary)"
            )
            async with maker() as session:
                account = (
                    await session.execute(
                        select(ConnectedAccount).where(ConnectedAccount.user_id == user.id)
                    )
                ).scalar_one()
                access_token = key_ring.decrypt(
                    account.encrypted_access_token,
                    context=credential_context(
                        connected_account_id=account.id,
                        user_id=account.user_id,
                        provider=account.provider,
                        field=ACCESS_TOKEN_FIELD,
                    ),
                )
            gmail = GmailDraftClient(mock_http)
            calendar = CalendarEventClient(mock_http)
            email_value = await gmail.get_profile_email(access_token=access_token)
            del email_value
            await gmail.list_messages(
                access_token=access_token, query="", page_token=None, max_results=5
            )
            calendar_id = await calendar.get_primary_calendar_metadata(access_token=access_token)
            del calendar_id
            await calendar.list_events(
                access_token=access_token,
                time_min=None,
                time_max=None,
                sync_token=None,
                page_token=None,
                max_results=5,
            )

            print("[8] Write kill switch — configuration re-check")
            # The behavioural proof that a real, connected account still
            # cannot write — approve-and-execute through the real HTTP
            # routes, asserting `provider_writes_disabled` before any
            # provider call — lives in
            # `test_gmail_write_blocked_when_provider_writes_disabled` /
            # `test_calendar_write_blocked_when_provider_writes_disabled`
            # (`test_google_route_integration.py`), which exercise the
            # identical `google_wiring.build_google_executor_registry` gate
            # this rehearsal's app instance also uses. Re-asserting the
            # config flag here, on the actual `app` instance mid-rehearsal,
            # closes the gap between "the flag was set at construction" and
            # "the flag is still what a write attempt would see right now".
            if app.state.settings.google_provider_writes_enabled:
                raise RehearsalError("provider writes became enabled mid-rehearsal")

            print("[9] Revocation and disconnect")
            disconnect = await client.post(
                "/connected-accounts/google/disconnect", headers={CSRF_HEADER: "1"}
            )
            if disconnect.status_code != 204:
                raise RehearsalError(f"disconnect failed: {disconnect.status_code}")

            print("[10] Revocation-confirmation truthfulness check")
            async with maker() as session:
                event = (
                    (
                        await session.execute(
                            select(AuditEvent)
                            .where(AuditEvent.event_type == "account.disconnected")
                            .order_by(AuditEvent.timestamp.desc())
                        )
                    )
                    .scalars()
                    .first()
                )
            if event is None or "revocation_confirmed" not in event.safe_metadata_json:
                raise RehearsalError("disconnect did not record a revocation-confirmation result")
            if event.safe_metadata_json["revocation_confirmed"] is not True:
                raise RehearsalError(
                    "mock transport returned 200 for /revoke but disconnect recorded "
                    f"{event.safe_metadata_json['revocation_confirmed']!r}"
                )

            print("[11] Final residue check")
            async with maker() as session:
                report_final = await credential_connection_gate(session, key_ring)
                remaining = (
                    (
                        await session.execute(
                            select(ConnectedAccount).where(
                                ConnectedAccount.user_id == user.id,
                                ConnectedAccount.encrypted_access_token.is_not(None),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            if not report_final.clear_to_connect:
                raise RehearsalError("gate not clear after disconnect")
            if remaining:
                raise RehearsalError("a credential-bearing row survived disconnect")

    await mock_http.aclose()
    await engine.dispose()
    await _drop_database(db_name)
    print(f"=== Cycle {cycle}: PASS ===")


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
