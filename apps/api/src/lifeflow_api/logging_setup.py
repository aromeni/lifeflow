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
