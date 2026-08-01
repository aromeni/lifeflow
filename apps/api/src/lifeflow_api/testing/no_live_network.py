"""No-live-network guard for Stage 11A Phase 4B readiness tooling.

Phase 4B's dry-run and rehearsal tools must never be able to reach a real
Google host, even if a future edit accidentally drops or misconfigures one
of their `httpx.MockTransport` fakes — exactly the mistake that let an
early, uncommitted draft of `stage11a_phase4b_connection_rehearsal.py` send
one real, unauthenticated GET to `gmail.googleapis.com` (see
`docs/evaluation/stage-11/owner-validation/phase-4b/dry-run-results.md`'s
exact-boundary classification). This module is the second, independent
layer that prevents a repeat: a transport wrapper that refuses any request
whose target host is not on an explicit loopback allowlist, raising before
the wrapped transport (real or mock) is ever invoked.

This is deliberately an allowlist of loopback hosts, not a blocklist of
known Google hostnames — it blocks every current and future non-loopback
host, not only the ones named in the governing instruction. It consults
only the outgoing request's own resolved host, never any setting or
environment variable, so no configuration value can silently exempt a
live Google origin.

Nothing under `lifeflow_api.testing` is imported by the production
application (see `testing/__init__.py`); this guard exists purely for
Phase 4B's own tooling and its regression tests. It must never be
installed on the real application's Google clients — the future,
separately-authorised real-provider connection runbook needs those
clients to reach the real hosts this guard blocks.
"""

from __future__ import annotations

import httpx

_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1"})

# Not consulted by the guard's own logic (which is allowlist-based and
# therefore already blocks these and any other non-loopback host) — kept
# here purely so regression tests can assert each host named in the
# governing instruction is in fact refused.
KNOWN_GOOGLE_HOSTS = frozenset(
    {
        "accounts.google.com",
        "oauth2.googleapis.com",
        "gmail.googleapis.com",
        "www.googleapis.com",
        "calendar.googleapis.com",
    }
)


class LiveNetworkAttemptError(RuntimeError):
    """Raised when Phase 4B tooling attempts to reach a non-loopback host."""


class NoLiveNetworkTransport(httpx.AsyncBaseTransport):
    """Wraps a transport (usually an `httpx.MockTransport`); refuses any
    request whose host is not loopback before the wrapped transport runs."""

    def __init__(self, wrapped: httpx.AsyncBaseTransport) -> None:
        self._wrapped = wrapped

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host not in _ALLOWED_HOSTS:
            raise LiveNetworkAttemptError(
                f"refusing outbound {request.method} request to non-loopback "
                f"host {host!r} ({request.url})"
            )
        return await self._wrapped.handle_async_request(request)

    async def aclose(self) -> None:
        await self._wrapped.aclose()


def block_live_google_network(wrapped: httpx.AsyncBaseTransport) -> NoLiveNetworkTransport:
    """Standard entry point Phase 4B tooling uses: wrap an existing
    transport (typically an `httpx.MockTransport`) with the loopback-only
    guard, so a request only ever reaches it if the host is loopback."""

    return NoLiveNetworkTransport(wrapped)
