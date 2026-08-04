"""Structured JSON logging with correlation IDs and credential redaction.

Threat model T6: credentials, cookies, and authorisation material must never
reach the logs. The redaction filter is a defence-in-depth backstop — code
should never log those values in the first place.
"""

import json
import logging
import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, unquote, urlencode

from lifeflow_api.correlation import get_correlation_id

# Matches "authorization: Bearer xyz", "token=abc", "cookie: a=b", etc.
_SENSITIVE_PATTERN = re.compile(
    r"(?i)\b(authorization|cookie|set-cookie|access[_-]?token|refresh[_-]?token"
    r"|client[_-]?secret|api[_-]?key|password)\b\s*[:=]\s*\S+"
)


def redact(message: str) -> str:
    return _SENSITIVE_PATTERN.sub(r"\1=[REDACTED]", message)


# Closed vocabulary, matched case-insensitively after percent-decoding the
# key. Deliberately broader than "the two OAuth callback paths" (an earlier,
# narrower version of this filter matched by exact path instead — dropped
# because it would not have generalised to a differently-cased path, a
# denied-consent error redirect, or any future route that happens to carry
# one of these keys): every route's access log is checked, but only these
# keys are ever touched.
_SENSITIVE_QUERY_KEYS = frozenset(
    {
        "code",
        "state",
        "nonce",
        "id_token",
        "access_token",
        "refresh_token",
        "client_secret",
        "code_verifier",
        "session",
        "session_state",
    }
)


class UvicornAccessQueryStringRedactor(logging.Filter):
    """`uvicorn.access` writes straight to its own handler (uvicorn's
    default `LOGGING_CONFIG` sets `propagate=False` on it), so it never
    reaches `JsonFormatter`/`redact()` above — a real gap found during
    Stage 11A Phase 4D's live-connection leakage inspection: the OAuth
    callback's single-use `code` and `state` query parameters were
    reaching the terminal in plaintext via uvicorn's default access log.

    `record.args` for this logger is the fixed 5-tuple `(client_addr,
    method, full_path, http_version, status_code)`
    (`uvicorn.logging.AccessFormatter.formatMessage`). Every query
    parameter whose (percent-decoded, lower-cased) key is in
    `_SENSITIVE_QUERY_KEYS` has its value replaced; every other parameter,
    and every route with no query string at all, is left untouched. A
    query string that fails to parse is redacted wholesale rather than
    emitted unfiltered — failing safe, not falling open.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not (isinstance(record.args, tuple) and len(record.args) == 5):
            return True
        full_path = record.args[2]
        if not isinstance(full_path, str) or "?" not in full_path:
            return True
        path, _, query = full_path.partition("?")
        if not query:
            return True
        if "=" not in query:
            # Not shaped like key=value pairs at all (e.g. malformed
            # percent-encoding with no separator) — cannot be matched
            # against the vocabulary safely, so redact the whole thing
            # rather than risk emitting an unrecognised sensitive blob.
            self._set_full_path(record, f"{path}?[REDACTED]")
            return True
        try:
            pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=False)
        except ValueError:
            self._set_full_path(record, f"{path}?[REDACTED]")
            return True
        redacted_any = False
        safe_pairs: list[tuple[str, str]] = []
        for key, value in pairs:
            if unquote(key).lower() in _SENSITIVE_QUERY_KEYS:
                safe_pairs.append((key, "[REDACTED]"))
                redacted_any = True
            else:
                safe_pairs.append((key, value))
        if redacted_any:
            self._set_full_path(record, f"{path}?{urlencode(safe_pairs)}")
        return True

    @staticmethod
    def _set_full_path(record: logging.LogRecord, full_path: str) -> None:
        args = list(record.args)  # type: ignore[arg-type]
        args[2] = full_path
        record.args = tuple(args)


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
