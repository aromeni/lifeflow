"""Stage 11A Phase 4A (F-P3-03) — key-versioned credential rotation.

Covers the acceptance-matrix rows `test_token_cipher.py`'s unit-level tests
do not: real-database integration for `credential_rotation.py` (dry-run,
bounded batch migration, interruption/resumption, blocked/unknown-key
handling, legacy-key retirement gating), a real-Postgres concurrent
refresh-vs-rotation race, disconnect/deletion interaction with the new
key-id columns, and the structural proof that no public route exposes
rotation to a user-controlled identifier.
"""

import asyncio
import base64
import io
import logging
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL
from tests.test_google_token_service import NOW, _seed_google_account, _StubOAuthClient

from lifeflow_api.accounts import ConnectedAccountService, GoogleTokenService
from lifeflow_api.credential_rotation import (
    dry_run_inventory,
    rotate_batch,
    verify_key_retirement_safe,
)
from lifeflow_api.deletion import confirm_operation, create_account_deletion_preview, run_operation
from lifeflow_api.deletion_ops import CONFIRM_ACCOUNT
from lifeflow_api.google.oauth import GoogleTokenResponse
from lifeflow_api.logging_setup import JsonFormatter
from lifeflow_api.models import AccountStatus, ConnectedAccount, User
from lifeflow_api.retention import RetentionHorizons
from lifeflow_api.security.credential_context import (
    ACCESS_TOKEN_FIELD,
    REFRESH_TOKEN_FIELD,
    credential_context,
)
from lifeflow_api.security.token_cipher import AesGcmTokenCipher, TokenCipherError, TokenKeyRing

pytestmark = pytest.mark.integration

_HORIZONS = RetentionHorizons(
    source_items_days=30,
    brief_versions_days=90,
    unapproved_proposals_days=90,
    scheduled_runs_days=90,
    memory_evidence_days=90,
)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


def _random_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


async def _seed_account_on_key(
    session: AsyncSession, cipher: AesGcmTokenCipher, *, provider: str = "google"
) -> ConnectedAccount:
    user = User(email=f"rot-{uuid.uuid4()}@example.com", display_name="Rot")
    session.add(user)
    await session.flush()
    account = ConnectedAccount(
        user_id=user.id, provider=provider, status=AccountStatus.active, granted_scopes=["scope"]
    )
    session.add(account)
    await session.flush()
    for field_name, attr, key_attr in (
        (ACCESS_TOKEN_FIELD, "encrypted_access_token", "access_token_key_id"),
        (REFRESH_TOKEN_FIELD, "encrypted_refresh_token", "refresh_token_key_id"),
    ):
        context = credential_context(
            connected_account_id=account.id, user_id=user.id, provider=provider, field=field_name
        )
        envelope = cipher.encrypt(f"plain-{field_name}-{uuid.uuid4()}", context=context)
        setattr(account, attr, envelope)
        setattr(account, key_attr, cipher.key_id)
    await session.flush()
    return account


# --- owner/account cryptographic binding, at the database-row level --------


async def test_transplanted_ciphertext_across_accounts_fails_to_decrypt(
    session: AsyncSession,
) -> None:
    """S11A-P4A-004/046: even with full row access, copying one account's
    ciphertext into a different account's column must not decrypt under the
    victim account's context. Treated as P0 if this ever succeeds."""
    cipher = AesGcmTokenCipher(_random_key(), "shared-1")
    account_a = await _seed_account_on_key(session, cipher)
    account_b = await _seed_account_on_key(session, cipher)
    await session.commit()

    stolen_envelope = account_a.encrypted_access_token
    victim_context = credential_context(
        connected_account_id=account_b.id,
        user_id=account_b.user_id,
        provider=account_b.provider,
        field=ACCESS_TOKEN_FIELD,
    )
    with pytest.raises(TokenCipherError):
        cipher.decrypt(stolen_envelope, context=victim_context)


async def test_transplanted_ciphertext_across_fields_fails_to_decrypt(
    session: AsyncSession,
) -> None:
    """S11A-P4A-007: swapping an account's own access/refresh envelopes must
    also fail — binding is per-field, not merely per-row."""
    cipher = AesGcmTokenCipher(_random_key(), "shared-1")
    account = await _seed_account_on_key(session, cipher)
    await session.commit()

    refresh_context = credential_context(
        connected_account_id=account.id,
        user_id=account.user_id,
        provider=account.provider,
        field=REFRESH_TOKEN_FIELD,
    )
    with pytest.raises(TokenCipherError):
        cipher.decrypt(account.encrypted_access_token, context=refresh_context)


