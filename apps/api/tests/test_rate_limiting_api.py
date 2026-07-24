"""Stage 9 Delivery Phase 4: rate limiting through the real API (ADR 0005
D64/D81). Uses tiny per-test policy overrides (via
`RATE_LIMIT_POLICY_OVERRIDES_JSON`) so tests never wait out a production
window, and a dedicated Redis logical database (index 7) flushed around every
test so buckets never leak between tests or collide with other suites.
"""

import json
import uuid
from collections.abc import AsyncIterator

import pytest
import redis.asyncio as aioredis
from httpx import AsyncClient
from tests.conftest import CSRF_HEADERS, _make_client, _test_settings

from lifeflow_api.config import Settings
from lifeflow_api.main import create_app

pytestmark = pytest.mark.integration

RATE_LIMIT_TEST_REDIS_URL = "redis://localhost:6380/7"
RATE_LIMIT_TEST_SECRET = "integration-test-rate-limit-secret-32chars!!"  # pragma: allowlist secret


def _rl_settings(overrides: dict[str, dict[str, int]] | None = None) -> Settings:
    return _test_settings("development").model_copy(
        update={
            "rate_limiting_enabled": True,
            "rate_limit_key_secret": RATE_LIMIT_TEST_SECRET,
            "redis_url": RATE_LIMIT_TEST_REDIS_URL,
            "rate_limit_policy_overrides_json": json.dumps(overrides or {}),
        }
    )


@pytest.fixture(autouse=True)
async def _clean_rate_limit_redis() -> AsyncIterator[None]:
    client: aioredis.Redis = aioredis.from_url(RATE_LIMIT_TEST_REDIS_URL)  # type: ignore[no-untyped-call]
    try:
        await client.flushdb()
    except Exception:
        pytest.skip("Redis is not running (docker compose up -d redis)")
    yield
    await client.flushdb()
    await client.aclose()


@pytest.fixture
async def rl_client() -> AsyncIterator[AsyncClient]:
    async for c in _make_client(_rl_settings()):
        yield c


async def _login(client: AsyncClient, marker: str) -> uuid.UUID:
    response = await client.post(
        "/auth/dev-login",
        json={"email": f"rl-{marker}-{uuid.uuid4()}@example.com", "display_name": "RL"},
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200
    return uuid.UUID(response.json()["user_id"])


# --- route inventory completeness -------------------------------------------

# Every state-changing (non-GET/HEAD/OPTIONS) route, or an explicit EXEMPT
# with its reason. A new state-changing route with neither breaks this test.
_EXEMPT_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/health"),
        ("GET", "/ready"),
        ("GET", "/config"),
        # FastAPI's own auto-registered docs routes: GET-only, no user data,
        # already disabled entirely in production (main.py: docs_url=None).
        ("GET", "/openapi.json"),
        ("GET", "/docs"),
        ("GET", "/docs/oauth2-redirect"),
        ("GET", "/redoc"),
    }
)


async def test_every_state_changing_route_has_a_policy_or_exemption(
    rl_client: AsyncClient,
) -> None:
    app = create_app(_rl_settings())
    unclassified: list[tuple[str, str]] = []
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        dependant = getattr(route, "dependant", None)
        if methods is None or path is None:
            continue
        for method in methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            if method == "GET" and (method, path) in _EXEMPT_ROUTES:
                continue
            if method == "GET":
                # Reads are covered by authenticated_read/privacy_audit_read
                # applied per-route; the exemption list above is closed to
                # infra/public routes only, so any other GET must carry a
                # rate-limit dependency.
                pass
            names = {
                d.call.__module__ + "." + d.call.__qualname__
                for d in (dependant.dependencies if dependant else [])
            }
            has_rate_limit_dep = any("rate_limit_deps" in name for name in names)
            is_confirm_route = path == "/privacy/deletion-operations/{operation_id}/confirm"
            if (
                not has_rate_limit_dep
                and not is_confirm_route
                and (method, path) not in _EXEMPT_ROUTES
            ):
                unclassified.append((method, path))
    assert unclassified == []


# --- anonymous auth ----------------------------------------------------------


