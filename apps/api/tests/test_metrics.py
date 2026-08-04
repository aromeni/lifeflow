"""Stage 9 Delivery Phase 5 (§14): bounded-cardinality operational metrics.
Every test constructs against `metrics.REGISTRY` directly (not the
prometheus_client global default) since that's what this module uses."""

import ast
import re
from pathlib import Path

import httpx
import pytest

from lifeflow_api.google.errors import (
    GoogleAuthError,
    GoogleClientError,
    GoogleHistoryExpiredError,
    GoogleSyncTokenExpiredError,
    GoogleTransientError,
    InvalidGrantError,
)
from lifeflow_api.metrics import (
    REGISTRY,
    observe_provider_call,
    provider_request_duration_seconds,
    provider_requests_total,
    provider_timeouts_total,
    render_latest,
    status_class,
    with_worker_metrics,
    worker_job_events_total,
)


def _provider_requests_value(**labels: str) -> float:
    return REGISTRY.get_sample_value("lifeflow_provider_requests_total", labels) or 0.0


def test_status_class_buckets_by_hundreds() -> None:
    assert status_class(200) == "2xx"
    assert status_class(201) == "2xx"
    assert status_class(404) == "4xx"
    assert status_class(429) == "4xx"
    assert status_class(503) == "5xx"


async def test_observe_provider_call_records_success() -> None:
    before = _provider_requests_value(provider="gmail", operation="test_success", outcome="success")

    async with observe_provider_call("gmail", "test_success"):
        pass

    after = _provider_requests_value(provider="gmail", operation="test_success", outcome="success")
    assert after == before + 1


@pytest.mark.parametrize(
    ("exc", "expected_outcome"),
    [
        (GoogleAuthError("rejected"), "auth_error"),
        (GoogleTransientError("HTTP 503"), "transient_error"),
        (GoogleClientError("bad request", status_code=400), "client_error"),
        (GoogleHistoryExpiredError("stale"), "history_expired"),
        (GoogleSyncTokenExpiredError("stale"), "sync_token_expired"),
        (InvalidGrantError("revoked"), "grant_invalid"),
        (ValueError("unexpected"), "unknown_error"),
    ],
)
async def test_observe_provider_call_classifies_each_outcome(
    exc: Exception, expected_outcome: str
) -> None:
    operation = f"test_{expected_outcome}"
    before = _provider_requests_value(
        provider="gmail", operation=operation, outcome=expected_outcome
    )

    with pytest.raises(type(exc)):
        async with observe_provider_call("gmail", operation):
            raise exc

    after = _provider_requests_value(
        provider="gmail", operation=operation, outcome=expected_outcome
    )
    assert after == before + 1


async def test_observe_provider_call_records_latency() -> None:
    sample_count_before = (
        REGISTRY.get_sample_value(
            "lifeflow_provider_request_duration_seconds_count",
            {"provider": "gmail", "operation": "test_latency"},
        )
        or 0.0
    )

    async with observe_provider_call("gmail", "test_latency"):
        pass

    sample_count_after = REGISTRY.get_sample_value(
        "lifeflow_provider_request_duration_seconds_count",
        {"provider": "gmail", "operation": "test_latency"},
    )
    assert sample_count_after == sample_count_before + 1
    assert provider_request_duration_seconds is not None  # module import sanity


async def test_with_worker_metrics_records_succeeded() -> None:
    @with_worker_metrics("test_job_ok")
    async def fake_job() -> str:
        return "done"

    before = (
        REGISTRY.get_sample_value(
            "lifeflow_worker_job_events_total", {"job": "test_job_ok", "outcome": "succeeded"}
        )
        or 0.0
    )

    result = await fake_job()

    after = REGISTRY.get_sample_value(
        "lifeflow_worker_job_events_total", {"job": "test_job_ok", "outcome": "succeeded"}
    )
    assert result == "done"
    assert after == before + 1


async def test_with_worker_metrics_records_failed_and_reraises() -> None:
    @with_worker_metrics("test_job_fail")
    async def failing_job() -> None:
        raise RuntimeError("boom")

    before = (
        REGISTRY.get_sample_value(
            "lifeflow_worker_job_events_total", {"job": "test_job_fail", "outcome": "failed"}
        )
        or 0.0
    )

    with pytest.raises(RuntimeError, match="boom"):
        await failing_job()

    after = REGISTRY.get_sample_value(
        "lifeflow_worker_job_events_total", {"job": "test_job_fail", "outcome": "failed"}
    )
    assert after == before + 1


def test_render_latest_produces_prometheus_text_exposition_format() -> None:
    body, content_type = render_latest()
    text = body.decode("utf-8")
    assert "text/plain" in content_type
    assert "lifeflow_provider_requests_total" in text
    assert "lifeflow_worker_job_events_total" in text


def test_metric_label_registries_are_closed_and_bounded() -> None:
    """A defensive regression check: every metric this module defines has a
    small, fixed label set, never something that could grow per-user or
    per-request (threat model T6 — unbounded cardinality is itself a
    privacy/ops risk, not just a style preference)."""
    for metric in worker_job_events_total, provider_requests_total, provider_timeouts_total:
        # prometheus_client stores label names on the private `_labelnames`
        # attribute; asserting on it directly proves the label set is fixed
        # at definition time, not computed per-call from arbitrary data.
        assert all(isinstance(name, str) for name in metric._labelnames)
        assert len(metric._labelnames) <= 3


