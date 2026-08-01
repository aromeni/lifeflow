"""Stage 11A Phase 4B — the no-live-network guard for readiness tooling.

Regression coverage for `lifeflow_api.testing.no_live_network`, added after
an early, uncommitted draft of `stage11a_phase4b_connection_rehearsal.py`
sent one real, unauthenticated GET to `gmail.googleapis.com` (see
`docs/evaluation/stage-11/owner-validation/phase-4b/dry-run-results.md`'s
exact-boundary classification). These tests prove the guard itself, not
the rehearsal script — the rehearsal's own 3/3 dry runs are the tool-level
proof it is actually installed and effective.
"""

from __future__ import annotations

import base64
import os
import re

import httpx
import pytest

from lifeflow_api.config import Settings
from lifeflow_api.main import create_app
from lifeflow_api.testing.no_live_network import (
    KNOWN_GOOGLE_HOSTS,
    LiveNetworkAttemptError,
    block_live_google_network,
)

pytestmark = pytest.mark.asyncio


def _never_called(request: httpx.Request) -> httpx.Response:
    raise AssertionError("wrapped transport must not run for a blocked host")


@pytest.mark.parametrize("host", sorted(KNOWN_GOOGLE_HOSTS))
async def test_each_known_google_host_is_blocked(host: str) -> None:
    guard = block_live_google_network(httpx.MockTransport(_never_called))
    request = httpx.Request("GET", f"https://{host}/some/path")
    with pytest.raises(LiveNetworkAttemptError, match=host):
        await guard.handle_async_request(request)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
async def test_loopback_hosts_reach_the_wrapped_transport(host: str) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    guard = block_live_google_network(httpx.MockTransport(handle))
    request = httpx.Request("GET", f"http://{host}:8010/connected-accounts/google/connect")
    response = await guard.handle_async_request(request)
    assert response.status_code == 200


async def test_arbitrary_non_loopback_host_is_also_blocked() -> None:
    """The guard is an allowlist, not a blocklist — it must also refuse a
    host that is neither loopback nor one of the five named Google hosts,
    proving it covers "any other non-loopback provider origin", not only
    the specific hosts enumerated in the governing instruction."""
    guard = block_live_google_network(httpx.MockTransport(_never_called))
    request = httpx.Request("GET", "https://evil-mirror.example.net/gmail/v1/users/me/messages")
    with pytest.raises(LiveNetworkAttemptError):
        await guard.handle_async_request(request)


async def test_no_environment_variable_can_select_a_live_origin(monkeypatch) -> None:
    """The guard consults only the outgoing request's own resolved host,
    never a setting or environment variable — so no override, however it
    is spelled, can silently exempt a live Google origin."""
    monkeypatch.setenv("GOOGLE_API_ORIGIN_OVERRIDE", "https://gmail.googleapis.com")
    monkeypatch.setenv("LIFEFLOW_ALLOW_LIVE_GOOGLE", "1")
    guard = block_live_google_network(httpx.MockTransport(_never_called))
    request = httpx.Request("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages")
    with pytest.raises(LiveNetworkAttemptError):
        await guard.handle_async_request(request)
    assert os.environ["GOOGLE_API_ORIGIN_OVERRIDE"] == "https://gmail.googleapis.com"


async def test_a_redirect_to_a_non_loopback_host_is_refused_on_the_second_hop() -> None:
    """A redirect response is not a way out: httpx issues the followed
    redirect as a second request through the same transport, so it is
    checked by the guard exactly like the first."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == "localhost":
            return httpx.Response(
                302, headers={"location": "https://accounts.google.com/o/oauth2/v2/auth"}
            )
        raise AssertionError("must never be reached — the redirect hop must be blocked first")

    guard = block_live_google_network(httpx.MockTransport(handle))
    async with httpx.AsyncClient(transport=guard, follow_redirects=True) as client:
        with pytest.raises(LiveNetworkAttemptError, match=re.escape("accounts.google.com")):
            await client.get("http://localhost:8010/connected-accounts/google/connect")


async def test_safety_net_catches_a_client_that_was_never_mocked() -> None:
    """Reproduces the exact shape of the original incident: `create_app()`
    wires `google_oauth_client`/`gmail_client`/`calendar_client` to one
    shared `google_http_client`. If a future edit to the rehearsal script
    forgets to override one of the three clients with a full local mock,
    that client falls back to `google_http_client` — which this test
    installs with a guarded *real* transport, exactly as
    `stage11a_phase4b_connection_rehearsal.py` now does before applying its
    per-cycle mocks. The forgotten client must be refused, not silently
    reach `gmail.googleapis.com` for real."""
    settings = Settings(
        _env_file=None,
        environment="development",
        log_level="WARNING",
        database_url="postgresql+asyncpg://lifeflow:lifeflow@localhost:5433/lifeflow_test",  # pragma: allowlist secret
        token_key=base64.b64encode(os.urandom(32)).decode(),
        token_key_id="guard-test-1",
        session_secret="g" * 32,
        google_oauth_enabled=True,
        google_oidc_client_id="oidc-id",
        google_oidc_client_secret="oidc-secret",  # pragma: allowlist secret
        google_oidc_redirect_uri="http://localhost:8010/auth/google/callback",
        google_connector_client_id="conn-id",
        google_connector_client_secret="conn-secret",  # pragma: allowlist secret
        google_connector_redirect_uri="http://localhost:8010/connected-accounts/google/callback",
    )
    app = create_app(settings)
    try:
        await app.state.google_http_client.aclose()
        app.state.google_http_client = httpx.AsyncClient(
            transport=block_live_google_network(httpx.AsyncHTTPTransport())
        )
        # Simulate the historical bug directly: `gmail_client` is left
        # exactly as `create_app()` built it, now backed by the guarded
        # client above instead of being overridden with a mock.
        from lifeflow_api.google.gmail_client import GmailDraftClient

        forgotten_client = GmailDraftClient(app.state.google_http_client)
        with pytest.raises(LiveNetworkAttemptError, match=re.escape("gmail.googleapis.com")):
            await forgotten_client.list_messages(
                access_token="fake",  # pragma: allowlist secret
                query="after:0 before:1",
                page_token=None,
                max_results=10,
            )
    finally:
        await app.state.google_http_client.aclose()


async def test_guard_closes_the_wrapped_transport() -> None:
    closed = False

    class _Wrapped(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise AssertionError("not exercised in this test")

        async def aclose(self) -> None:
            nonlocal closed
            closed = True

    guard = block_live_google_network(_Wrapped())
    await guard.aclose()
    assert closed is True
