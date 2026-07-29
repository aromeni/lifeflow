"""Stage 9 Delivery Phase 5: bounded retry-with-backoff for safe reads only.
`sleep`/`rand` are injected everywhere so these tests run instantly and
deterministically — no real waiting, no flakiness from actual jitter."""

import pytest

from lifeflow_api.retry import DEFAULT_MAX_ATTEMPTS, parse_retry_after_seconds, retry_read


class _FakeClock:
    def __init__(self) -> None:
        self.sleeps: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def _always_retryable(_exc: BaseException) -> bool:
    return True


def _never_retryable(_exc: BaseException) -> bool:
    return False


async def test_succeeds_on_first_attempt_without_sleeping() -> None:
    clock = _FakeClock()

    async def fn() -> str:
        return "ok"

    result = await retry_read(fn, is_retryable=_always_retryable, sleep=clock.sleep)
    assert result == "ok"
    assert clock.sleeps == []


async def test_retries_a_transient_failure_then_succeeds() -> None:
    clock = _FakeClock()
    attempts = {"count": 0}

    async def fn() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionError("transient")
        return "recovered"

    result = await retry_read(
        fn, is_retryable=_always_retryable, max_attempts=5, sleep=clock.sleep, rand=lambda: 0.0
    )
    assert result == "recovered"
    assert attempts["count"] == 3
    assert len(clock.sleeps) == 2


async def test_non_retryable_failure_propagates_immediately_no_sleep() -> None:
    clock = _FakeClock()
    attempts = {"count": 0}

    async def fn() -> str:
        attempts["count"] += 1
        raise ValueError("permanent")

    with pytest.raises(ValueError, match="permanent"):
        await retry_read(fn, is_retryable=_never_retryable, sleep=clock.sleep)
    assert attempts["count"] == 1
    assert clock.sleeps == []


async def test_retry_count_is_bounded_by_max_attempts() -> None:
    clock = _FakeClock()
    attempts = {"count": 0}

    async def fn() -> str:
        attempts["count"] += 1
        raise ConnectionError("always fails")

    with pytest.raises(ConnectionError, match="always fails"):
        await retry_read(
            fn, is_retryable=_always_retryable, max_attempts=3, sleep=clock.sleep, rand=lambda: 0.0
        )
    assert attempts["count"] == 3
    assert len(clock.sleeps) == 2  # sleeps between attempts, never after the last one


async def test_default_max_attempts_is_a_small_bounded_number() -> None:
    assert 1 < DEFAULT_MAX_ATTEMPTS <= 5


async def test_backoff_grows_and_stays_within_validated_bounds_with_jitter() -> None:
    clock = _FakeClock()
    attempts = {"count": 0}

    async def fn() -> str:
        attempts["count"] += 1
        raise ConnectionError("always fails")

    with pytest.raises(ConnectionError):
        await retry_read(
            fn,
            is_retryable=_always_retryable,
            max_attempts=4,
            base_delay_seconds=1.0,
            max_delay_seconds=8.0,
            budget_seconds=1000.0,
            sleep=clock.sleep,
            rand=lambda: 1.0,  # maximum jitter multiplier (1.5x)
        )
    # base delays before jitter: 1, 2, 4 (capped at 8); jitter multiplies by
    # up to 1.5x and the result is re-clamped to max_delay_seconds.
    assert clock.sleeps == [1.5, 3.0, 6.0]
    assert all(delay <= 8.0 for delay in clock.sleeps)


async def test_retry_after_is_honoured_as_a_floor_for_the_next_delay() -> None:
    clock = _FakeClock()
    attempts = {"count": 0}

    async def fn() -> str:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise ConnectionError("rate limited")
        return "ok"

    result = await retry_read(
        fn,
        is_retryable=_always_retryable,
        base_delay_seconds=0.1,
        max_delay_seconds=30.0,
        retry_after_seconds=20.0,
        sleep=clock.sleep,
        rand=lambda: 0.0,
    )
    assert result == "ok"
    assert clock.sleeps == [20.0]


async def test_malformed_retry_after_header_is_ignored_safely() -> None:
    assert parse_retry_after_seconds("not-a-number") is None
    assert parse_retry_after_seconds(None) is None
    assert parse_retry_after_seconds("-5") is None
    assert parse_retry_after_seconds("Wed, 21 Oct 2026 07:28:00 GMT") is None


async def test_well_formed_retry_after_header_parses_to_seconds() -> None:
    assert parse_retry_after_seconds("30") == 30.0
    assert parse_retry_after_seconds("0") == 0.0


async def test_total_elapsed_time_budget_stops_retrying_before_max_attempts() -> None:
    clock = _FakeClock()
    attempts = {"count": 0}

    async def fn() -> str:
        attempts["count"] += 1
        raise ConnectionError("always fails")

    with pytest.raises(ConnectionError):
        await retry_read(
            fn,
            is_retryable=_always_retryable,
            max_attempts=10,
            base_delay_seconds=5.0,
            max_delay_seconds=10.0,
            budget_seconds=6.0,
            sleep=clock.sleep,
            rand=lambda: 0.0,
        )
    # rand=0.0 -> jitter multiplier is the minimum, 0.5x. First delay
    # 5.0*0.5=2.5 fits the 6.0s budget; the next (10.0*0.5=5.0) would push
    # elapsed to 7.5 > 6.0, so retrying stops well short of max_attempts=10.
    assert attempts["count"] == 2
    assert clock.sleeps == [2.5]


async def test_exhaustion_reraises_the_original_exception_type_unwrapped() -> None:
    """Callers throughout this codebase pattern-match on a connector's own
    exception hierarchy (GoogleTransientError vs GoogleClientError, etc.) —
    a generic wrapper exception on exhaustion would silently break every
    one of those `except SpecificError:` clauses."""
    clock = _FakeClock()

    class _CustomTransientError(ConnectionError):
        pass

    async def fn() -> str:
        raise _CustomTransientError("root cause")

    with pytest.raises(_CustomTransientError, match="root cause"):
        await retry_read(
            fn, is_retryable=_always_retryable, max_attempts=2, sleep=clock.sleep, rand=lambda: 0.0
        )
