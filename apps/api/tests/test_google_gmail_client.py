"""Stage 7: the narrow Gmail transport client (ADR 0003 D13).

`gmail.compose` permits sending (threat model T22) — these tests prove the
enforcement is at the transport level: the only HTTP call `create_draft` can
ever make is `POST /gmail/v1/users/me/drafts`, never `.../send`.
"""

import base64
import email.message
import email.policy

import httpx
import pytest

from lifeflow_api.google.errors import (
    GoogleAuthError,
    GoogleClientError,
    GoogleHistoryExpiredError,
    GoogleTransientError,
)
from lifeflow_api.google.gmail_client import GmailDraftClient
from lifeflow_api.metrics import REGISTRY, provider_timeouts_total


def _build_raw_message(
    *, to: str, subject: str, body: str, cte: str = "7bit", from_: str = "me@example.com"
) -> str:
    """Builds a `format=raw` draft response body the way Gmail actually
    would — via the stdlib's own MIME serialisation, not hand-written
    RFC822 text — so these tests exercise realistic encoded-word Unicode
    subjects, quoted-printable bodies, and CRLF line endings exactly as a
    real Gmail response contains them (Stage 7 focused remediation: a real
    sandbox account showed the previous echo-only verification never
    actually decoded a message this way)."""
    message = email.message.EmailMessage(policy=email.policy.default)
    message["From"] = from_
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body, cte=cte)
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


def _client(handler: httpx.MockTransport) -> GmailDraftClient:
    return GmailDraftClient(httpx.AsyncClient(transport=handler))


async def test_create_draft_calls_only_the_drafts_endpoint_never_send() -> None:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={"id": "draft-1", "message": {"id": "msg-1", "threadId": "thread-1"}},
        )

    client = _client(httpx.MockTransport(handle))
    result = await client.create_draft(
        access_token="token",
        to=["dana@example.com"],
        subject="Re: Quarterly review",
        body="Hi Dana",
        thread_id="thread-1",
    )

    assert len(calls) == 1
    assert calls[0].method == "POST"
    assert calls[0].url.path == "/gmail/v1/users/me/drafts"
    assert "send" not in calls[0].url.path
    assert result.draft_id == "draft-1"
    assert result.message_id == "msg-1"


async def test_get_draft_requests_the_correct_path_with_format_raw() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/gmail/v1/users/me/drafts/draft-1"
        assert request.url.params["format"] == "raw"
        raw = _build_raw_message(to="dana@example.com", subject="Hi", body="Hi Dana")
        return httpx.Response(
            200, json={"id": "draft-1", "message": {"id": "msg-1", "threadId": "t1", "raw": raw}}
        )

    client = _client(httpx.MockTransport(handle))
    content = await client.get_draft(access_token="token", draft_id="draft-1")
    assert content.draft_id == "draft-1"
    assert content.message_id == "msg-1"
    assert content.thread_id == "t1"


async def test_get_draft_normalises_display_names_and_multiple_recipients() -> None:
    raw = _build_raw_message(
        to='"Dana Lee" <dana@example.com> ,  second@example.com',
        subject="Re: Quarterly review",
        body="Hi Dana",
    )

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"id": "d1", "message": {"id": "m1", "threadId": "t1", "raw": raw}}
        )

    client = _client(httpx.MockTransport(handle))
    content = await client.get_draft(access_token="token", draft_id="d1")

    assert content.to == ("dana@example.com", "second@example.com")


async def test_get_draft_decodes_unicode_subject_and_quoted_printable_crlf_body() -> None:
    """Reproduces the real sandbox finding directly: a redacted, realistic
    Gmail `format=raw` response — RFC 2047-encoded Unicode subject,
    quoted-printable transfer encoding, CRLF line endings — must decode to
    exactly the approved plain-text content, not fail to match it."""
    approved_subject = "Re: Quarterly review — approved ✓"
    approved_body = "Hi Dana,\n\nI am reviewing it and will follow up.\n\nBest"
    raw = _build_raw_message(
        to="dana@example.com",
        subject=approved_subject,
        body=approved_body,
        cte="quoted-printable",
    )

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"id": "d1", "message": {"id": "m1", "threadId": "t1", "raw": raw}}
        )

    client = _client(httpx.MockTransport(handle))
    content = await client.get_draft(access_token="token", draft_id="d1")

    assert content.subject == approved_subject
    assert content.body == approved_body
    assert content.to == ("dana@example.com",)


async def test_get_draft_treats_header_lookup_as_case_insensitive() -> None:
    """`email.policy.default` header lookup is inherently case-insensitive
    — proves we rely on that rather than a hand-rolled, case-sensitive
    header scan (a real server or proxy may return any header casing)."""
    raw_bytes = (
        b"from: me@example.com\r\n"
        b"to: dana@example.com\r\n"
        b"subject: Hi\r\n"
        b"content-type: text/plain; charset=UTF-8\r\n"
        b"\r\n"
        b"Hi Dana"
    )
    raw = base64.urlsafe_b64encode(raw_bytes).decode("ascii")

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"id": "d1", "message": {"id": "m1", "threadId": "t1", "raw": raw}}
        )

    client = _client(httpx.MockTransport(handle))
    content = await client.get_draft(access_token="token", draft_id="d1")

    assert content.to == ("dana@example.com",)
    assert content.subject == "Hi"
    assert content.body == "Hi Dana"