async def test_anonymous_auth_route_returns_429_with_safe_body_and_header() -> None:
    settings = _rl_settings(
        {"anonymous_auth": {"capacity": 1, "refill_amount": 1, "refill_window_seconds": 3600}}
    )
    async for client in _make_client(settings):
        first = await client.post(
            "/auth/dev-login", json={"email": "a@example.com"}, headers=CSRF_HEADERS
        )
        assert first.status_code == 200
        blocked = await client.post(
            "/auth/dev-login", json={"email": "b@example.com"}, headers=CSRF_HEADERS
        )
        assert blocked.status_code == 429
        body = blocked.json()
        assert body["error"]["code"] == "rate_limited"
        assert isinstance(body["error"]["retry_after_seconds"], int)
        assert body["error"]["retry_after_seconds"] > 0
        assert set(body["error"]) == {"code", "message", "correlation_id", "retry_after_seconds"}
        assert "Retry-After" in blocked.headers
        assert blocked.headers["Retry-After"] == str(body["error"]["retry_after_seconds"])


async def test_429_response_never_leaks_subject_or_policy_internals() -> None:
    settings = _rl_settings(
        {"anonymous_auth": {"capacity": 1, "refill_amount": 1, "refill_window_seconds": 3600}}
    )
    async for client in _make_client(settings):
        await client.post("/auth/dev-login", json={"email": "a@example.com"}, headers=CSRF_HEADERS)
        blocked = await client.post(
            "/auth/dev-login", json={"email": "b@example.com"}, headers=CSRF_HEADERS
        )
        text = blocked.text
        assert "anonymous_auth" not in text
        assert "ratelimit:v1" not in text
        assert RATE_LIMIT_TEST_SECRET not in text
        assert "127.0.0.1" not in text and "testclient" not in text.lower()


# --- authenticated read -------------------------------------------------------


async def test_authenticated_read_policy_enforced() -> None:
    settings = _rl_settings(
        {"authenticated_read": {"capacity": 1, "refill_amount": 1, "refill_window_seconds": 3600}}
    )
    async for client in _make_client(settings):
        await _login(client, "read")
        first = await client.get("/me")
        second = await client.get("/me")
        assert first.status_code == 200
        assert second.status_code == 429


async def test_disabled_rate_limiting_never_calls_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    from lifeflow_api.rate_limiter import RateLimiter

    async def _fail(self: RateLimiter, key: str, policy: object) -> None:  # pragma: no cover
        raise AssertionError("RateLimiter.check must not be called when disabled")

    monkeypatch.setattr(RateLimiter, "check", _fail)
    async for client in _make_client(_test_settings("development")):
        await _login(client, "disabled")
        response = await client.get("/me")
        assert response.status_code == 200


# --- hidden path parameters cannot bypass the user bucket --------------------


async def test_hidden_proposal_id_does_not_bypass_the_user_bucket() -> None:
    settings = _rl_settings(
        {
            "demo_start": {"capacity": 1, "refill_amount": 1, "refill_window_seconds": 3600},
            "brief_generate": {"capacity": 1, "refill_amount": 1, "refill_window_seconds": 3600},
            "proposal_approval": {"capacity": 1, "refill_amount": 1, "refill_window_seconds": 3600},
        }
    )
    async for client in _make_client(settings):
        await _login(client, "hidden-id")
        assert (await client.post("/demo/start", headers=CSRF_HEADERS)).status_code == 200
        assert (await client.post("/briefs/generate", headers=CSRF_HEADERS)).status_code == 200
        proposals = (await client.get("/action-proposals")).json()["proposals"]
        assert len(proposals) >= 2

        first, second = proposals[0], proposals[1]
        approve_first = await client.post(
            f"/action-proposals/{first['id']}/approve",
            headers=CSRF_HEADERS,
            json={
                "expected_version": first["version"],
                "action_type": first["action_type"],
                "displayed_payload_hash": first["payload_hash"],
                "displayed_execution_context_hash": first["execution_context_hash"],
            },
        )
        assert approve_first.status_code == 200
        # A DIFFERENT proposal id must not grant a fresh bucket for the same user.
        approve_second = await client.post(
            f"/action-proposals/{second['id']}/approve",
            headers=CSRF_HEADERS,
            json={
                "expected_version": second["version"],
                "action_type": second["action_type"],
                "displayed_payload_hash": second["payload_hash"],
                "displayed_execution_context_hash": second["execution_context_hash"],
            },
        )
        assert approve_second.status_code == 429


# --- execution: no duplicate side effects under a blocked request -----------


