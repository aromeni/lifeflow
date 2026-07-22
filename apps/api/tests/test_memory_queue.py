"""Stage 8 Phase 3: best-effort inference enqueue and failure isolation
(ADR 0004 D56).

`enqueue_recompute` carries only a user id, never draft content, and can never
fail the approval that triggers it: a down Redis returns False and self-heals
on the next recompute. The real-Redis case (skipped when Redis is unavailable)
proves the job payload is JSON, not pickle, and holds only the user id.
"""

import json
import uuid
from collections.abc import AsyncIterator

import pytest
import redis.asyncio as aioredis
import redis.exceptions as redis_exceptions
from arq import constants as arq_constants
from arq.connections import ArqRedis, RedisSettings, create_pool
from httpx import AsyncClient
from tests.conftest import CSRF_HEADERS

from lifeflow_api.memory_inference import (
    JOB_FUNCTION_NAME,
    enqueue_recompute,
    job_deserializer,
    job_serializer,
)

pytestmark = pytest.mark.integration

REDIS_HOST, REDIS_PORT = "localhost", 6380
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
REDIS_SETTINGS = RedisSettings(host=REDIS_HOST, port=REDIS_PORT)


@pytest.fixture
async def redis() -> AsyncIterator[ArqRedis]:
    try:
        pool = await create_pool(
            REDIS_SETTINGS, job_serializer=job_serializer, job_deserializer=job_deserializer
        )
    except (OSError, redis_exceptions.RedisError):
        pytest.skip("Redis is not running (docker compose up -d redis --wait)")
    await pool.flushdb()
    try:
        yield pool
    finally:
        await pool.flushdb()
        await pool.aclose()


async def test_enqueue_returns_false_when_redis_unavailable_and_never_raises() -> None:
    """The approval that calls this must never be broken by a down queue
    (failure isolation, tests 40/41). No exception escapes; it just returns
    False and the missed job self-heals on the next recompute."""
    # A port nothing listens on — connection refused, resolved quickly.
    result = await enqueue_recompute("redis://localhost:6399/0", uuid.uuid4())
    assert result is False


async def test_enqueue_puts_one_json_job_with_only_the_user_id(redis: ArqRedis) -> None:
    user_id = uuid.uuid4()
    ok = await enqueue_recompute(REDIS_URL, user_id)
    assert ok is True

    raw_client = aioredis.from_url(REDIS_URL)
    try:
        # arq assigns a random job id; find the single queued job.
        keys = await raw_client.keys(arq_constants.job_key_prefix + "*")
        assert len(keys) == 1
        raw_bytes = await raw_client.get(keys[0])
        assert raw_bytes is not None
        # If this were pickle (arq's default), json.loads would raise.
        payload = json.loads(raw_bytes)
        assert payload["f"] == JOB_FUNCTION_NAME
        assert payload["a"] == [str(user_id)]  # only the user id, nothing else
        assert payload["k"] == {}
    finally:
        await raw_client.aclose()


async def test_real_approval_path_enqueues_an_identifiers_only_recompute(
    redis: ArqRedis, dev_client: AsyncClient
) -> None:
    """The production trigger, end to end: enable inference, generate a real
    `create_gmail_draft` proposal, edit its sign-off and approve the exact
    edited proposal — all through the normal API — and confirm the approval
    path (not a manual call) enqueues an identifiers-only recompute job (ADR
    0004 D56). `redis` flushed the db; the app enqueues to the same instance."""
    login = await dev_client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
    assert login.status_code == 200
    user_id = login.json()["user_id"]
    assert (
        await dev_client.put(
            "/preferences/memory_inference_enabled",
            json={"value": {"enabled": True}},
            headers=CSRF_HEADERS,
        )
    ).status_code == 200
    assert (await dev_client.post("/demo/start", headers=CSRF_HEADERS)).status_code == 200
    assert (await dev_client.post("/briefs/generate", headers=CSRF_HEADERS)).status_code == 200

    proposals = (await dev_client.get("/action-proposals")).json()["proposals"]
    draft = next(p for p in proposals if p["action_type"] == "create_gmail_draft")

    # Edit the sign-off through the normal edit route (sets user_edited_at).
    payload = dict(draft["payload"])
    payload["body"] = payload["body"].rsplit("\n\n", 1)[0] + "\n\nKind regards"
    edited = await dev_client.patch(
        f"/action-proposals/{draft['id']}",
        headers=CSRF_HEADERS,
        json={
            "expected_version": draft["version"],
            "action_type": "create_gmail_draft",
            "payload": payload,
        },
    )
    assert edited.status_code == 200
    edited_body = edited.json()

    # Approve the exact edited proposal.
    approved = await dev_client.post(
        f"/action-proposals/{draft['id']}/approve",
        headers=CSRF_HEADERS,
        json={
            "expected_version": edited_body["version"],
            "action_type": "create_gmail_draft",
            "displayed_payload_hash": edited_body["payload_hash"],
            "displayed_execution_context_hash": edited_body["execution_context_hash"],
        },
    )
    assert approved.status_code == 200
    # No side effect executed by approval: still awaiting the user's execute.
    assert approved.json()["status"] == "approved"
    assert approved.json()["execution"] is None

    # The approval path enqueued exactly one identifiers-only recompute.
    raw_client = aioredis.from_url(REDIS_URL)
    try:
        keys = await raw_client.keys(arq_constants.job_key_prefix + "*")
        jobs = [json.loads(await raw_client.get(key)) for key in keys]
        recompute_jobs = [j for j in jobs if j["f"] == JOB_FUNCTION_NAME]
        assert len(recompute_jobs) == 1
        assert recompute_jobs[0]["a"] == [user_id]  # only the user id
        assert recompute_jobs[0]["k"] == {}
    finally:
        await raw_client.aclose()
