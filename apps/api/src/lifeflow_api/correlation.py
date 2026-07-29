"""Correlation ID handling.

Every request carries a correlation ID: taken from the X-Correlation-ID header
when the caller supplies one, otherwise generated. The ID is stored in a
context variable so log records and error responses can include it, and is
always echoed back in the response header.

Stage 9 Delivery Phase 5: the middleware above only covers HTTP-request-scoped
code — an ARQ job runs in its own task with no inbound request, so it never
had a correlation id in its logs before `with_worker_correlation` (below).
Every job/cron entry point in `worker_app.py` is decorated with it, so
`get_correlation_id()` returns a real, job-scoped id inside any function a
job calls (e.g. `scheduled_briefs.dispatch_tick`), not the `"-"` default."""

import functools
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CORRELATION_HEADER = "X-Correlation-ID"

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


def get_correlation_id() -> str:
    return _correlation_id.get()


def _is_valid(value: str) -> bool:
    # Bound the header to something log-safe: printable ASCII, reasonable length.
    return 0 < len(value) <= 128 and value.isascii() and value.isprintable()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        supplied = request.headers.get(CORRELATION_HEADER, "")
        correlation_id = supplied if _is_valid(supplied) else str(uuid.uuid4())
        token = _correlation_id.set(correlation_id)
        try:
            response = await call_next(request)
        finally:
            _correlation_id.reset(token)
        response.headers[CORRELATION_HEADER] = correlation_id
        return response


def with_worker_correlation[T](
    fn: Callable[..., Awaitable[T]],
) -> Callable[..., Awaitable[T]]:
    """Binds a fresh correlation id for the duration of one ARQ job/cron
    invocation, exactly like `CorrelationIdMiddleware` does for one HTTP
    request. A fresh id every call is correct here — unlike an inbound HTTP
    request, a job has no caller-supplied header to honour, and every
    invocation (including a retry-scheduled re-run) is its own traceable
    unit of work, distinguished from the last by this id, not by reusing
    one.

    Typed `Callable[..., Awaitable[T]]` rather than a `ParamSpec`
    (`Callable[P, Awaitable[T]]`) deliberately: arq's own `WorkerCoroutine`
    protocol (`async def __call__(self, ctx, *args: Any, **kwargs: Any)`)
    is itself untyped-variadic, and a `ParamSpec`-generic wrapper does not
    structurally satisfy that protocol under mypy strict the way this
    simpler, equally-accurate-here signature does."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        token = _correlation_id.set(str(uuid.uuid4()))
        try:
            return await fn(*args, **kwargs)
        finally:
            _correlation_id.reset(token)

    return wrapper


__all__ = [
    "CORRELATION_HEADER",
    "CorrelationIdMiddleware",
    "get_correlation_id",
    "with_worker_correlation",
]
