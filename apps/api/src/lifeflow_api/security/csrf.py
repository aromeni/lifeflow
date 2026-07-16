"""CSRF protection for the JSON API (threat model T7).

State-changing requests must carry the custom header `X-LifeFlow-CSRF: 1`.
Browsers will not attach custom headers to cross-site requests without a CORS
preflight (which we never grant to other origins), so a forged form or
cross-site fetch cannot pass this check. Combined with SameSite=Lax session
cookies this covers the classic CSRF vectors for a JSON-only API.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from lifeflow_api.errors import error_response

CSRF_HEADER = "X-LifeFlow-CSRF"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class CsrfProtectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method not in _SAFE_METHODS and request.headers.get(CSRF_HEADER) != "1":
            return error_response(
                403, "csrf_header_missing", f"State-changing requests require {CSRF_HEADER}: 1."
            )
        return await call_next(request)
