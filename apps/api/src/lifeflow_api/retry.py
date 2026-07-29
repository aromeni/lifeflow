"""Stage 9 Delivery Phase 5 — bounded retry with backoff and jitter, for
provably safe (idempotent-read) operations only.

Never wrap a write. Gmail draft creation, Calendar event insertion,
proposal execution, and account-deletion confirmation must never pass
through `retry_read` — an uncertain external write is a distinct, durable
outcome (`ExecutionOutcome.uncertain`, `action_proposal_service.py`), never
something to retry automatically. This module has no knowledge of writes at
all: it only ever calls `fn()` again after a retryable read failure.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY_SECONDS = 0.5
DEFAULT_MAX_DELAY_SECONDS = 8.0
DEFAULT_BUDGET_SECONDS = 20.0


def parse_retry_after_seconds(value: str | None) -> float | None:
    """Parses an HTTP `Retry-After` header value (seconds form only — the
    HTTP-date form is deliberately not supported, since none of this app's
    dependencies send it). Returns `None` for anything missing, malformed,
    or negative — a malformed value must never be trusted, only ignored."""
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    if seconds < 0:
        return None
    return seconds


async def retry_read[T](
    fn: Callable[[], Awaitable[T]],
    *,
    is_retryable: Callable[[BaseException], bool],
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
    max_delay_seconds: float = DEFAULT_MAX_DELAY_SECONDS,
    budget_seconds: float = DEFAULT_BUDGET_SECONDS,
    retry_after_seconds: float | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rand: Callable[[], float] = random.random,
) -> T:
    """Call `fn()` up to `max_attempts` times, total sleep time bounded by
    `budget_seconds` regardless of `max_attempts`.

    - The first exception for which `is_retryable(exc)` is False propagates
      immediately, no retry attempted.
    - Backoff is exponential (`base_delay_seconds * 2**(attempt-1)`, capped
      at `max_delay_seconds`) with full jitter in `[0.5x, 1.5x]` of that
      capped value, then re-clamped to `max_delay_seconds` so jitter can
      never push a delay past the configured ceiling.
    - `retry_after_seconds`, when given and non-negative, is honoured as a
      floor for the *next* delay only (e.g. a provider's parsed
      `Retry-After`) — still capped at `max_delay_seconds`. Pass the output
      of `parse_retry_after_seconds` here; a malformed header should
      already have become `None` before it reaches this function.
    - On exhaustion (attempt count or time budget), re-raises the *original*
      exception from the last attempt — never a wrapper type — so callers
      that pattern-match on a connector's specific exception hierarchy
      (e.g. `GoogleTransientError` vs `GoogleClientError` vs
      `GoogleHistoryExpiredError`) see the exact same exception type whether
      it happened on the first attempt or the last.
    """
    elapsed = 0.0
    attempt = 0
    last_exc: BaseException | None = None
    while attempt < max_attempts:
        attempt += 1
        try:
            return await fn()
        except Exception as exc:
            if not is_retryable(exc):
                raise
            last_exc = exc
            if attempt >= max_attempts:
                break
            delay = min(base_delay_seconds * (2 ** (attempt - 1)), max_delay_seconds)
            delay = min(delay * (0.5 + rand()), max_delay_seconds)
            if retry_after_seconds is not None and retry_after_seconds >= 0:
                delay = min(max(delay, retry_after_seconds), max_delay_seconds)
            if elapsed + delay > budget_seconds:
                break
            logger.warning(
                "retry.read_attempt_failed attempt=%s of %s delay_seconds=%.2f",
                attempt,
                max_attempts,
                delay,
            )
            await sleep(delay)
            elapsed += delay
    assert last_exc is not None  # noqa: S101 -- loop only exits this way after >=1 failure
    raise last_exc


__all__ = ["DEFAULT_MAX_ATTEMPTS", "parse_retry_after_seconds", "retry_read"]
