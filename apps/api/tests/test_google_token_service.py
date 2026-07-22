"""Stage 7: GoogleTokenService — the single path real callers use to obtain
a valid access token (ADR 0003 D18/D19/D20). Refresh concurrency, revoked
handling, and refresh-token preservation, against a real PostgreSQL row lock
and a stub OAuth client (never real network).
"""

import asyncio
import base64
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL

from lifeflow_api.accounts import (
    ConnectedAccountService,
    GoogleTokenService,
    ReauthorisationRequiredError,
)
from lifeflow_api.execution_context import ApprovedExecutionContextChangedError
from lifeflow_api.google.errors import InvalidGrantError
from lifeflow_api.google.oauth import GoogleTokenResponse
from lifeflow_api.models import AccountStatus, ConnectedAccount, User
from lifeflow_api.repositories import AuditEventRepository, ConnectedAccountRepository
from lifeflow_api.security.token_cipher import AesGcmTokenCipher

pytestmark = pytest.mark.integration

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


class _StubOAuthClient:
    def __init__(
        self, response: GoogleTokenResponse | None = None, *, raises: Exception | None = None
    ) -> None:
        self.calls = 0
        self._response = response
        self._raises = raises

    async def refresh_access_token(
        self, *, client_id: str, client_secret: str, refresh_token: str
    ) -> GoogleTokenResponse:
        self.calls += 1
        if self._raises:
            raise self._raises
        assert self._response is not None
        return self._response


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


@pytest.fixture
def cipher() -> AesGcmTokenCipher:
    return AesGcmTokenCipher(base64.b64encode(os.urandom(32)).decode(), "test-1")


async def _seed_google_account(
    session: AsyncSession,
    cipher: AesGcmTokenCipher,
    *,
    expires_at: datetime,
    refresh_token: str | None = "refresh-1",
) -> User:
    user = User(email=f"g-{uuid.uuid4()}@example.com", display_name="G")
    session.add(user)
    await session.flush()
    await ConnectedAccountService(session, user.id, cipher).store_tokens(
        provider="google",
        access_token="access-old",
        refresh_token=refresh_token,
        granted_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        expires_at=expires_at,
    )
    await session.flush()
    return user


