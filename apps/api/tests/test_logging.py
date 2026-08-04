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
# stdout in plaintext.
#
# The first version of this fix redacted the entire query string, but only
# on an exact, case-sensitive match against the two known callback paths —
# a subsequent merge-integrity review found that would not have generalised
# to a differently-cased path, a denied-consent error redirect, or any
# future route carrying one of these keys. The filter below instead applies
# a closed sensitive-key vocabulary to every route's query string, redacting
# only matching keys and leaving unrelated parameters and paths untouched.
# These tests exercise it directly against the real 5-tuple shape uvicorn's
# own `AccessFormatter` uses.


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
    assert "real-auth-code" not in full_path
    assert "real-state-value" not in full_path
    assert full_path.startswith("/auth/google/callback?")


def test_oauth_connector_callback_query_string_is_redacted() -> None:
    record = _access_record(
        "/connected-accounts/google/callback?code=real-auth-code&state=real-state-value"
    )
    UvicornAccessQueryStringRedactor().filter(record)
    full_path = record.args[2]
    assert "real-auth-code" not in full_path
    assert "real-state-value" not in full_path


def test_denied_consent_error_redirect_state_is_also_redacted() -> None:
    """A denied/cancelled consent callback carries `error`/`state`, never
    `code` — the vocabulary is keyed, not tied to the code param alone."""
    record = _access_record(
        "/connected-accounts/google/callback?error=access_denied&state=real-state-value"
    )
    UvicornAccessQueryStringRedactor().filter(record)
    full_path = record.args[2]
    assert "real-state-value" not in full_path
    assert "error=access_denied" in full_path


def test_sensitive_keys_are_redacted_on_any_route_not_only_the_two_callbacks() -> None:
    """A closed sensitive-key vocabulary, not a path allow-list — a
    differently-cased or lookalike path must not fall through unredacted."""
    record = _access_record("/some/other/route?access_token=leaked-value&safe=1")
    UvicornAccessQueryStringRedactor().filter(record)
    full_path = record.args[2]
    assert "leaked-value" not in full_path
    assert "safe=1" in full_path


def test_sensitive_key_matching_is_case_insensitive() -> None:
    record = _access_record("/connected-accounts/google/callback?Code=real-code&STATE=real-state")
    UvicornAccessQueryStringRedactor().filter(record)
    full_path = record.args[2]
    assert "real-code" not in full_path
    assert "real-state" not in full_path


def test_percent_encoded_sensitive_key_name_is_still_matched() -> None:
    # "code" percent-encoded as "%63ode" — the key itself is decoded before
    # being compared against the vocabulary.
    record = _access_record("/connected-accounts/google/callback?%63ode=real-code&state=real-state")
    UvicornAccessQueryStringRedactor().filter(record)
    full_path = record.args[2]
    assert "real-code" not in full_path
    assert "real-state" not in full_path


def test_repeated_sensitive_keys_are_all_redacted() -> None:
    record = _access_record(
        "/connected-accounts/google/callback?code=first-code&code=second-code&state=real-state"
    )
    UvicornAccessQueryStringRedactor().filter(record)
    full_path = record.args[2]
    assert "first-code" not in full_path
    assert "second-code" not in full_path
    assert "real-state" not in full_path


def test_unrelated_safe_query_parameters_are_preserved() -> None:
    record = _access_record(
        "/connected-accounts/google/callback?code=real-code&state=real-state&utm_source=demo"
    )
    UvicornAccessQueryStringRedactor().filter(record)
    full_path = record.args[2]
    assert "utm_source=demo" in full_path
    assert "real-code" not in full_path


def test_non_oauth_paths_with_no_sensitive_keys_are_left_untouched() -> None:
    record = _access_record("/today?refresh=true")
    UvicornAccessQueryStringRedactor().filter(record)
    assert record.args[2] == "/today?refresh=true"


def test_oauth_callback_without_query_string_is_left_untouched() -> None:
    record = _access_record("/auth/google/callback")
    UvicornAccessQueryStringRedactor().filter(record)
    assert record.args[2] == "/auth/google/callback"


def test_malformed_query_string_is_redacted_wholesale_not_emitted_unfiltered() -> None:
    """Fail safe, not fall open: if the query string can't be parsed, the
    whole thing is redacted rather than passed through untouched."""
    record = _access_record("/connected-accounts/google/callback?%zz-not-percent-encoding")
    UvicornAccessQueryStringRedactor().filter(record)
    full_path = record.args[2]
    assert full_path == "/connected-accounts/google/callback?[REDACTED]"


def test_record_with_a_different_arg_shape_is_left_untouched() -> None:
    """A non-access-log record (or any record not matching uvicorn's exact
    5-tuple contract) must not be mutated or crash the filter."""
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="Application startup complete.",
        args=(),
        exc_info=None,
    )
    UvicornAccessQueryStringRedactor().filter(record)
    assert record.args == ()
    assert record.getMessage() == "Application startup complete."


def test_filter_always_returns_true_never_drops_the_record() -> None:
    record = _access_record("/auth/google/callback?code=x&state=y")
    assert UvicornAccessQueryStringRedactor().filter(record) is True


def test_filter_does_not_mutate_unrelated_record_fields() -> None:
    record = _access_record("/connected-accounts/google/callback?code=real-code&state=real-state")
    UvicornAccessQueryStringRedactor().filter(record)
    assert record.args[0] == "127.0.0.1:12345"
    assert record.args[1] == "GET"
    assert record.args[3] == "1.1"
    assert record.args[4] == 302


def test_configure_logging_registers_the_redactor_on_uvicorn_access() -> None:
    configure_logging("INFO")
    filters = logging.getLogger("uvicorn.access").filters
    assert any(isinstance(f, UvicornAccessQueryStringRedactor) for f in filters)


def test_end_to_end_formatted_access_line_contains_no_sentinel(capsys) -> None:  # type: ignore[no-untyped-def]
    """Drives a real uvicorn.access log call, through the real filter and
    the real AccessFormatter, and inspects the actual emitted line — not
    just the intermediate record.args state the tests above check."""
    import sys

    from uvicorn.logging import AccessFormatter

    logger = logging.getLogger("uvicorn.access")
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(AccessFormatter(use_colors=False))
    handler.addFilter(UvicornAccessQueryStringRedactor())
    logger.handlers = [handler]
    logger.propagate = False

    logger.info(
        '%s - "%s %s HTTP/%s" %s',
        "127.0.0.1:54321",
        "GET",
        "/connected-accounts/google/callback?code=sentinel-code&state=sentinel-state",
        "1.1",
        302,
    )
    emitted = capsys.readouterr().out
    assert "sentinel-code" not in emitted
    assert "sentinel-state" not in emitted
    assert "/connected-accounts/google/callback?" in emitted
