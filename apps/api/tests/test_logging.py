from lifeflow_api.logging_setup import redact


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
