"""Closed, canonical Stage 6 action payload contracts."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from lifeflow_api.action_payloads import (
    CalendarEventCreatePayload,
    GmailDraftCreatePayload,
    TaskCreatePayload,
    action_payload_hash,
    approval_binding_hash,
    canonical_payload,
    parse_action_payload,
)
from lifeflow_api.models import ActionType


def test_canonical_hash_is_order_independent_and_binds_type_and_version() -> None:
    first = {
        "notes": "Use the exact reviewed fields.",
        "due_at": "2026-07-17T09:00:00Z",
        "title": "Prepare the review",
    }
    reordered = {
        "title": "Prepare the review",
        "notes": "Use the exact reviewed fields.",
        "due_at": "2026-07-17T09:00:00+00:00",
    }

    assert canonical_payload(ActionType.create_task, first) == canonical_payload(
        ActionType.create_task, reordered
    )
    assert action_payload_hash(ActionType.create_task, first) == action_payload_hash(
        ActionType.create_task, reordered
    )
    context_hash = "a" * 64
    assert approval_binding_hash(
        ActionType.create_task, first, 1, context_hash
    ) != approval_binding_hash(ActionType.create_task, first, 2, context_hash)
    assert approval_binding_hash(
        ActionType.create_task, first, 1, context_hash
    ) != approval_binding_hash(ActionType.create_task, first, 1, "b" * 64)


@pytest.mark.parametrize(
    ("action_type", "payload"),
    [
        (ActionType.create_task, {"title": "Task", "notes": "Notes"}),
        (
            ActionType.create_gmail_draft,
            {"to": ["person@example.test"], "subject": "Subject", "body": "Body"},
        ),
        (
            ActionType.create_calendar_event,
            {
                "title": "Meeting",
                "starts_at": "2026-07-17T09:00:00Z",
                "ends_at": "2026-07-17T10:00:00Z",
                "timezone": "Europe/London",
                "description": "Review",
                "attendees": ["person@example.test"],
            },
        ),
    ],
)
def test_every_executor_field_must_be_explicit(
    action_type: ActionType, payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        parse_action_payload(action_type, payload)


def test_hidden_defaults_and_wrong_payload_types_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse_action_payload(
            ActionType.create_task,
            {
                "title": "Task",
                "notes": "Notes",
                "due_at": None,
                "hidden_priority": "urgent",
            },
        )
    with pytest.raises(ValidationError):
        parse_action_payload(
            ActionType.create_task,
            {
                "title": "Task",
                "notes": 42,
                "due_at": None,
            },
        )
    with pytest.raises(ValidationError, match="ISO strings"):
        TaskCreatePayload(title="Task", notes="Notes", due_at=1_721_210_400)


def test_payload_validators_cover_demo_addresses_dates_and_timezones() -> None:
    assert GmailDraftCreatePayload(
        to=["demo@lifeflow.local"], subject="Draft", body="Body", thread_id=None
    ).to == ["demo@lifeflow.local"]
    with pytest.raises(ValidationError, match="valid email"):
        GmailDraftCreatePayload(to=["not-an-address"], subject="Draft", body="Body", thread_id=None)
    with pytest.raises(ValidationError, match="must be unique"):
        GmailDraftCreatePayload(
            to=["One@example.test", "one@example.test"],
            subject="Draft",
            body="Body",
            thread_id=None,
        )
    with pytest.raises(ValidationError, match="end after"):
        CalendarEventCreatePayload(
            title="Meeting",
            starts_at=datetime(2026, 7, 17, 10, tzinfo=UTC),
            ends_at=datetime(2026, 7, 17, 9, tzinfo=UTC),
            timezone="Europe/London",
            location=None,
            description="Review",
            attendees=["person@example.test"],
        )
    with pytest.raises(ValidationError, match="not recognised"):
        CalendarEventCreatePayload(
            title="Meeting",
            starts_at=datetime(2026, 7, 17, 9, tzinfo=UTC),
            ends_at=datetime(2026, 7, 17, 10, tzinfo=UTC),
            timezone="Mars/Olympus",
            location=None,
            description="Review",
            attendees=["person@example.test"],
        )


def test_closed_action_type_rejects_prohibited_send() -> None:
    payload = TaskCreatePayload(title="Task", notes="Notes", due_at=None)
    with pytest.raises(ValueError):
        parse_action_payload("send_email", payload)
