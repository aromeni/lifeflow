"""Stage 7: GoogleGmailDraftExecutor / GoogleCalendarEventExecutor (ADR 0003
D16/D17). A 2xx alone is never trusted — the echoed resource must match the
approved payload before `succeeded`; anything else (transient error or an
unverifiable echo) is `uncertain`, never silently treated as success."""

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from tests.test_google_gmail_client import _build_raw_message

from lifeflow_api.action_executors import (
    FinalExecutionError,
    GoogleCalendarEventExecutor,
    GoogleGmailDraftExecutor,
)
from lifeflow_api.action_payloads import (
    CalendarEventCreatePayload,
    GmailDraftCreatePayload,
    TaskCreatePayload,
)
from lifeflow_api.execution_context import ApprovedExecutionAuthorization
from lifeflow_api.google.calendar_client import CalendarEventClient
from lifeflow_api.google.gmail_client import GmailDraftClient

PROPOSAL_ID = uuid.uuid4()
USER_ID = uuid.uuid4()

SAMPLE_AUTHORIZATION = ApprovedExecutionAuthorization(
    connected_account_id=uuid.uuid4(),
    provider="google",
    authorisation_revision=1,
    required_scope="scope",
    execution_context_hash="a" * 64,
)


class _StubTokens:
    """Duck-types the surface `GoogleGmailDraftExecutor`/
    `GoogleCalendarEventExecutor` actually use — the exact-account method,
    not the legacy `(user, provider)` one, plus the `user_id` property the
    executor reads to build the exact-account lookup."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    @property
    def user_id(self) -> uuid.UUID:
        return USER_ID

    async def get_valid_access_token_for_execution(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return "access-token"


DRAFT_PAYLOAD = GmailDraftCreatePayload(
    to=["dana@example.com"], subject="Re: Quarterly review", body="Hi Dana", thread_id="thread-1"
)
EVENT_PAYLOAD = CalendarEventCreatePayload(
    title="Project sync",
    starts_at=datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
    ends_at=datetime(2026, 7, 20, 10, 30, tzinfo=UTC),
    timezone="Europe/London",
    location=None,
    description="",
    attendees=["dana@example.com"],
)


def _create_response(*, draft_id: str = "draft-1", message_id: str = "msg-1") -> dict:
    """`drafts.create`'s own response — identifiers only. A real sandbox
    account showed this response frequently omits a parsed `message.
    payload` entirely, so tests never put verification content here
    (Stage 7 focused remediation) — that only ever comes from `get_draft`."""
    return {"id": draft_id, "message": {"id": message_id, "threadId": "thread-created"}}


def _get_draft_response(
    *,
    draft_id: str = "draft-1",
    message_id: str = "msg-1",
    thread_id: str = "thread-actual",
    to: str = "dana@example.com",
    subject: str = "Re: Quarterly review",
    body: str = "Hi Dana",
) -> dict:
    raw = _build_raw_message(to=to, subject=subject, body=body)
    return {"id": draft_id, "message": {"id": message_id, "threadId": thread_id, "raw": raw}}


def _gmail_executor(handler: httpx.MockTransport) -> GoogleGmailDraftExecutor:
    client = GmailDraftClient(httpx.AsyncClient(transport=handler))
    return GoogleGmailDraftExecutor(client, _StubTokens())


def _gmail_create_then_get(
    get_response: dict, *, create_response: dict | None = None
) -> httpx.MockTransport:
    """The real two-call flow (Stage 7 focused remediation): `create_draft`
    (POST) never itself carries verification content any more — only the
    independent `get_draft` (GET) response does."""
    calls = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.method == "POST":
            return httpx.Response(200, json=create_response or _create_response())
        return httpx.Response(200, json=get_response)

    return httpx.MockTransport(handle)


async def test_gmail_draft_succeeds_when_the_verified_draft_matches() -> None:
    executor = _gmail_executor(_gmail_create_then_get(_get_draft_response()))
    outcome = await executor.execute(
        proposal_id=PROPOSAL_ID, payload=DRAFT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )
    assert outcome.status == "succeeded"
    assert outcome.result["draft_id"] == "draft-1"
    # The actual thread Gmail created, not the requested one (requirement:
    # handle thread ID per Gmail's real semantics).
    assert outcome.result["thread_id"] == "thread-actual"


async def test_gmail_draft_succeeds_even_when_gmail_declines_the_requested_thread_id() -> None:
    """Gmail only honours a requested reply threadId when Subject/
    References make it a valid continuation — otherwise it silently starts
    a new thread. This must never be treated as a verification mismatch;
    only recipient/subject/body matter."""
    executor = _gmail_executor(
        _gmail_create_then_get(_get_draft_response(thread_id="a-completely-different-thread"))
    )
    outcome = await executor.execute(
        proposal_id=PROPOSAL_ID, payload=DRAFT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )
    assert outcome.status == "succeeded"
    assert outcome.result["thread_id"] == "a-completely-different-thread"


async def test_gmail_draft_uncertain_when_verified_recipient_does_not_match_approved_payload() -> (
    None
):
    """D17: a 2xx alone is not proof; the independently re-fetched draft
    must match the approved payload."""
    executor = _gmail_executor(
        _gmail_create_then_get(_get_draft_response(to="someone-else@example.com"))
    )
    outcome = await executor.execute(
        proposal_id=PROPOSAL_ID, payload=DRAFT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )
    assert outcome.status == "uncertain"


async def test_gmail_draft_uncertain_when_verification_fetch_times_out() -> None:
    """The draft has genuinely been created by this point (create already
    returned 200) — an inability to confirm its content is `uncertain`,
    never `failed`: the write happened, LifeFlow just couldn't verify it in
    time (the exact real sandbox finding this remediation fixes)."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json=_create_response())
        return httpx.Response(503, json={})

    executor = _gmail_executor(httpx.MockTransport(handle))
    outcome = await executor.execute(
        proposal_id=PROPOSAL_ID, payload=DRAFT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )
    assert outcome.status == "uncertain"
    assert "did not confirm" in outcome.result["message"].lower()