# --- rotation service, against real PostgreSQL ------------------------------


async def test_dry_run_inventory_counts_legacy_rows(session: AsyncSession) -> None:
    legacy = AesGcmTokenCipher(_random_key(), "legacy-x")
    active = AesGcmTokenCipher(_random_key(), "active-x")
    ring = TokenKeyRing(active, [legacy])
    await _seed_account_on_key(session, legacy)
    await _seed_account_on_key(session, legacy)
    await session.commit()

    inventory = await dry_run_inventory(session, ring)
    assert inventory.get("legacy-x", 0) >= 2


async def test_rotate_batch_migrates_a_legacy_row_to_the_active_key(
    session: AsyncSession,
) -> None:
    legacy = AesGcmTokenCipher(_random_key(), "legacy-y")
    active = AesGcmTokenCipher(_random_key(), "active-y")
    ring = TokenKeyRing(active, [legacy])
    account = await _seed_account_on_key(session, legacy)
    await session.commit()

    result = await rotate_batch(session, ring, batch_size=10)
    await session.commit()

    assert result.migrated >= 1
    refreshed = await session.get(ConnectedAccount, account.id, populate_existing=True)
    assert refreshed is not None
    assert refreshed.access_token_key_id == "active-y"
    assert refreshed.refresh_token_key_id == "active-y"
    context = credential_context(
        connected_account_id=refreshed.id,
        user_id=refreshed.user_id,
        provider=refreshed.provider,
        field=ACCESS_TOKEN_FIELD,
    )
    assert ring.decrypt(refreshed.encrypted_access_token, context=context).startswith("plain-")


async def test_rotate_batch_skips_rows_already_on_the_active_key(session: AsyncSession) -> None:
    active = AesGcmTokenCipher(_random_key(), "active-z")
    ring = TokenKeyRing(active)
    await _seed_account_on_key(session, active)
    await session.commit()

    result = await rotate_batch(session, ring, batch_size=10)
    assert result.migrated == 0
    assert (
        result.skipped_current == 0
    )  # nothing selected at all — already current, not even a candidate


async def test_rotate_batch_blocks_rows_whose_key_the_ring_no_longer_holds(
    session: AsyncSession,
) -> None:
    """S11A-P4A-029: a row on a key that has been retired/never configured
    must be reported BLOCKED — never deleted, never marked migrated."""
    orphaned = AesGcmTokenCipher(_random_key(), "orphaned-1")
    active = AesGcmTokenCipher(_random_key(), "active-only")
    account = await _seed_account_on_key(session, orphaned)
    await session.commit()

    ring = TokenKeyRing(active)  # orphaned-1 deliberately absent
    result = await rotate_batch(session, ring, batch_size=10)
    await session.commit()

    assert result.blocked == 1
    assert str(account.id) in result.blocked_account_ids
    unchanged = await session.get(ConnectedAccount, account.id, populate_existing=True)
    assert unchanged is not None
    assert unchanged.access_token_key_id == "orphaned-1"  # untouched, not lost


