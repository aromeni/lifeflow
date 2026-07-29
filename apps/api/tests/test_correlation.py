import uuid

from httpx import AsyncClient

from lifeflow_api.correlation import get_correlation_id, with_worker_correlation


async def test_correlation_id_is_generated_when_absent(client: AsyncClient) -> None:
    response = await client.get("/health")
    correlation_id = response.headers["X-Correlation-ID"]
    uuid.UUID(correlation_id)  # generated IDs are UUIDs


async def test_supplied_correlation_id_is_echoed(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Correlation-ID": "req-12345"})
    assert response.headers["X-Correlation-ID"] == "req-12345"


async def test_invalid_correlation_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Correlation-ID": "a" * 300})
    replaced = response.headers["X-Correlation-ID"]
    assert replaced != "a" * 300
    uuid.UUID(replaced)


async def test_worker_correlation_id_is_absent_outside_any_job_or_request() -> None:
    assert get_correlation_id() == "-"


async def test_with_worker_correlation_binds_a_real_id_for_the_call_duration() -> None:
    """Stage 9 Delivery Phase 5 (§15): a background job has no inbound HTTP
    request to take a correlation id from — `with_worker_correlation` is the
    ARQ-side analogue of `CorrelationIdMiddleware`, giving every job/cron
    invocation its own id for the duration of the call, then restoring the
    outer context exactly as the middleware does."""
    seen: dict[str, str] = {}

    @with_worker_correlation
    async def fake_job(ctx: dict[str, object]) -> str:
        seen["id"] = get_correlation_id()
        return seen["id"]

    assert get_correlation_id() == "-"
    result = await fake_job({})
    assert result == seen["id"]
    uuid.UUID(seen["id"])  # a real, valid, generated id — never the "-" default
    assert get_correlation_id() == "-"  # restored after the call


async def test_with_worker_correlation_gives_each_invocation_a_distinct_id() -> None:
    ids: list[str] = []

    @with_worker_correlation
    async def fake_job(ctx: dict[str, object]) -> None:
        ids.append(get_correlation_id())

    await fake_job({})
    await fake_job({})
    assert len(ids) == 2
    assert ids[0] != ids[1]


async def test_with_worker_correlation_resets_even_when_the_job_raises() -> None:
    @with_worker_correlation
    async def failing_job(ctx: dict[str, object]) -> None:
        raise RuntimeError("boom")

    try:
        await failing_job({})
    except RuntimeError:
        pass
    assert get_correlation_id() == "-"