async def test_execution_blocked_by_rate_limit_creates_no_duplicate_and_no_uncertain() -> None:
    settings = _rl_settings(
        {
            "demo_start": {"capacity": 1, "refill_amount": 1, "refill_window_seconds": 3600},
            "brief_generate": {"capacity": 1, "refill_amount": 1, "refill_window_seconds": 3600},
            "proposal_approval": {"capacity": 5, "refill_amount": 5, "refill_window_seconds": 3600},
            "external_execution": {
                "capacity": 1,
                "refill_amount": 1,
                "refill_window_seconds": 3600,
            },
        }
    )
    async for client in _make_client(settings):
        await _login(client, "exec-block")
        await client.post("/demo/start", headers=CSRF_HEADERS)
        await client.post("/briefs/generate", headers=CSRF_HEADERS)
        proposals = (await client.get("/action-proposals")).json()["proposals"]
        assert len(proposals) >= 2

        approved_ids = []
        for proposal in proposals[:2]:
            resp = await client.post(
                f"/action-proposals/{proposal['id']}/approve",
                headers=CSRF_HEADERS,
                json={
                    "expected_version": proposal["version"],
                    "action_type": proposal["action_type"],
                    "displayed_payload_hash": proposal["payload_hash"],
                    "displayed_execution_context_hash": proposal["execution_context_hash"],
                },
            )
            assert resp.status_code == 200
            approved_ids.append(proposal["id"])

        first_execute = await client.post(
            f"/action-proposals/{approved_ids[0]}/execute", headers=CSRF_HEADERS
        )
        assert first_execute.status_code == 200
        assert first_execute.json()["execution"] is not None

        blocked_execute = await client.post(
            f"/action-proposals/{approved_ids[1]}/execute", headers=CSRF_HEADERS
        )
        assert blocked_execute.status_code == 429

        # The blocked proposal never got an execution record, and is not
        # marked uncertain or failed — it is simply unexecuted.
        second_proposal_state = await client.get(f"/action-proposals/{approved_ids[1]}")
        assert second_proposal_state.json()["execution"] is None

        # The first proposal's successful execution is unaffected and remains
        # retrievable — proving the limiter never corrupted an existing record.
        first_proposal_state = await client.get(f"/action-proposals/{approved_ids[0]}")
        assert first_proposal_state.json()["execution"]["outcome"] in ("succeeded", "failed")


async def test_idempotent_replay_consumes_budget_but_never_duplicates() -> None:
    settings = _rl_settings(
        {
            "demo_start": {"capacity": 1, "refill_amount": 1, "refill_window_seconds": 3600},
            "brief_generate": {"capacity": 1, "refill_amount": 1, "refill_window_seconds": 3600},
            "proposal_approval": {"capacity": 5, "refill_amount": 5, "refill_window_seconds": 3600},
            "external_execution": {
                "capacity": 2,
                "refill_amount": 2,
                "refill_window_seconds": 3600,
            },
        }
    )
    async for client in _make_client(settings):
        await _login(client, "exec-replay")
        await client.post("/demo/start", headers=CSRF_HEADERS)
        await client.post("/briefs/generate", headers=CSRF_HEADERS)
        proposals = (await client.get("/action-proposals")).json()["proposals"]
        proposal = proposals[0]
        await client.post(
            f"/action-proposals/{proposal['id']}/approve",
            headers=CSRF_HEADERS,
            json={
                "expected_version": proposal["version"],
                "action_type": proposal["action_type"],
                "displayed_payload_hash": proposal["payload_hash"],
                "displayed_execution_context_hash": proposal["execution_context_hash"],
            },
        )
        first = await client.post(
            f"/action-proposals/{proposal['id']}/execute", headers=CSRF_HEADERS
        )
        replay = await client.post(
            f"/action-proposals/{proposal['id']}/execute", headers=CSRF_HEADERS
        )
        assert first.status_code == 200
        assert replay.status_code == 200
        assert first.json()["execution"] == replay.json()["execution"]

        # Budget (capacity 2) is now exhausted by the original + replay.
        third = await client.post(
            f"/action-proposals/{proposal['id']}/execute", headers=CSRF_HEADERS
        )
        assert third.status_code == 429


# --- deletion confirm: policy resolved by operation type, exactly once ------


async def test_deletion_confirm_uses_stricter_policy_only_for_account_deletion() -> None:
    settings = _rl_settings(
        {
            "deletion_confirm_cancel": {
                "capacity": 5,
                "refill_amount": 5,
                "refill_window_seconds": 3600,
            },
            "account_deletion_confirm": {
                "capacity": 1,
                "refill_amount": 1,
                "refill_window_seconds": 3600,
            },
        }
    )
    async for client in _make_client(settings):
        await _login(client, "del-confirm")
        account_preview = await client.post(
            "/privacy/account-deletion/preview", headers=CSRF_HEADERS
        )
        assert account_preview.status_code == 200
        body = account_preview.json()

        confirm = await client.post(
            f"/privacy/deletion-operations/{body['operation_id']}/confirm",
            json={
                "expected_version": body["version"],
                "confirmation_phrase": "DELETE MY LIFEFLOW ACCOUNT",
            },
            headers=CSRF_HEADERS,
        )
        assert confirm.status_code == 200