async def test_list_messages_and_get_message_never_touch_write_paths() -> None:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "m1", "threadId": "t1"}]})
        return httpx.Response(
            200,
            json={
                "id": "m1",
                "threadId": "t1",
                "snippet": "hello",
                "internalDate": "1700000000000",
                "labelIds": ["INBOX"],
                "payload": {"headers": [{"name": "Subject", "value": "Hi"}]},
            },
        )

    client = _client(httpx.MockTransport(handle))
    summaries, _ = await client.list_messages(
        access_token="token", query="after:1 before:2", page_token=None, max_results=10
    )
    message = await client.get_message(access_token="token", message_id="m1")

    assert {c.url.path for c in calls} == {
        "/gmail/v1/users/me/messages",
        "/gmail/v1/users/me/messages/m1",
    }
    assert all(c.method == "GET" for c in calls)
    assert summaries[0].id == "m1"
    assert message.snippet == "hello"


async def test_history_expired_raises_typed_error_on_404() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    client = _client(httpx.MockTransport(handle))
    with pytest.raises(GoogleHistoryExpiredError):
        await client.list_history(access_token="token", start_history_id="1", page_token=None)


async def test_auth_error_classified_on_401_and_403() -> None:
    for status in (401, 403):

        def handle(request: httpx.Request, status: int = status) -> httpx.Response:
            return httpx.Response(status, json={})

        client = _client(httpx.MockTransport(handle))
        with pytest.raises(GoogleAuthError):
            await client.get_message(access_token="token", message_id="m1")


async def test_transient_error_classified_on_5xx_and_429() -> None:
    for status in (429, 500, 503):

        def handle(request: httpx.Request, status: int = status) -> httpx.Response:
            return httpx.Response(status, json={})

        client = _client(httpx.MockTransport(handle))
        with pytest.raises(GoogleTransientError):
            await client.get_message(access_token="token", message_id="m1")


async def test_other_client_error_carries_status_code() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={})

    client = _client(httpx.MockTransport(handle))
    with pytest.raises(GoogleClientError) as exc:
        await client.get_message(access_token="token", message_id="m1")
    assert exc.value.status_code == 400


async def test_get_current_history_id_is_a_single_fixed_read() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/gmail/v1/users/me/profile"
        return httpx.Response(200, json={"historyId": "999"})

    client = _client(httpx.MockTransport(handle))
    history_id = await client.get_current_history_id(access_token="token")
    assert history_id == "999"


def _requests_value(*, operation: str, outcome: str) -> float:
    return (
        REGISTRY.get_sample_value(
            "lifeflow_provider_requests_total",
            {"provider": "gmail", "operation": operation, "outcome": outcome},
        )
        or 0.0
    )


@pytest.mark.parametrize(
    ("operation", "call"),
    [
        (
            "list_messages",
            lambda client: client.list_messages(
                access_token="token", query="q", page_token=None, max_results=10
            ),
        ),
        ("get_message", lambda client: client.get_message(access_token="token", message_id="m1")),
        (
            "list_history",
            lambda client: client.list_history(
                access_token="token", start_history_id="1", page_token=None
            ),
        ),
        (
            "get_current_history_id",
            lambda client: client.get_current_history_id(access_token="token"),
        ),
    ],
)
async def test_every_registered_ingestion_read_emits_a_success_request_metric(
    operation: str, call: object
) -> None:
    """Stage 9 Delivery Phase 5 (§14/§18 item 36): the bulk ingestion read
    surface — previously uninstrumented — now emits the same
    `lifeflow_provider_requests_total{outcome="success"}` signal the
    write/verification paths already did."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "messages": [{"id": "m1", "threadId": "t1"}],
                "id": "m1",
                "threadId": "t1",
                "snippet": "",
                "internalDate": "1700000000000",
                "labelIds": [],
                "payload": {"headers": []},
                "history": [],
                "historyId": "1",
                "historyId_": None,
            },
        )

    client = _client(httpx.MockTransport(handle))
    before = _requests_value(operation=operation, outcome="success")

    await call(client)  # type: ignore[operator]

    after = _requests_value(operation=operation, outcome="success")
    assert after == before + 1


async def test_a_raw_transport_timeout_is_classified_as_the_timeout_outcome() -> None:
    """A timeout (no response ever received) must be distinguishable from an
    ordinary HTTP-level transient error (429/5xx) in the metrics, and must
    populate the dedicated timeout counter — never treated as evidence the
    request didn't happen (see `retry.py`/`timeouts.py` module docstrings)."""

    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("simulated timeout", request=request)

    client = _client(httpx.MockTransport(handle))
    before_outcome = _requests_value(operation="get_message", outcome="timeout")
    before_timeout_counter = (
        REGISTRY.get_sample_value(
            "lifeflow_provider_timeouts_total", {"provider": "gmail", "operation": "get_message"}
        )
        or 0.0
    )

    with pytest.raises(GoogleTransientError):
        await client.get_message(access_token="token", message_id="m1")

    assert _requests_value(operation="get_message", outcome="timeout") == before_outcome + 1
    after_timeout_counter = REGISTRY.get_sample_value(
        "lifeflow_provider_timeouts_total", {"provider": "gmail", "operation": "get_message"}
    )
    assert after_timeout_counter == before_timeout_counter + 1
    assert provider_timeouts_total is not None  # module import sanity


async def test_an_http_5xx_transient_error_does_not_increment_the_timeout_counter() -> None:
    """A real 5xx response is a transient error but was never a timeout —
    the two counters must not be conflated."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    client = _client(httpx.MockTransport(handle))
    before = (
        REGISTRY.get_sample_value(
            "lifeflow_provider_timeouts_total", {"provider": "gmail", "operation": "get_message"}
        )
        or 0.0
    )

    with pytest.raises(GoogleTransientError):
        await client.get_message(access_token="token", message_id="m1")

    after = REGISTRY.get_sample_value(
        "lifeflow_provider_timeouts_total", {"provider": "gmail", "operation": "get_message"}
    )
    assert after == before
