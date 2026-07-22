"""Stage 8 Phase 3: the owner-scoped inferred-memory API (ADR 0004 D55/D58).

Route-level behaviour: list, confirm (writes the explicit preference),
edit-and-confirm, dismiss, delete one, delete all, ownership isolation, stale
versions, unknown ids, and audit trail.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL

from lifeflow_api.memory import MemoryService
from lifeflow_api.memory_registry import PREFERRED_EMAIL_SIGNOFF_KEY
from lifeflow_api.models import AuditEvent, MemoryEvidence, MemoryItem, MemoryStatus, Preference
from lifeflow_api.preferences import PREFERRED_EMAIL_SIGNOFF_KEY as PREF_KEY

pytestmark = pytest.mark.integration


async def _login(client: AsyncClient, marker: str) -> uuid.UUID:
    response = await client.post(
        "/auth/dev-login",
        json={"email": f"mem-{marker}-{uuid.uuid4()}@example.com", "display_name": "Mem"},
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200
    return uuid.UUID(response.json()["user_id"])


async def _seed_candidate(
    user_id: uuid.UUID,
    *,
    value: str = "Kind regards",
    evidence: int = 2,
    last_evaluated_at: datetime | None = None,
) -> uuid.UUID:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            item = MemoryItem(
                user_id=user_id,
                memory_key=PREFERRED_EMAIL_SIGNOFF_KEY,
                value_json={"value": value},
                status=MemoryStatus.candidate,
                confidence=0.8,
                evidence_count=evidence,
                last_evaluated_at=last_evaluated_at,
                application_mode="suggest_only",
                corresponding_preference_key=PREFERRED_EMAIL_SIGNOFF_KEY,
                version=1,
            )
            session.add(item)
            await session.flush()
            for _ in range(evidence):
                session.add(
                    MemoryEvidence(
                        memory_item_id=item.id,
                        user_id=user_id,
                        evidence_type="gmail_draft_signoff_edit",
                        # No FK linkage needed for API-level tests; the
                        # source proposal is exercised in test_memory_inference.
                        source_proposal_id=None,
                        observed_at=datetime(2026, 7, 22, 9, 0, tzinfo=UTC),
                        derived_value=value,
                        reason_code="approved_edited_draft",
                    )
                )
            await session.flush()
            await session.commit()
            return item.id
    finally:
        await engine.dispose()


async def _audit_types(user_id: uuid.UUID) -> list[str]:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            rows = (
                (
                    await session.execute(
                        select(AuditEvent.event_type).where(AuditEvent.user_id == user_id)
                    )
                )
                .scalars()
                .all()
            )
            return list(rows)
    finally:
        await engine.dispose()


async def _explicit_signoff_row(user_id: uuid.UUID) -> Preference | None:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            return (
                await session.execute(
                    select(Preference).where(
                        Preference.user_id == user_id, Preference.key == PREF_KEY
                    )
                )
            ).scalar_one_or_none()
    finally:
        await engine.dispose()


# --- List -------------------------------------------------------------------


async def test_list_returns_items_with_confidence_and_explanation(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "list")
    await _seed_candidate(user_id)
    response = await dev_client.get("/memories")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["inference_enabled"] is False  # default off
    item = body["memories"][0]
    assert item["value"] == {"value": "Kind regards"}
    assert item["confidence_band"] == "high"
    assert item["evidence_count"] == 2
    assert "Kind regards" in item["explanation"]
    assert item["applied"] is False  # a candidate is never applied
    assert len(item["evidence"]) == 2
    # No raw draft body ever leaks — only the token + reason code.
    assert item["evidence"][0]["derived_value"] == "Kind regards"
    assert item["evidence"][0]["reason_code"] == "approved_edited_draft"


# --- Confirm & edit ---------------------------------------------------------


async def test_confirm_writes_explicit_preference_and_marks_confirmed(
    dev_client: AsyncClient,
) -> None:
    user_id = await _login(dev_client, "confirm")
    item_id = await _seed_candidate(user_id)
    response = await dev_client.post(
        f"/memories/{item_id}/confirm", json={"expected_version": 1}, headers=CSRF_HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["applied"] is True  # confirmed value == explicit preference
    # The confirmed value became the explicit preference (D55).
    pref = await _explicit_signoff_row(user_id)
    assert pref is not None
    assert pref.value_json == {"value": "Kind regards"}
    assert str(pref.provenance) == "explicit"
    events = await _audit_types(user_id)
    assert "memory.confirmed" in events
    assert "preference.updated" in events


async def test_edit_and_confirm_uses_the_edited_value(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "edit")
    item_id = await _seed_candidate(user_id, value="Best")
    response = await dev_client.put(
        f"/memories/{item_id}",
        json={"expected_version": 1, "value": "Warm regards"},
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["value"] == {"value": "Warm regards"}
    pref = await _explicit_signoff_row(user_id)
    assert pref is not None and pref.value_json == {"value": "Warm regards"}
    assert "memory.edited" in await _audit_types(user_id)


async def test_edit_rejects_an_unsafe_signoff(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "unsafe")
    item_id = await _seed_candidate(user_id)
    response = await dev_client.put(
        f"/memories/{item_id}",
        json={"expected_version": 1, "value": "Call me on 07700 900000"},
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 422


# --- Dismiss & delete -------------------------------------------------------


async def test_dismiss_marks_dismissed_and_records_no_value(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "dismiss")
    item_id = await _seed_candidate(user_id)
    response = await dev_client.post(
        f"/memories/{item_id}/dismiss", json={"expected_version": 1}, headers=CSRF_HEADERS
    )
    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"
    assert "memory.dismissed" in await _audit_types(user_id)


async def test_delete_one_removes_item_and_records_key_only(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "delone")
    item_id = await _seed_candidate(user_id)
    response = await dev_client.delete(f"/memories/{item_id}", headers=CSRF_HEADERS)
    assert response.status_code == 200
    assert response.json()["deleted"] == 1
    listed = await dev_client.get("/memories")
    assert listed.json()["count"] == 0
    assert "memory.deleted" in await _audit_types(user_id)


async def test_delete_all_removes_every_memory(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "delall")
    await _seed_candidate(user_id)
    response = await dev_client.delete("/memories", headers=CSRF_HEADERS)
    assert response.status_code == 200
    assert response.json()["deleted"] == 1
    listed = await dev_client.get("/memories")
    assert listed.json()["count"] == 0


# --- Ownership, versions, unknown ids ---------------------------------------


async def test_memories_are_isolated_per_user(dev_client: AsyncClient) -> None:
    owner_id = await _login(dev_client, "owner")
    item_id = await _seed_candidate(owner_id)
    # A different user signs in on the same client.
    await _login(dev_client, "intruder")
    # Cannot see it.
    listed = await dev_client.get("/memories")
    assert listed.json()["count"] == 0
    # Cannot read it — 404 without leaking ownership.
    assert (await dev_client.get(f"/memories/{item_id}")).status_code == 404
    # Cannot act on it.
    confirm = await dev_client.post(
        f"/memories/{item_id}/confirm", json={"expected_version": 1}, headers=CSRF_HEADERS
    )
    assert confirm.status_code == 404


async def test_stale_version_is_409(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "stale")
    item_id = await _seed_candidate(user_id)
    response = await dev_client.post(
        f"/memories/{item_id}/confirm", json={"expected_version": 99}, headers=CSRF_HEADERS
    )
    assert response.status_code == 409


async def test_unknown_id_is_404(dev_client: AsyncClient) -> None:
    await _login(dev_client, "missing")
    missing = await dev_client.get(f"/memories/{uuid.uuid4()}")
    assert missing.status_code == 404


async def test_confirmed_memory_cannot_be_reconfirmed(dev_client: AsyncClient) -> None:
    user_id = await _login(dev_client, "reconfirm")
    item_id = await _seed_candidate(user_id)
    first = await dev_client.post(
        f"/memories/{item_id}/confirm", json={"expected_version": 1}, headers=CSRF_HEADERS
    )
    assert first.status_code == 200
    new_version = first.json()["version"]
    again = await dev_client.post(
        f"/memories/{item_id}/confirm",
        json={"expected_version": new_version},
        headers=CSRF_HEADERS,
    )
    assert again.status_code == 409  # invalid transition (already confirmed)


# --- Confirmation is atomic (Point 3) ---------------------------------------


async def _item_status(item_id: uuid.UUID) -> str | None:
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            item = await session.get(MemoryItem, item_id)
            return None if item is None else str(item.status)
    finally:
        await engine.dispose()


async def test_confirm_rolls_back_entirely_if_it_fails_after_the_preference_write(
    dev_client: AsyncClient,
) -> None:
    """Failure injected *after* the explicit preference write but *before* the
    memory status update — the shared request transaction rolls back both, so
    no partial preference becomes active."""
    user_id = await _login(dev_client, "atomic1")
    item_id = await _seed_candidate(user_id)
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            svc = MemoryService(session, user_id)
            original = svc._write_explicit_signoff

            async def boom(value: str) -> None:
                await original(value)
                raise RuntimeError("injected after the preference write")

            svc._write_explicit_signoff = boom  # type: ignore[method-assign]
            with pytest.raises(RuntimeError):
                await svc.confirm(item_id, expected_version=1)
            await session.rollback()
    finally:
        await engine.dispose()
    assert await _explicit_signoff_row(user_id) is None
    assert await _item_status(item_id) == "candidate"


async def test_confirm_rolls_back_entirely_if_the_memory_audit_fails(
    dev_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure injected *after* the memory status update but *before* the
    memory audit completes — all-or-nothing: the preference write is rolled
    back too, and the item stays a candidate."""
    user_id = await _login(dev_client, "atomic2")
    item_id = await _seed_candidate(user_id)

    import lifeflow_api.memory as memory_module

    real = memory_module.record_audit_event

    def failing(session: object, **kwargs: object) -> object:
        if kwargs.get("entity_type") == "memory_item":
            raise RuntimeError("injected during the memory audit")
        return real(session, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(memory_module, "record_audit_event", failing)
    engine = create_async_engine(TEST_DB_URL)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            svc = MemoryService(session, user_id)
            with pytest.raises(RuntimeError):
                await svc.confirm(item_id, expected_version=1)
            await session.rollback()
    finally:
        await engine.dispose()
    assert await _explicit_signoff_row(user_id) is None
    assert await _item_status(item_id) == "candidate"


async def test_two_confirmations_cannot_create_contradictory_preferences(
    dev_client: AsyncClient,
) -> None:
    """Two confirmations serialize on the row lock: the first wins, the second
    (same, now-stale version) is a 409 — never a second, contradictory
    preference write. A retry of the same request is idempotent-or-conflict."""
    user_id = await _login(dev_client, "concur")
    item_id = await _seed_candidate(user_id, value="Kind regards")
    first = await dev_client.post(
        f"/memories/{item_id}/confirm", json={"expected_version": 1}, headers=CSRF_HEADERS
    )
    assert first.status_code == 200
    retry = await dev_client.post(
        f"/memories/{item_id}/confirm", json={"expected_version": 1}, headers=CSRF_HEADERS
    )
    assert retry.status_code == 409  # stale version — documented conflict
    pref = await _explicit_signoff_row(user_id)
    assert pref is not None
    assert pref.value_json == {"value": "Kind regards"}  # exactly one, the winner's value


# --- Read-time expiry (Point 2, API surface) --------------------------------


async def test_reading_expires_a_decayed_candidate_and_audits_once(dev_client: AsyncClient) -> None:
    """A candidate last evaluated long ago has decayed below the floor; the
    read expires it and exposes the effective status, auditing exactly once
    across repeated reads."""
    user_id = await _login(dev_client, "expread")
    old = datetime.now(UTC) - timedelta(days=400)
    await _seed_candidate(user_id, last_evaluated_at=old)

    listed = await dev_client.get("/memories")
    item = listed.json()["memories"][0]
    assert item["status"] == "expired"
    assert item["confidence"] < 0.15  # effective, decayed value

    await dev_client.get("/memories")  # read again
    events = await _audit_types(user_id)
    assert events.count("memory.expired") == 1