async def test_gmail_draft_uncertain_when_the_created_draft_cannot_be_refetched() -> None:
    """A 404 on the immediate re-fetch (vanishingly unlikely, not provably
    impossible) must never be read as "the create failed" — it already
    succeeded."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json=_create_response())
        return httpx.Response(404, json={})

    executor = _gmail_executor(httpx.MockTransport(handle))
    outcome = await executor.execute(
        proposal_id=PROPOSAL_ID, payload=DRAFT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )
    assert outcome.status == "uncertain"


async def test_gmail_draft_uncertain_on_transient_error() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    executor = _gmail_executor(httpx.MockTransport(handle))
    outcome = await executor.execute(
        proposal_id=PROPOSAL_ID, payload=DRAFT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )
    assert outcome.status == "uncertain"


async def test_gmail_draft_final_error_on_auth_rejection() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={})

    executor = _gmail_executor(httpx.MockTransport(handle))
    with pytest.raises(FinalExecutionError) as exc:
        await executor.execute(
            proposal_id=PROPOSAL_ID,
            payload=DRAFT_PAYLOAD,
            approved_authorization=SAMPLE_AUTHORIZATION,
        )
    assert exc.value.error_code == "google_auth_rejected"


async def test_gmail_draft_final_error_on_client_rejection() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={})

    executor = _gmail_executor(httpx.MockTransport(handle))
    with pytest.raises(FinalExecutionError) as exc:
        await executor.execute(
            proposal_id=PROPOSAL_ID,
            payload=DRAFT_PAYLOAD,
            approved_authorization=SAMPLE_AUTHORIZATION,
        )
    assert exc.value.error_code == "google_client_error_400"


async def test_gmail_draft_rejects_wrong_payload_type() -> None:
    executor = _gmail_executor(httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    wrong_payload = TaskCreatePayload(title="Not a draft", notes="", due_at=None)
    with pytest.raises(FinalExecutionError) as exc:
        await executor.execute(
            proposal_id=PROPOSAL_ID,
            payload=wrong_payload,
            approved_authorization=SAMPLE_AUTHORIZATION,
        )
    assert exc.value.error_code == "payload_type_mismatch"


async def test_gmail_draft_rejects_missing_approved_authorization() -> None:
    """Defensive: a real Google executor must never proceed without an
    approved authorisation snapshot to bind to (Stage 7 focused
    remediation) — this should never be reachable in production, since
    `execute()` only selects a Google registry when the mode is `real`,
    which always yields a non-`None` snapshot."""
    executor = _gmail_executor(
        httpx.MockTransport(
            lambda r: (_ for _ in ()).throw(AssertionError("must never call Google"))
        )
    )
    with pytest.raises(FinalExecutionError) as exc:
        await executor.execute(
            proposal_id=PROPOSAL_ID, payload=DRAFT_PAYLOAD, approved_authorization=None
        )
    assert exc.value.error_code == "approved_authorization_missing"


def _insert_response() -> dict:
    """`events.insert`'s own response — identifiers only, mirroring the
    Gmail convention (D17/D40): verification content only ever comes from
    the independent `get_event` re-fetch."""
    return {"id": "event-1"}


def _get_event_response(
    *,
    summary: str = "Project sync",
    start: str = "2026-07-20T11:00:00+01:00",  # 10:00 UTC, Google-normalised
    end: str = "2026-07-20T11:30:00+01:00",
    attendees: tuple[str, ...] = ("dana@example.com",),
    status: str = "confirmed",
    organiser: str | None = "owner@example.com",
) -> dict:
    body: dict = {
        "id": "event-1",
        "summary": summary,
        "status": status,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
        "attendees": [{"email": address} for address in attendees],
    }
    if organiser is not None:
        body["organizer"] = {"email": organiser}
    return body


def _calendar_executor(handler: httpx.MockTransport) -> GoogleCalendarEventExecutor:
    client = CalendarEventClient(httpx.AsyncClient(transport=handler))
    return GoogleCalendarEventExecutor(client, _StubTokens())


def _calendar_create_then_get(
    get_response: dict,
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(200, json=_insert_response())
        return httpx.Response(200, json=get_response)

    return httpx.MockTransport(handle), calls


async def test_calendar_event_succeeds_when_the_refetched_event_matches() -> None:
    transport, calls = _calendar_create_then_get(_get_event_response())
    executor = _calendar_executor(transport)
    outcome = await executor.execute(
        proposal_id=PROPOSAL_ID, payload=EVENT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )

    assert outcome.status == "succeeded"
    assert outcome.result["event_id"] == "event-1"
    assert outcome.result["guest_notifications"] == "off"
    posts = [request for request in calls if request.method == "POST"]
    assert len(posts) == 1
    assert posts[0].url.params["sendUpdates"] == "none"
    gets = [request for request in calls if request.method == "GET"]
    assert len(gets) == 1 and gets[0].url.path.endswith("/events/event-1")


async def test_calendar_event_compares_google_normalised_times_by_instant() -> None:
    # Same instants written in UTC spelling instead of the +01:00 offset.
    transport, _ = _calendar_create_then_get(
        _get_event_response(start="2026-07-20T10:00:00Z", end="2026-07-20T10:30:00Z")
    )
    outcome = await _calendar_executor(transport).execute(
        proposal_id=PROPOSAL_ID, payload=EVENT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )
    assert outcome.status == "succeeded"


async def test_calendar_event_uncertain_when_the_stored_start_differs() -> None:
    transport, _ = _calendar_create_then_get(_get_event_response(start="2026-07-20T12:00:00+01:00"))
    outcome = await _calendar_executor(transport).execute(
        proposal_id=PROPOSAL_ID, payload=EVENT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )
    assert outcome.status == "uncertain"


async def test_calendar_event_uncertain_when_a_verified_attendee_is_missing() -> None:
    transport, _ = _calendar_create_then_get(_get_event_response(attendees=("wrong@example.com",)))
    outcome = await _calendar_executor(transport).execute(
        proposal_id=PROPOSAL_ID, payload=EVENT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )
    assert outcome.status == "uncertain"


async def test_calendar_event_tolerates_google_adding_the_organiser_as_attendee() -> None:
    transport, _ = _calendar_create_then_get(
        _get_event_response(attendees=("dana@example.com", "owner@example.com"))
    )
    outcome = await _calendar_executor(transport).execute(
        proposal_id=PROPOSAL_ID, payload=EVENT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )
    assert outcome.status == "succeeded"


async def test_calendar_event_uncertain_on_an_unapproved_extra_attendee() -> None:
    transport, _ = _calendar_create_then_get(
        _get_event_response(attendees=("dana@example.com", "stranger@example.com"))
    )
    outcome = await _calendar_executor(transport).execute(
        proposal_id=PROPOSAL_ID, payload=EVENT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )
    assert outcome.status == "uncertain"


async def test_calendar_event_uncertain_when_the_stored_event_is_cancelled() -> None:
    transport, _ = _calendar_create_then_get(_get_event_response(status="cancelled"))
    outcome = await _calendar_executor(transport).execute(
        proposal_id=PROPOSAL_ID, payload=EVENT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )
    assert outcome.status == "uncertain"


async def test_calendar_event_uncertain_when_verification_refetch_fails() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json=_insert_response())
        return httpx.Response(500, json={})

    outcome = await _calendar_executor(httpx.MockTransport(handle)).execute(
        proposal_id=PROPOSAL_ID, payload=EVENT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )
    assert outcome.status == "uncertain"


async def test_calendar_event_uncertain_when_momentarily_not_found_after_create() -> None:
    """A 404 on the verification read AFTER a successful insert means the
    write happened but could not be confirmed — `uncertain`, never `failed`,
    and never retried automatically."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json=_insert_response())
        return httpx.Response(404, json={})

    outcome = await _calendar_executor(httpx.MockTransport(handle)).execute(
        proposal_id=PROPOSAL_ID, payload=EVENT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )
    assert outcome.status == "uncertain"


async def test_calendar_event_uncertain_on_transient_error() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    executor = _calendar_executor(httpx.MockTransport(handle))
    outcome = await executor.execute(
        proposal_id=PROPOSAL_ID, payload=EVENT_PAYLOAD, approved_authorization=SAMPLE_AUTHORIZATION
    )
    assert outcome.status == "uncertain"


async def test_calendar_event_final_error_on_client_rejection() -> None:
    """A 4xx on the INSERT itself (nothing written) stays a final error."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    executor = _calendar_executor(httpx.MockTransport(handle))
    with pytest.raises(FinalExecutionError) as exc:
        await executor.execute(
            proposal_id=PROPOSAL_ID,
            payload=EVENT_PAYLOAD,
            approved_authorization=SAMPLE_AUTHORIZATION,
        )
    assert exc.value.error_code == "google_client_error_404"
