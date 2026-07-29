"""Stage 9 Delivery Phase 4 closure: a real-Uvicorn regression for the
trusted-proxy boundary (ADR 0005 D64/D81).

Every other rate-limiting test in this suite drives the app through
`httpx.ASGITransport`, which never runs Uvicorn's own `ProxyHeadersMiddleware`
— that is exactly why the manual smoke test (not any automated test) found
that Uvicorn's default `--forwarded-allow-ips` trusts X-Forwarded-For from any
loopback connection, silently overriding this application's own
`TRUSTED_PROXY_CIDRS` resolver. These tests close that gap by starting a real
`uv run uvicorn` subprocess, using the repository's canonical safe launch
flags, and driving it over a real TCP socket.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import socket
import subprocess
import tempfile
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import redis.asyncio as aioredis
from tests.conftest import TEST_DB_URL

pytestmark = pytest.mark.integration

API_DIR = Path(__file__).resolve().parents[1]
CSRF_HEADERS = {"X-LifeFlow-CSRF": "1"}
UVICORN_TEST_SECRET = "uvicorn-regression-rate-limit-secret-32ch"  # pragma: allowlist secret
STARTUP_TIMEOUT_SECONDS = 30.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextlib.asynccontextmanager
async def _run_uvicorn(
    *,
    trusted_proxy_cidrs: str,
    redis_db: int,
    anonymous_auth_overrides: dict[str, int],
) -> AsyncIterator[tuple[str, aioredis.Redis, Path]]:
    """Start a real uvicorn subprocess using the exact canonical safe launch
    command documented in `main.py`/`CLAUDE.md`/`README.md`
    (`--forwarded-allow-ips=""`), and yield `(base_url, redis_client,
    log_path)`. Only the process started here is ever signalled."""
    port = _free_port()
    redis_url = f"redis://localhost:6380/{redis_db}"
    log_file = tempfile.NamedTemporaryFile(
        prefix="uvicorn-rl-regression-", suffix=".log", delete=False
    )
    env = {
        **os.environ,
        "ENVIRONMENT": "development",
        "DATABASE_URL": TEST_DB_URL,
        "REDIS_URL": redis_url,
        "RATE_LIMITING_ENABLED": "true",
        "RATE_LIMIT_KEY_SECRET": UVICORN_TEST_SECRET,
        "RATE_LIMIT_POLICY_OVERRIDES_JSON": json.dumps(
            {"anonymous_auth": anonymous_auth_overrides}
        ),
        "TRUSTED_PROXY_CIDRS": trusted_proxy_cidrs,
        "GOOGLE_OAUTH_ENABLED": "false",
        "LLM_EXTRACTION_ENABLED": "false",
        "RETENTION_ENFORCEMENT_ENABLED": "false",
        "TOKEN_KEY": base64.b64encode(os.urandom(32)).decode(),
        "SESSION_SECRET": base64.b64encode(os.urandom(32)).decode(),
        "LOG_LEVEL": "INFO",
    }

    redis_client: aioredis.Redis = aioredis.from_url(redis_url)  # type: ignore[no-untyped-call]
    try:
        await redis_client.flushdb()
    except Exception:
        pytest.skip("Redis is not running (docker compose up -d redis)")

    # Fixed, non-shell argv against the repository's own `uv`/`uvicorn` — the
    # same pattern as scripts/smoke_phase2.py's Alembic subprocess call.
    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "--app-dir",
            "src",
            "lifeflow_api.main:app",
            "--port",
            str(port),
            "--forwarded-allow-ips=",
        ],
        cwd=API_DIR,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        ready = False
        async with httpx.AsyncClient(timeout=1.0) as probe:
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    log_file.flush()
                    tail = Path(log_file.name).read_text(errors="replace")[-4000:]
                    raise RuntimeError(
                        f"uvicorn exited early (code {proc.returncode}); log tail:\n{tail}"
                    )
                try:
                    resp = await probe.get(f"{base_url}/health")
                    if resp.status_code == 200:
                        ready = True
                        break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.25)
        if not ready:
            raise RuntimeError("uvicorn did not become ready within the startup timeout")
        yield base_url, redis_client, Path(log_file.name)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        assert proc.poll() is not None, "uvicorn subprocess did not terminate — orphan risk"
        await redis_client.flushdb()
        await redis_client.aclose()
        log_file.close()
        Path(log_file.name).unlink(missing_ok=True)


async def _dev_login(client: httpx.AsyncClient, *, xff: str | None) -> httpx.Response:
    headers = dict(CSRF_HEADERS)
    if xff is not None:
        headers["X-Forwarded-For"] = xff
    return await client.post(
        "/auth/dev-login",
        json={"email": f"uv-{uuid.uuid4()}@example.com"},
        headers=headers,
    )


async def test_real_uvicorn_ignores_spoofed_forwarded_for_from_untrusted_peer() -> None:
    """The exact manual-smoke-test regression: with TRUSTED_PROXY_CIDRS empty
    (the default — trust nothing) and the canonical `--forwarded-allow-ips=""`
    flag applied, a real Uvicorn process must never let a spoofed
    X-Forwarded-For grant a fresh rate-limit identity, and the real shared
    peer must hit 429 at exactly the configured capacity."""
    async with _run_uvicorn(
        trusted_proxy_cidrs="",
        redis_db=9,
        anonymous_auth_overrides={
            "capacity": 2,
            "refill_amount": 2,
            "refill_window_seconds": 3600,
        },
    ) as (base_url, redis_client, log_path):
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
            first = await _dev_login(client, xff=None)
            second = await _dev_login(client, xff="9.9.9.9")
            third = await _dev_login(client, xff="1.2.3.4")

        assert first.status_code == 200
        # Same shared bucket as `first` — the spoofed header never grants a
        # separate identity, because Uvicorn itself never rewrote the peer.
        assert second.status_code == 200
        # The real, shared peer (127.0.0.1) has now made 3 requests against a
        # capacity-2 bucket, regardless of the differing spoofed addresses.
        assert third.status_code == 429

        keys = await redis_client.keys("ratelimit:v1:anonymous_auth:*")
        assert len(keys) == 1, f"expected exactly one shared bucket, found {len(keys)}"

        parts: list[str] = []
        for key in keys:
            parts.append(str(key))
            parts.append(str(await redis_client.hgetall(key)))
        dumped = " ".join(parts)
        assert "9.9.9.9" not in dumped
        assert "1.2.3.4" not in dumped

        log_text = log_path.read_text(errors="replace")
        assert "9.9.9.9" not in log_text
        assert "1.2.3.4" not in log_text


async def test_real_uvicorn_trusted_proxy_chain_resolution() -> None:
    """With the immediate peer explicitly trusted, two different forwarded
    client addresses must draw from separate buckets, and a malformed or
    excessively long chain must safely fall back to the immediate peer rather
    than granting a fresh identity — exactly as `rate_limit_ip.py` documents.
    Uses a real Uvicorn process so Uvicorn's own header handling is exercised
    end to end, not just the application-level resolver in isolation."""
    async with _run_uvicorn(
        trusted_proxy_cidrs="127.0.0.1/32",
        redis_db=10,
        anonymous_auth_overrides={
            "capacity": 2,
            "refill_amount": 2,
            "refill_window_seconds": 3600,
        },
    ) as (base_url, redis_client, log_path):
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
            a1 = await _dev_login(client, xff="198.51.100.7")
            a2 = await _dev_login(client, xff="198.51.100.7")
            a3 = await _dev_login(client, xff="198.51.100.7")
            b1 = await _dev_login(client, xff="198.51.100.8")
            malformed1 = await _dev_login(client, xff="not-an-ip")
            excessive = await _dev_login(client, xff=",".join(f"10.0.0.{i}" for i in range(1, 12)))
            malformed2 = await _dev_login(client, xff="not-an-ip")

        # Bucket A: two different valid forwarded addresses stay isolated,
        # and the resolver still enforces the configured capacity (2) on A.
        assert a1.status_code == 200
        assert a2.status_code == 200
        assert a3.status_code == 429

        # Bucket B is a fresh, separate identity from bucket A.
        assert b1.status_code == 200

        # A malformed hop and an excessively long chain both fall back to the
        # trusted immediate peer's own bucket (documented resolver policy),
        # which is then independently enforced.
        assert malformed1.status_code == 200
        assert excessive.status_code == 200
        assert malformed2.status_code == 429

        keys = await redis_client.keys("ratelimit:v1:anonymous_auth:*")
        assert len(keys) == 3, (
            f"expected 3 isolated buckets (A, B, peer-fallback), found {len(keys)}"
        )

        parts: list[str] = []
        for key in keys:
            parts.append(str(key))
            parts.append(str(await redis_client.hgetall(key)))
        dumped = " ".join(parts)
        for leaked in ("198.51.100.7", "198.51.100.8", "not-an-ip"):
            assert leaked not in dumped

        log_text = log_path.read_text(errors="replace")
        for leaked in ("198.51.100.7", "198.51.100.8", "not-an-ip"):
            assert leaked not in log_text
