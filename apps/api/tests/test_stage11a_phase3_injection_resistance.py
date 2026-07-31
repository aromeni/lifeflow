"""Stage 11A Phase 3 (S11A-P3-027) — input handling and injection
resistance through real API routes and a real PostgreSQL database.

SQL injection risk is structurally low here (SQLAlchemy's ORM is
parameterised throughout, no string-built SQL anywhere in the codebase),
and React's default auto-escaping plus the absence of any
`dangerouslySetInnerHTML` on the frontend closes classic stored/reflected
XSS structurally too — but the Phase 3 audit found no test that actually
sends these payload shapes through a real route and confirms the safe
outcome directly, rather than relying on those structural properties alone.
This file drives a representative set of malicious-shaped strings through
the one user-controlled free-text surface with the most permissive
validation (a task proposal's title/notes), and confirms: no 500, no SQL
error text, no stack trace, and — for anything accepted — the content comes
back byte-identical (never executed, never silently altered) on the next
read.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL

from lifeflow_api.models import ActionProposal, ActionType, ProposalStatus

pytestmark = pytest.mark.integration

MALICIOUS_PAYLOADS = [
    ("script_tag", "<script>alert('xss')</script>"),
    ("event_handler_attribute", "<img src=x onerror=alert(1)>"),
    ("javascript_url", "javascript:alert(document.cookie)"),
    ("markdown_link_javascript", "[click me](javascript:alert(1))"),
    ("sql_like_string", "'; DROP TABLE action_proposals; --"),
    ("sql_union", "' UNION SELECT email, encrypted_access_token FROM users --"),
    ("template_expression", "{{7*7}}${7*7}#{7*7}"),
    ("shell_like_string", "$(rm -rf /); `id`; | cat /etc/passwd"),
    ("unicode_control_chars", "Title\u202ewith control chars"),
    ("bidi_override", "\u202etext appears reversed\u202c"),
    ("null_byte_in_string", "before\x00after"),
    ("nested_json_shaped_string", '{"a": {"b": {"c": [1,2,3]}}}'),
]


async def _login(client: AsyncClient, marker: str) -> uuid.UUID:
    response = await client.post(
        "/auth/dev-login",
        json={
            "email": f"injection-{marker}-{uuid.uuid4()}@example.com",
            "display_name": "Injection Resistance",
        },
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200
    return uuid.UUID(response.json()["user_id"])


async def _seed_task_proposal(user_id: uuid.UUID) -> uuid.UUID:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            proposal = ActionProposal(
                user_id=user_id,
                origin_fingerprint=f"fp-{uuid.uuid4()}",
                action_type=ActionType.create_task,
                rationale="Injection-resistance fixture",
                source_refs=[],
                payload_json={"title": "Initial title", "notes": "", "due_at": None},
                payload_hash="0" * 64,
                risk_level="low",
                confidence=0.9,
                status=ProposalStatus.proposed,
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
            session.add(proposal)
            await session.commit()
            return proposal.id
    finally:
        await engine.dispose()


@pytest.mark.parametrize("label,payload", MALICIOUS_PAYLOADS)
async def test_malicious_text_never_causes_a_server_error_or_is_executed(
    dev_client: AsyncClient, label: str, payload: str
) -> None:
    user_id = await _login(dev_client, label)
    proposal_id = await _seed_task_proposal(user_id)

    response = await dev_client.patch(
        f"/action-proposals/{proposal_id}",
        json={
            "expected_version": 1,
            "action_type": "create_task",
            "payload": {"title": payload, "notes": payload, "due_at": None},
        },
        headers=CSRF_HEADERS,
    )
    # Never a crash, regardless of whether the content is accepted.
    assert response.status_code in (200, 422), f"{label} caused status {response.status_code}"
    assert response.status_code != 500

    body_text = response.text
    assert "Traceback" not in body_text
    assert "psycopg" not in body_text and "asyncpg" not in body_text
    assert "sqlalchemy" not in body_text.lower()

    if response.status_code == 200:
        # Stored and returned byte-identical — never executed, never
        # silently sanitised into something different.
        readback = await dev_client.get(f"/action-proposals/{proposal_id}")
        assert readback.status_code == 200
        stored_title = readback.json()["payload"]["title"]
        assert stored_title == payload

        # The database itself was never confused into treating this as SQL
        # or losing the row — the proposal still exists exactly once.
        engine = create_async_engine(TEST_DB_URL)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as session:
                from lifeflow_api.repositories import ActionProposalRepository

                repo = ActionProposalRepository(session, user_id)
                surviving = await repo.get(proposal_id)
                assert surviving is not None
                assert surviving.payload_json["title"] == payload
        finally:
            await engine.dispose()


async def test_oversized_content_is_rejected_not_silently_truncated(
    dev_client: AsyncClient,
) -> None:
    user_id = await _login(dev_client, "oversized")
    proposal_id = await _seed_task_proposal(user_id)

    oversized_title = "A" * 10_000  # exceeds TaskCreatePayload's 200-char limit
    response = await dev_client.patch(
        f"/action-proposals/{proposal_id}",
        json={
            "expected_version": 1,
            "action_type": "create_task",
            "payload": {"title": oversized_title, "notes": "", "due_at": None},
        },
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 422


async def test_unexpected_object_type_is_rejected_not_a_server_error(
    dev_client: AsyncClient,
) -> None:
    user_id = await _login(dev_client, "wrong-type")
    proposal_id = await _seed_task_proposal(user_id)

    response = await dev_client.patch(
        f"/action-proposals/{proposal_id}",
        json={
            "expected_version": 1,
            "action_type": "create_task",
            "payload": {
                "title": ["not", "a", "string"],
                "notes": {"nested": "object"},
                "due_at": None,
            },
        },
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 422
    assert response.status_code != 500


async def test_audit_history_never_renders_the_malicious_content_verbatim(
    dev_client: AsyncClient,
) -> None:
    """The audit-history projection is already a closed-vocabulary
    presentation registry (never raw metadata) — this proves that holds
    even when the edited proposal's own content is adversarial."""
    user_id = await _login(dev_client, "audit-check")
    proposal_id = await _seed_task_proposal(user_id)
    payload = "<script>alert('xss')</script>"

    edit = await dev_client.patch(
        f"/action-proposals/{proposal_id}",
        json={
            "expected_version": 1,
            "action_type": "create_task",
            "payload": {"title": payload, "notes": "", "due_at": None},
        },
        headers=CSRF_HEADERS,
    )
    assert edit.status_code == 200

    history = await dev_client.get("/audit-history")
    assert history.status_code == 200
    assert payload not in history.text
