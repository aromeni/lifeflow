"""Correlation ID handling.

Every request carries a correlation ID: taken from the X-Correlation-ID header
when the caller supplies one, otherwise generated. The ID is stored in a
context variable so log records and error responses can include it, and is
always echoed back in the response header.
"""

import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

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
