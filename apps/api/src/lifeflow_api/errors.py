"""Shared error response structure.

Every error leaving the API has the same shape:

    {"error": {"code": "...", "message": "...", "correlation_id": "..."}}

Unhandled exceptions are logged with their stack trace but return a generic
message — internals are never exposed to clients (guard rail: never expose
prompt or system internals; never silently ignore failures).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from lifeflow_api.correlation import get_correlation_id

logger = logging.getLogger(__name__)

# Stable machine-readable codes for the HTTP errors the API raises today.
_STATUS_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    503: "service_unavailable",
}


class ErrorBody(BaseModel):
    code: str
    message: str
    correlation_id: str
    # Present only on a 429 (Stage 9 Delivery Phase 4, ADR 0005 D64/D81) — a
    # bounded, non-negative number of seconds, never a raw bucket timestamp,
    # policy code, or subject digest.
    retry_after_seconds: int | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


def error_response(
    status_code: int, code: str, message: str, *, retry_after_seconds: int | None = None
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            correlation_id=get_correlation_id(),
            retry_after_seconds=retry_after_seconds,
        )
    )
    response = JSONResponse(status_code=status_code, content=body.model_dump())
    if retry_after_seconds is not None:
        response.headers["Retry-After"] = str(retry_after_seconds)
    return response


class RateLimitExceededError(Exception):
    """Raised by the rate-limit dependency (`rate_limit_deps.py`) when a
    bucket is exhausted. Carries only a registered policy code and a bounded
    retry-after value — never a subject, digest, or bucket state."""

    def __init__(self, policy_code: str, retry_after_seconds: int) -> None:
        super().__init__(policy_code)
        self.policy_code = policy_code
        self.retry_after_seconds = retry_after_seconds


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_exception_handler(
        request: Request, exc: RateLimitExceededError
    ) -> JSONResponse:
        return error_response(
            429,
            "rate_limited",
            "Too many requests. Try again later.",
            retry_after_seconds=exc.retry_after_seconds,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "error")
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(422, "validation_error", "Request validation failed.")

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
        return error_response(500, "internal_error", "An internal error occurred.")
