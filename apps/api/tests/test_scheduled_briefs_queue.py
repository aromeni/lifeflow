"""Stage 8 Phase 2: real-Redis queue-level behaviour (ADR 0004 D48).

Queue uniqueness cannot be claimed from mocks alone — these tests run
against a real Redis (the compose `redis` service, localhost:6380).
Requires: `docker compose up -d redis --wait`.

`test_scheduled_briefs.py` covers everything the database owns (dispatch
planning, DST, catch-up, idempotent generation) with a fake Redis; this
file covers only what genuinely needs a live queue: arq's own `_job_id`
deduplication, and proof that job payloads are JSON (never pickle) and
contain nothing but a plain internal identifier.
"""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import redis.asyncio as aioredis
from arq import constants as arq_constants
from arq.connections import ArqRedis, RedisSettings, create_pool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL
from tests.test_scheduled_briefs import _enable_scheduling, _make_user

from lifeflow_api.scheduled_briefs import (
    JOB_FUNCTION_NAME,
    dispatch_tick,
    job_deserializer,
    job_id_for,
    job_serializer,
)

pytestmark = pytest.mark.integration

REDIS_HOST, REDIS_PORT = "localhost", 6380
REDIS_SETTINGS = RedisSettings(host=REDIS_HOST, port=REDIS_PORT)


@pytest.fixture
async def redis() -> AsyncIterator[ArqRedis]:
    try:
        pool = await create_pool(
            REDIS_SETTINGS, job_serializer=job_serializer, job_deserializer=job_deserializer
        )
    except OSError:
        pytest.skip("Redis is not running (docker compose up -d redis --wait)")
    await pool.flushdb()
    try:
        yield pool
    finally:
        await pool.flushdb()
        await pool.aclose()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


async def test_real_redis_deduplicates_a_repeated_job_id(redis: ArqRedis) -> None:
    job_id = job_id_for(uuid.uuid4(), datetime(2026, 7, 21, tzinfo=UTC).date(), 0)
    first = await redis.enqueue_job(JOB_FUNCTION_NAME, "run-id-placeholder", _job_id=job_id)
    second = await redis.enqueue_job(JOB_FUNCTION_NAME, "run-id-placeholder", _job_id=job_id)
    assert first is not None
    assert second is None  # arq's own unique-job-id guard, not a mock


async def test_dispatch_tick_enqueues_a_real_job_end_to_end(
    redis: ArqRedis, session: AsyncSession
) -> None:
    user = await _make_user(session)
    await _enable_scheduling(session, user.id, briefing_time="07:30")
    await session.commit()
    now = datetime(2026, 7, 21, 6, 30, tzinfo=UTC)

    result = await dispatch_tick(redis, session, now=now)
    assert result.enqueued == 1
    assert result.deduplicated == 0

    raw_client = aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}/0")
    try:
        job_id = job_id_for(user.id, now.date(), 0)
        raw = await raw_client.get(arq_constants.job_key_prefix + job_id)
        assert raw is not None
    finally:
        await raw_client.aclose()


async def test_job_payload_is_json_not_pickle_and_contains_only_the_run_id(
    redis: ArqRedis, session: AsyncSession
) -> None:
    """The queue never sees anything but a plain identifier: no email
    addresses, no brief content, no pickled objects (skill security
    requirement)."""
    user = await _make_user(session)
    await _enable_scheduling(session, user.id, briefing_time="07:30")
    await session.commit()
    now = datetime(2026, 7, 21, 6, 30, tzinfo=UTC)

    await dispatch_tick(redis, session, now=now)
    job_id = job_id_for(user.id, now.date(), 0)

    raw_client = aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}/0")
    try:
        raw_bytes = await raw_client.get(arq_constants.job_key_prefix + job_id)
        assert raw_bytes is not None
        # If this were pickle (arq's default), json.loads would raise.
        payload = json.loads(raw_bytes)
        assert payload["f"] == JOB_FUNCTION_NAME
        assert len(payload["a"]) == 1
        assert isinstance(payload["a"][0], str)
        uuid.UUID(payload["a"][0])  # the sole argument is a bare run-id UUID string
        assert payload["k"] == {}
    finally:
        await raw_client.aclose()
