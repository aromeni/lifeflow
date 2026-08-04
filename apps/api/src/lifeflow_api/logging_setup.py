"""Structured JSON logging with correlation IDs and credential redaction.

Threat model T6: credentials, cookies, and authorisation material must never
reach the logs. The redaction filter is a defence-in-depth backstop — code
should never log those values in the first place.
"""

import json
import logging
import re
from datetime import UTC, datetime

from lifeflow_api.correlation import get_correlation_id

# Matches "authorization: Bearer xyz", "token=abc", "cookie: a=b", etc.
_SENSITIVE_PATTERN = re.compile(
    r"(?i)\b(authorization|cookie|set-cookie|access[_-]?token|refresh[_-]?token"
    r"|client[_-]?secret|api[_-]?key|password)\b\s*[:=]\s*\S+"
)


def redact(message: str) -> str:
    return _SENSITIVE_PATTERN.sub(r"\1=[REDACTED]", message)


_OAUTH_CALLBACK_PATHS = ("/auth/google/callback", "/connected-accounts/google/callback")


class UvicornAccessQueryStringRedactor(logging.Filter):
    """`uvicorn.access` writes straight to its own handler (uvicorn's
    default `LOGGING_CONFIG` sets `propagate=False` on it), so it never
    reaches `JsonFormatter`/`redact()` above — a real gap found during
    Stage 11A Phase 4D's live-connection leakage inspection: the OAuth
    callback's single-use `code` and `state` query parameters were
    reaching the terminal in plaintext via uvicorn's default access log.

    `record.args` for this logger is the fixed 5-tuple `(client_addr,
    method, full_path, http_version, status_code)`
    (`uvicorn.logging.AccessFormatter.formatMessage`); only `full_path`'s
    query string is redacted, and only for the two OAuth callback paths —
    every other route's access log line is left untouched.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) == 5:
            full_path = record.args[2]
            if isinstance(full_path, str) and "?" in full_path:
                path, _, _query = full_path.partition("?")
                if path in _OAUTH_CALLBACK_PATHS:
                    args = list(record.args)
                    args[2] = f"{path}?[REDACTED]"
                    record.args = tuple(args)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
            "correlation_id": get_correlation_id(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = record.exc_info[0].__name__
            payload["stack"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # uvicorn.access has propagate=False in uvicorn's own default logging
    # config, so it never reaches the root handler above — it needs its
    # own, separately-attached filter.
    logging.getLogger("uvicorn.access").addFilter(UvicornAccessQueryStringRedactor())