async def test_fresh_token_is_returned_without_any_refresh_call(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user = await _seed_google_account(session, cipher, expires_at=NOW + timedelta(hours=1))
    oauth = _StubOAuthClient()
    service = GoogleTokenService(
        session,
        user.id,
        cipher,
        oauth,
        client_id="cid",
        client_secret="secret",
        now_factory=lambda: NOW,
    )
    token = await service.get_valid_access_token("google")
    assert token == "access-old"
    assert oauth.calls == 0


async def test_expiring_token_is_refreshed(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user = await _seed_google_account(session, cipher, expires_at=NOW + timedelta(seconds=30))
    oauth = _StubOAuthClient(
        GoogleTokenResponse(
            access_token="access-new", refresh_token=None, expires_in=3600, scope="a", id_token=None
        )
    )
    service = GoogleTokenService(
        session,
        user.id,
        cipher,
        oauth,
        client_id="cid",
        client_secret="secret",
        now_factory=lambda: NOW,
    )
    token = await service.get_valid_access_token("google")
    assert token == "access-new"
    assert oauth.calls == 1

    account = await ConnectedAccountRepository(session, user.id).get_by_provider("google")
    assert account is not None
    assert cipher.decrypt(account.encrypted_refresh_token) == "refresh-1"  # preserved (D18)


async def test_refresh_response_with_new_refresh_token_replaces_it(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user = await _seed_google_account(session, cipher, expires_at=NOW + timedelta(seconds=30))
    oauth = _StubOAuthClient(
        GoogleTokenResponse(
            access_token="access-new",
            refresh_token="refresh-2",
            expires_in=3600,
            scope="a",
            id_token=None,
        )
    )
    service = GoogleTokenService(
        session,
        user.id,
        cipher,
        oauth,
        client_id="cid",
        client_secret="secret",
        now_factory=lambda: NOW,
    )
    await service.get_valid_access_token("google")
    account = await ConnectedAccountRepository(session, user.id).get_by_provider("google")
    assert account is not None
    assert cipher.decrypt(account.encrypted_refresh_token) == "refresh-2"


async def test_invalid_grant_marks_account_revoked_and_raises(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user = await _seed_google_account(session, cipher, expires_at=NOW + timedelta(seconds=30))
    oauth = _StubOAuthClient(raises=InvalidGrantError("rejected"))
    service = GoogleTokenService(
        session,
        user.id,
        cipher,
        oauth,
        client_id="cid",
        client_secret="secret",
        now_factory=lambda: NOW,
    )
    with pytest.raises(ReauthorisationRequiredError):
        await service.get_valid_access_token("google")

    account = await ConnectedAccountRepository(session, user.id).get_by_provider("google")
    assert account is not None
    assert account.status == AccountStatus.revoked

    events = await AuditEventRepository(session, user.id).list(limit=50)
    assert any(e.event_type == "account.revoked" for e in events)


async def test_no_connected_account_requires_reauthorisation(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user = User(email=f"g-{uuid.uuid4()}@example.com", display_name="G")
    session.add(user)
    await session.flush()
    oauth = _StubOAuthClient()
    service = GoogleTokenService(
        session,
        user.id,
        cipher,
        oauth,
        client_id="cid",
        client_secret="secret",
        now_factory=lambda: NOW,
    )
    with pytest.raises(ReauthorisationRequiredError):
        await service.get_valid_access_token("google")


async def test_missing_refresh_token_requires_reauthorisation(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user = await _seed_google_account(
        session, cipher, expires_at=NOW + timedelta(seconds=30), refresh_token=None
    )
    oauth = _StubOAuthClient()
    service = GoogleTokenService(
        session,
        user.id,
        cipher,
        oauth,
        client_id="cid",
        client_secret="secret",
        now_factory=lambda: NOW,
    )
    with pytest.raises(ReauthorisationRequiredError):
        await service.get_valid_access_token("google")


async def test_concurrent_refresh_is_serialised_by_the_row_lock(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user = await _seed_google_account(session, cipher, expires_at=NOW + timedelta(seconds=30))
    await session.commit()

    call_counter = {"n": 0}

    async def refresh_once() -> str:
        engine = create_async_engine(TEST_DB_URL)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as racing:
                oauth = _StubOAuthClient(
                    GoogleTokenResponse(
                        access_token=f"access-{call_counter['n']}",
                        refresh_token=None,
                        expires_in=3600,
                        scope="a",
                        id_token=None,
                    )
                )
                service = GoogleTokenService(
                    racing,
                    user.id,
                    cipher,
                    oauth,
                    client_id="cid",
                    client_secret="secret",
                    now_factory=lambda: NOW,
                )
                token = await service.get_valid_access_token("google")
                call_counter["n"] += oauth.calls
                await racing.commit()
                return token
        finally:
            await engine.dispose()

    first, second = await asyncio.gather(refresh_once(), refresh_once())

    # The row lock serialises the two refreshes: the second sees the first's
    # already-refreshed, still-valid token and never calls the OAuth client.
    assert call_counter["n"] == 1
    assert first == second


# --- get_valid_access_token_for_execution (Stage 7 focused remediation) ---
# The exact-account variant real action executors use: row-locks by BOTH
# `connected_account_id` and `user_id`, then re-verifies provider, status,
# `authorisation_revision`, and `required_scope` atomically with token
# acquisition — never a `(user, provider)` lookup that could resolve to
# whatever happens to be connected right now.

REQUIRED_SCOPE = "https://www.googleapis.com/auth/gmail.compose"


async def _seed_google_account_for_execution(
    session: AsyncSession,
    cipher: AesGcmTokenCipher,
    *,
    expires_at: datetime,
    refresh_token: str | None = "refresh-1",
    scopes: list[str] | None = None,
) -> tuple[User, ConnectedAccount]:
    user = await _seed_google_account(
        session, cipher, expires_at=expires_at, refresh_token=refresh_token
    )
    account = await ConnectedAccountRepository(session, user.id).get_by_provider("google")
    assert account is not None
    account.granted_scopes = scopes if scopes is not None else [REQUIRED_SCOPE]
    await session.flush()
    return user, account


def _execution_service(
    session: AsyncSession, user_id: uuid.UUID, cipher: AesGcmTokenCipher, oauth: _StubOAuthClient
) -> GoogleTokenService:
    return GoogleTokenService(
        session,
        user_id,
        cipher,
        oauth,
        client_id="cid",
        client_secret="secret",
        now_factory=lambda: NOW,
    )


async def test_execution_exact_account_returns_token_when_everything_matches(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user, account = await _seed_google_account_for_execution(
        session, cipher, expires_at=NOW + timedelta(hours=1)
    )
    oauth = _StubOAuthClient()
    service = _execution_service(session, user.id, cipher, oauth)
    token = await service.get_valid_access_token_for_execution(
        user_id=user.id,
        connected_account_id=account.id,
        expected_provider="google",
        expected_authorisation_revision=account.authorisation_revision,
        required_scope=REQUIRED_SCOPE,
    )
    assert token == "access-old"
    assert oauth.calls == 0


async def test_execution_unknown_connected_account_id_is_rejected(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user, account = await _seed_google_account_for_execution(
        session, cipher, expires_at=NOW + timedelta(hours=1)
    )
    oauth = _StubOAuthClient()
    service = _execution_service(session, user.id, cipher, oauth)
    with pytest.raises(ApprovedExecutionContextChangedError):
        await service.get_valid_access_token_for_execution(
            user_id=user.id,
            connected_account_id=uuid.uuid4(),  # no such account
            expected_provider="google",
            expected_authorisation_revision=account.authorisation_revision,
            required_scope=REQUIRED_SCOPE,
        )
    assert oauth.calls == 0


async def test_execution_wrong_user_account_id_is_rejected(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    """A connected_account_id belonging to a DIFFERENT user must never be
    usable even by that user's own legitimate GoogleTokenService — the
    lookup requires id AND user_id to match, never id alone."""
    owner, owner_account = await _seed_google_account_for_execution(
        session, cipher, expires_at=NOW + timedelta(hours=1)
    )
    other_user = User(email=f"other-{uuid.uuid4()}@example.com", display_name="Other")
    session.add(other_user)
    await session.flush()

    oauth = _StubOAuthClient()
    service = _execution_service(session, other_user.id, cipher, oauth)
    with pytest.raises(ApprovedExecutionContextChangedError):
        await service.get_valid_access_token_for_execution(
            user_id=other_user.id,
            connected_account_id=owner_account.id,  # belongs to `owner`, not `other_user`
            expected_provider="google",
            expected_authorisation_revision=owner_account.authorisation_revision,
            required_scope=REQUIRED_SCOPE,
        )
    assert oauth.calls == 0
    del owner


async def test_execution_provider_mismatch_is_rejected(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user, account = await _seed_google_account_for_execution(
        session, cipher, expires_at=NOW + timedelta(hours=1)
    )
    oauth = _StubOAuthClient()
    service = _execution_service(session, user.id, cipher, oauth)
    with pytest.raises(ApprovedExecutionContextChangedError):
        await service.get_valid_access_token_for_execution(
            user_id=user.id,
            connected_account_id=account.id,
            expected_provider="synthetic",  # the account is actually "google"
            expected_authorisation_revision=account.authorisation_revision,
            required_scope=REQUIRED_SCOPE,
        )
    assert oauth.calls == 0


async def test_execution_inactive_account_is_rejected(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user, account = await _seed_google_account_for_execution(
        session, cipher, expires_at=NOW + timedelta(hours=1)
    )
    account.status = AccountStatus.disconnected
    await session.flush()
    oauth = _StubOAuthClient()
    service = _execution_service(session, user.id, cipher, oauth)
    with pytest.raises(ApprovedExecutionContextChangedError):
        await service.get_valid_access_token_for_execution(
            user_id=user.id,
            connected_account_id=account.id,
            expected_provider="google",
            expected_authorisation_revision=account.authorisation_revision,
            required_scope=REQUIRED_SCOPE,
        )
    assert oauth.calls == 0


async def test_execution_revision_mismatch_is_rejected(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user, account = await _seed_google_account_for_execution(
        session, cipher, expires_at=NOW + timedelta(hours=1)
    )
    oauth = _StubOAuthClient()
    service = _execution_service(session, user.id, cipher, oauth)
    with pytest.raises(ApprovedExecutionContextChangedError):
        await service.get_valid_access_token_for_execution(
            user_id=user.id,
            connected_account_id=account.id,
            expected_provider="google",
            expected_authorisation_revision=account.authorisation_revision + 1,
            required_scope=REQUIRED_SCOPE,
        )
    assert oauth.calls == 0


async def test_execution_scope_missing_is_rejected(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user, account = await _seed_google_account_for_execution(
        session, cipher, expires_at=NOW + timedelta(hours=1), scopes=["some.other.scope"]
    )
    oauth = _StubOAuthClient()
    service = _execution_service(session, user.id, cipher, oauth)
    with pytest.raises(ApprovedExecutionContextChangedError):
        await service.get_valid_access_token_for_execution(
            user_id=user.id,
            connected_account_id=account.id,
            expected_provider="google",
            expected_authorisation_revision=account.authorisation_revision,
            required_scope=REQUIRED_SCOPE,
        )
    assert oauth.calls == 0


async def test_execution_routine_refresh_preserves_revision_and_returns_fresh_token(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    user, account = await _seed_google_account_for_execution(
        session, cipher, expires_at=NOW + timedelta(seconds=30)
    )
    original_revision = account.authorisation_revision
    oauth = _StubOAuthClient(
        GoogleTokenResponse(
            access_token="access-refreshed",
            refresh_token=None,
            expires_in=3600,
            scope=REQUIRED_SCOPE,
            id_token=None,
        )
    )
    service = _execution_service(session, user.id, cipher, oauth)
    token = await service.get_valid_access_token_for_execution(
        user_id=user.id,
        connected_account_id=account.id,
        expected_provider="google",
        expected_authorisation_revision=account.authorisation_revision,
        required_scope=REQUIRED_SCOPE,
    )
    assert token == "access-refreshed"
    assert oauth.calls == 1

    refreshed_account = await ConnectedAccountRepository(session, user.id).get(account.id)
    assert refreshed_account is not None
    assert refreshed_account.authorisation_revision == original_revision
    assert cipher.decrypt(refreshed_account.encrypted_access_token) == "access-refreshed"


async def test_execution_invalid_grant_marks_revoked_not_context_changed(
    session: AsyncSession, cipher: AesGcmTokenCipher
) -> None:
    """A refresh rejected by Google (`invalid_grant`) is a distinct,
    already-controlled classification (`ReauthorisationRequiredError`) —
    not `ApprovedExecutionContextChangedError`, since the account/revision/
    scope all matched at the row-locked check; the failure happened later,
    during the refresh call itself."""
    user, account = await _seed_google_account_for_execution(
        session, cipher, expires_at=NOW + timedelta(seconds=30)
    )
    oauth = _StubOAuthClient(raises=InvalidGrantError("rejected"))
    service = _execution_service(session, user.id, cipher, oauth)
    with pytest.raises(ReauthorisationRequiredError):
        await service.get_valid_access_token_for_execution(
            user_id=user.id,
            connected_account_id=account.id,
            expected_provider="google",
            expected_authorisation_revision=account.authorisation_revision,
            required_scope=REQUIRED_SCOPE,
        )
    revoked_account = await ConnectedAccountRepository(session, user.id).get(account.id)
    assert revoked_account is not None
    assert revoked_account.status == AccountStatus.revoked