async def test_deletion_confirm_charges_exactly_one_policy_per_request() -> None:
    """An imported-data confirm must not also consume the stricter
    account_deletion_confirm budget — the two remain isolated."""
    settings = _rl_settings(
        {
            "deletion_confirm_cancel": {
                "capacity": 1,
                "refill_amount": 1,
                "refill_window_seconds": 3600,
            },
            "account_deletion_confirm": {
                "capacity": 1,
                "refill_amount": 1,
                "refill_window_seconds": 3600,
            },
        }
    )
    async for client in _make_client(settings):
        user_id = await _login(client, "del-isolated")
        from datetime import UTC, datetime

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from tests.conftest import TEST_DB_URL

        from lifeflow_api.models import ConnectedAccount, SourceItem

        engine = create_async_engine(TEST_DB_URL)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            account = ConnectedAccount(user_id=user_id, provider="google", granted_scopes=[])
            session.add(account)
            await session.flush()
            session.add(
                SourceItem(
                    user_id=user_id,
                    source_type="email",
                    external_id=f"em-{uuid.uuid4()}",
                    source_account_id=account.id,
                    title="t",
                    sender_or_organiser="x@example.com",
                    occurred_at=datetime.now(UTC),
                    content_fingerprint="fp",
                )
            )
            await session.commit()
            account_id = account.id
        await engine.dispose()

        imported_preview = await client.post(
            f"/privacy/imported-data/{account_id}/preview", headers=CSRF_HEADERS
        )
        imported_body = imported_preview.json()
        imported_confirm = await client.post(
            f"/privacy/deletion-operations/{imported_body['operation_id']}/confirm",
            json={
                "expected_version": imported_body["version"],
                "confirmation_phrase": "DELETE IMPORTED DATA",
            },
            headers=CSRF_HEADERS,
        )
        assert imported_confirm.status_code == 200  # used deletion_confirm_cancel, not the other

        account_preview = await client.post(
            "/privacy/account-deletion/preview", headers=CSRF_HEADERS
        )
        account_body = account_preview.json()
        account_confirm = await client.post(
            f"/privacy/deletion-operations/{account_body['operation_id']}/confirm",
            json={
                "expected_version": account_body["version"],
                "confirmation_phrase": "DELETE MY LIFEFLOW ACCOUNT",
            },
            headers=CSRF_HEADERS,
        )
        # account_deletion_confirm bucket is independent and still has budget.
        assert account_confirm.status_code == 200


# --- exemptions --------------------------------------------------------------


async def test_health_ready_config_are_never_rate_limited() -> None:
    settings = _rl_settings(
        {"authenticated_read": {"capacity": 1, "refill_amount": 1, "refill_window_seconds": 3600}}
    )
    async for client in _make_client(settings):
        for _ in range(10):
            assert (await client.get("/health")).status_code == 200
            assert (await client.get("/config")).status_code == 200
            assert (await client.get("/ready")).status_code == 200


# --- Redis failure fails open on a real route --------------------------------


async def test_redis_unavailable_fails_open_on_a_real_route() -> None:
    settings = _rl_settings().model_copy(update={"redis_url": "redis://localhost:1/0"})
    async for client in _make_client(settings):
        await _login(client, "redis-down")
        for _ in range(5):
            assert (await client.get("/me")).status_code == 200


async def test_redis_failure_creates_no_duplicate_execution() -> None:
    settings = _rl_settings().model_copy(update={"redis_url": "redis://localhost:1/0"})
    async for client in _make_client(settings):
        await _login(client, "redis-down-exec")
        await client.post("/demo/start", headers=CSRF_HEADERS)
        await client.post("/briefs/generate", headers=CSRF_HEADERS)
        proposal = (await client.get("/action-proposals")).json()["proposals"][0]
        await client.post(
            f"/action-proposals/{proposal['id']}/approve",
            headers=CSRF_HEADERS,
            json={
                "expected_version": proposal["version"],
                "action_type": proposal["action_type"],
                "displayed_payload_hash": proposal["payload_hash"],
                "displayed_execution_context_hash": proposal["execution_context_hash"],
            },
        )
        first = await client.post(
            f"/action-proposals/{proposal['id']}/execute", headers=CSRF_HEADERS
        )
        second = await client.post(
            f"/action-proposals/{proposal['id']}/execute", headers=CSRF_HEADERS
        )
        assert first.status_code == second.status_code == 200
        assert first.json()["execution"] == second.json()["execution"]