async def test_rotate_batch_is_resumable_after_a_simulated_interruption(
    session: AsyncSession,
) -> None:
    legacy = AesGcmTokenCipher(_random_key(), "legacy-resume")
    active = AesGcmTokenCipher(_random_key(), "active-resume")
    ring = TokenKeyRing(active, [legacy])
    accounts = [await _seed_account_on_key(session, legacy) for _ in range(3)]
    account_ids = [account.id for account in accounts]  # captured before the rollback below
    await session.commit()

    # Simulate an interruption: migrate, then roll back before commit.
    await rotate_batch(session, ring, batch_size=10)
    await session.rollback()

    rows = (
        (
            await session.execute(
                select(ConnectedAccount).where(ConnectedAccount.id.in_(account_ids))
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == len(account_ids)
    for row in rows:
        assert row.access_token_key_id == "legacy-resume"  # rollback truly discarded it

    # Resume: this run must complete the work the rolled-back one did not.
    result = await rotate_batch(session, ring, batch_size=10)
    await session.commit()
    assert result.migrated == len(accounts)


async def test_rerunning_rotation_after_completion_is_a_no_op(session: AsyncSession) -> None:
    legacy = AesGcmTokenCipher(_random_key(), "legacy-idem")
    active = AesGcmTokenCipher(_random_key(), "active-idem")
    ring = TokenKeyRing(active, [legacy])
    await _seed_account_on_key(session, legacy)
    await session.commit()

    first = await rotate_batch(session, ring, batch_size=10)
    await session.commit()
    assert first.migrated == 1

    second = await rotate_batch(session, ring, batch_size=10)
    assert second.migrated == 0
    assert second.processed == 0  # already-current rows are not even selected


# --- legacy-key retirement gating -------------------------------------------


async def test_key_retirement_is_blocked_while_rows_still_reference_it(
    session: AsyncSession,
) -> None:
    legacy = AesGcmTokenCipher(_random_key(), "legacy-retire")
    await _seed_account_on_key(session, legacy)
    await session.commit()

    assert await verify_key_retirement_safe(session, "legacy-retire") is False


async def test_key_retirement_is_permitted_once_zero_rows_reference_it(
    session: AsyncSession,
) -> None:
    legacy = AesGcmTokenCipher(_random_key(), "legacy-clear")
    active = AesGcmTokenCipher(_random_key(), "active-clear")
    ring = TokenKeyRing(active, [legacy])
    await _seed_account_on_key(session, legacy)
    await session.commit()

    await rotate_batch(session, ring, batch_size=10)
    await session.commit()

    assert await verify_key_retirement_safe(session, "legacy-clear") is True


# --- concurrent refresh vs. rotation, real PostgreSQL row locking -----------


async def test_concurrent_refresh_and_rotation_never_corrupt_a_row(session: AsyncSession) -> None:
    """S11A-P4A-031: a real token refresh (SELECT ... FOR UPDATE) and a real
    rotation batch (SELECT ... FOR UPDATE SKIP LOCKED) racing the same row
    must leave exactly one consistent, decryptable result — never a split
    write, never a lost update."""
    legacy = AesGcmTokenCipher(_random_key(), "legacy-race")
    active = AesGcmTokenCipher(_random_key(), "active-race")
    ring = TokenKeyRing(active, [legacy])

    user = await _seed_google_account(
        session, legacy, expires_at=NOW + timedelta(seconds=30), refresh_token="race-refresh"
    )
    await session.commit()

    async def do_refresh() -> None:
        engine = create_async_engine(TEST_DB_URL)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as racing:
                oauth = _StubOAuthClient(
                    GoogleTokenResponse(
                        access_token="access-after-race",
                        refresh_token=None,
                        expires_in=3600,
                        scope="a",
                        id_token=None,
                    )
                )
                service = GoogleTokenService(
                    racing,
                    user.id,
                    ring,
                    oauth,
                    client_id="cid",
                    client_secret="secret",  # pragma: allowlist secret
                    now_factory=lambda: NOW,
                )
                await service.get_valid_access_token("google")
                await racing.commit()
        finally:
            await engine.dispose()

    async def do_rotate() -> None:
        engine = create_async_engine(TEST_DB_URL)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as racing:
                await rotate_batch(racing, ring, batch_size=10)
                await racing.commit()
        finally:
            await engine.dispose()

    await asyncio.gather(do_refresh(), do_rotate())

    final = (
        await session.execute(select(ConnectedAccount).where(ConnectedAccount.user_id == user.id))
    ).scalar_one()
    context = credential_context(
        connected_account_id=final.id,
        user_id=final.user_id,
        provider=final.provider,
        field=ACCESS_TOKEN_FIELD,
    )
    # Whichever interleaving won, the surviving envelope must be readable and
    # every reference to the active key must be internally consistent.
    plaintext = ring.decrypt(final.encrypted_access_token, context=context)
    assert plaintext in ("access-after-race",) or plaintext.startswith("access-")
    assert final.access_token_key_id == "active-race"


# --- disconnect / deletion interaction with key-id columns ------------------


async def test_disconnect_clears_key_id_columns(session: AsyncSession) -> None:
    cipher = AesGcmTokenCipher(_random_key(), "disc-1")
    user = User(email=f"disc-{uuid.uuid4()}@example.com", display_name="Disc")
    session.add(user)
    await session.flush()
    await ConnectedAccountService(session, user.id, cipher).store_tokens(
        provider="google",
        access_token="a",
        refresh_token="r",
        granted_scopes=["s"],
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await session.commit()

    await ConnectedAccountService(session, user.id, cipher).disconnect("google")
    await session.commit()

    account = (
        await session.execute(select(ConnectedAccount).where(ConnectedAccount.user_id == user.id))
    ).scalar_one()
    assert account.access_token_key_id is None
    assert account.refresh_token_key_id is None


async def test_full_account_deletion_removes_key_id_columns_with_the_row(
    session: AsyncSession,
) -> None:
    cipher = AesGcmTokenCipher(_random_key(), "del-1")
    account = await _seed_account_on_key(session, cipher)
    user = await session.get(User, account.user_id)
    assert user is not None
    await session.commit()

    op = await create_account_deletion_preview(session, user, now=NOW, ttl_minutes=30)
    confirmed = await confirm_operation(
        session,
        user,
        op.id,
        expected_version=op.version,
        phrase=CONFIRM_ACCOUNT,
        now=NOW,
        preview_ttl_minutes=30,
    )
    await session.commit()
    await run_operation(
        session, confirmed.id, now=NOW, horizons=_HORIZONS, batch_size=50, max_attempts=3
    )
    await session.commit()

    remaining = (
        (await session.execute(select(ConnectedAccount).where(ConnectedAccount.user_id == user.id)))
        .scalars()
        .all()
    )
    assert remaining == []


# --- structural proof: no public rotation route exists ----------------------


def test_no_router_file_references_the_rotation_service() -> None:
    """S11A-P4A-045/046: `credential_rotation` must only ever be imported by
    the internal service module, its own tests, and the operator CLI/
    rehearsal scripts — never by any FastAPI route module, which would make
    it reachable from a user-controlled request."""
    src_root = Path(__file__).resolve().parent.parent / "src" / "lifeflow_api"
    router_dirs = [src_root / "routes", src_root]
    offending: list[str] = []
    for directory in {d for d in router_dirs if d.exists()}:
        for path in directory.rglob("*.py"):
            if path.name in ("credential_rotation.py",):
                continue
            text = path.read_text(encoding="utf-8")
            if "credential_rotation" in text and "APIRouter" in text:
                offending.append(str(path))
    assert offending == [], f"a router file references credential_rotation: {offending}"


# --- secret-sentinel scan across a full rotation cycle ----------------------


async def test_rotation_never_logs_plaintext_or_key_material(session: AsyncSession) -> None:
    """S11A-P4A-043: distinctive sentinel plaintext and key material must
    never appear in structured logs captured across a full dry-run + batch
    migration cycle. Attached after the app's own `configure_logging()`
    would have run, matching the pattern `test_stage11a_phase3_log_privacy.py`
    established for surviving that function's handler reset."""
    sentinel_plaintext = f"SENTINEL-ROTATE-PLAINTEXT-{uuid.uuid4()}"  # pragma: allowlist secret
    legacy_key_b64 = base64.b64encode(os.urandom(32)).decode()
    active_key_b64 = base64.b64encode(os.urandom(32)).decode()

    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    previous_level = root_logger.level
    root_logger.setLevel(logging.DEBUG)

    try:
        legacy = AesGcmTokenCipher(legacy_key_b64, "legacy-sentinel")
        active = AesGcmTokenCipher(active_key_b64, "active-sentinel")
        ring = TokenKeyRing(active, [legacy])

        user = User(email=f"sentinel-rot-{uuid.uuid4()}@example.com", display_name="SentinelRot")
        session.add(user)
        await session.flush()
        account = ConnectedAccount(
            user_id=user.id, provider="google", status=AccountStatus.active, granted_scopes=["s"]
        )
        session.add(account)
        await session.flush()
        context = credential_context(
            connected_account_id=account.id,
            user_id=user.id,
            provider="google",
            field=ACCESS_TOKEN_FIELD,
        )
        account.encrypted_access_token = legacy.encrypt(sentinel_plaintext, context=context)
        account.access_token_key_id = "legacy-sentinel"
        await session.commit()

        await dry_run_inventory(session, ring)
        await rotate_batch(session, ring, batch_size=10)
        await session.commit()
    finally:
        root_logger.removeHandler(handler)
        root_logger.setLevel(previous_level)
        captured = log_capture.getvalue()
        assert sentinel_plaintext not in captured
        assert legacy_key_b64 not in captured
        assert active_key_b64 not in captured