async def test_a_transport_timeout_increments_the_dedicated_timeout_counter_once() -> None:
    """A `GoogleTransientError` caused by an `httpx.TimeoutException` (the
    `raise ... from exc` pattern every Google client's `_get`/`_post` helper
    uses) is the one outcome that also bumps `provider_timeouts_total` — a
    deliberate, documented second counter, not an accidental double count of
    `provider_requests_total` itself (see `observe_provider_call`'s
    docstring)."""
    before_outcome = _provider_requests_value(
        provider="gmail", operation="test_timeout", outcome="timeout"
    )
    before_timeout_counter = (
        REGISTRY.get_sample_value(
            "lifeflow_provider_timeouts_total", {"provider": "gmail", "operation": "test_timeout"}
        )
        or 0.0
    )

    request = httpx.Request("GET", "https://example.invalid")
    cause = httpx.ConnectTimeout("simulated", request=request)

    with pytest.raises(GoogleTransientError):
        async with observe_provider_call("gmail", "test_timeout"):
            raise GoogleTransientError("timed out") from cause

    assert (
        _provider_requests_value(provider="gmail", operation="test_timeout", outcome="timeout")
        == before_outcome + 1
    )
    after_timeout_counter = REGISTRY.get_sample_value(
        "lifeflow_provider_timeouts_total", {"provider": "gmail", "operation": "test_timeout"}
    )
    assert after_timeout_counter == before_timeout_counter + 1


async def test_a_response_level_transient_error_does_not_touch_the_timeout_counter() -> None:
    """A `GoogleTransientError` raised from an actual 429/5xx response (no
    `__cause__`) is a real answer from the provider, not a timeout — the two
    counters must stay independent so an on-call engineer can trust the
    timeout counter specifically."""
    before = (
        REGISTRY.get_sample_value(
            "lifeflow_provider_timeouts_total",
            {"provider": "gmail", "operation": "test_no_timeout"},
        )
        or 0.0
    )

    with pytest.raises(GoogleTransientError):
        async with observe_provider_call("gmail", "test_no_timeout"):
            raise GoogleTransientError("HTTP 503")

    after = (
        REGISTRY.get_sample_value(
            "lifeflow_provider_timeouts_total",
            {"provider": "gmail", "operation": "test_no_timeout"},
        )
        or 0.0
    )
    assert after == before


def _observe_provider_call_sites() -> list[ast.Call]:
    """Every literal call to `observe_provider_call(...)` in the shipped
    source tree (not this test file) — used to statically prove the
    provider/operation vocabulary is closed at the call site rather than
    computed from runtime data, since prometheus_client itself does not
    reject arbitrary label values at record time."""
    root = Path(__file__).resolve().parent.parent / "src" / "lifeflow_api"
    calls: list[ast.Call] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "observe_provider_call"
            ):
                calls.append(node)
    return calls


_CLOSED_PROVIDERS = {"gmail", "calendar", "google_oauth"}
_CLOSED_OPERATIONS = {
    "create_draft",
    "get_draft",
    "list_messages",
    "get_message",
    "list_history",
    "get_current_history_id",
    "get_profile_email",
    "insert_event",
    "get_event",
    "get_primary_calendar_metadata",
    "list_events",
    "refresh_access_token",
}


def test_every_observe_provider_call_site_uses_a_literal_closed_provider_and_operation() -> None:
    """Proves every real call site passes fixed string literals from the
    documented closed vocabulary — never an f-string, a variable, or any
    other value that could vary per-request and blow up cardinality. A
    future call site passing something else fails this test, which is the
    intended enforcement mechanism (arbitrary operation names are rejected
    at review/CI time, since prometheus_client cannot reject them at
    runtime)."""
    call_sites = _observe_provider_call_sites()
    assert len(call_sites) >= len(_CLOSED_OPERATIONS)  # every registered operation is covered

    for call in call_sites:
        assert len(call.args) == 2, "observe_provider_call must be called with two positional args"
        provider_arg, operation_arg = call.args
        assert isinstance(provider_arg, ast.Constant) and isinstance(provider_arg.value, str), (
            "provider must be a literal string, never computed"
        )
        assert isinstance(operation_arg, ast.Constant) and isinstance(operation_arg.value, str), (
            "operation must be a literal string, never computed"
        )
        assert provider_arg.value in _CLOSED_PROVIDERS
        assert operation_arg.value in _CLOSED_OPERATIONS


async def test_metrics_exposition_never_contains_a_private_sentinel() -> None:
    """Drives every documented outcome through `observe_provider_call` with
    exception messages deliberately carrying sensitive-looking content, then
    proves none of it reaches the rendered exposition text — labels are
    always the fixed `provider`/`operation`/`outcome` strings, never the
    exception message itself."""
    sentinel_email = "victim+private@example.com"
    sentinel_token = "ya29.super-secret-access-token-value"

    for exc in (
        GoogleAuthError(f"rejected for {sentinel_email}"),
        GoogleClientError(f"bad request token={sentinel_token}", status_code=400),
        ValueError(f"unexpected, saw {sentinel_email}"),
    ):
        with pytest.raises(type(exc)):
            async with observe_provider_call("gmail", "test_sentinel_free"):
                raise exc

    body, _ = render_latest()
    text = body.decode("utf-8")
    assert sentinel_email not in text
    assert sentinel_token not in text
    assert re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text) is None, "no email-shaped value leaked"
