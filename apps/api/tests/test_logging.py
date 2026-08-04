import logging

from lifeflow_api.logging_setup import UvicornAccessQueryStringRedactor, configure_logging, redact


def test_authorization_header_is_redacted() -> None:
    assert "Bearer" not in redact("authorization: Bearer abc.def.ghi")


def test_tokens_and_secrets_are_redacted() -> None:
    message = "refresh_token=rt-123 client_secret: cs-456 api-key=ak-789 password=hunter2"
    result = redact(message)
    for leaked in ("rt-123", "cs-456", "ak-789", "hunter2"):
        assert leaked not in result


def test_ordinary_messages_are_untouched() -> None:
    message = "Sync completed: 38 new messages"
    assert redact(message) == message


# --- uvicorn.access OAuth query-string redaction (Stage 11A Phase 4D) ------
# Found during the live-connection leakage inspection: uvicorn's default
# access logger has `propagate=False`, so it bypasses `JsonFormatter`/
# `redact()` above entirely and writes the raw request line — including
# the OAuth callback's single-use `code`/`state` query parameters — to
# stdout in plaintext. These tests exercise the fix directly against the
# real 5-tuple shape uvicorn's own `AccessFormatter` uses.


def _access_record(full_path: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %s',
        args=("127.0.0.1:12345", "GET", full_path, "1.1", 302),
        exc_info=None,
    )


def test_oauth_signin_callback_query_string_is_redacted() -> None:
    record = _access_record("/auth/google/callback?code=real-auth-code&state=real-state-value")
    UvicornAccessQueryStringRedactor().filter(record)
    full_path = record.args[2]
    assert full_path == "/auth/google/callback?[REDACTED]"
    assert "real-auth-code" not in full_path
    assert "real-state-value" not in full_path


def test_oauth_connector_callback_query_string_is_redacted() -> None:
    record = _access_record(
        "/connected-accounts/google/callback?code=real-auth-code&state=real-state-value"
    )
    UvicornAccessQueryStringRedactor().filter(record)
    full_path = record.args[2]
    assert full_path == "/connected-accounts/google/callback?[REDACTED]"


def test_non_oauth_paths_are_left_untouched() -> None:
    record = _access_record("/today?refresh=true")
    UvicornAccessQueryStringRedactor().filter(record)
    assert record.args[2] == "/today?refresh=true"


def test_oauth_callback_without_query_string_is_left_untouched() -> None:
    record = _access_record("/auth/google/callback")
    UvicornAccessQueryStringRedactor().filter(record)
    assert record.args[2] == "/auth/google/callback"


def test_filter_always_returns_true_never_drops_the_record() -> None:
    record = _access_record("/auth/google/callback?code=x&state=y")
    assert UvicornAccessQueryStringRedactor().filter(record) is True


def test_configure_logging_registers_the_redactor_on_uvicorn_access() -> None:
    configure_logging("INFO")
    filters = logging.getLogger("uvicorn.access").filters
    assert any(isinstance(f, UvicornAccessQueryStringRedactor) for f in filters)
