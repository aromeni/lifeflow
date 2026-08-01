"""ConnectedAccountService — the secure storage path for OAuth tokens — and
GoogleTokenService, the refresh-concurrency-controlled access-token source
for Stage 7's real Google calls (ADR 0003 D18/D19/D20).

Tokens pass through the TokenCipher before they touch the database; there is
no code path that stores plaintext (threat model T1).
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.audit import record_audit_event
from lifeflow_api.execution_context import ApprovedExecutionContextChangedError
from lifeflow_api.failure_taxonomy import classify_exception
from lifeflow_api.google.errors import InvalidGrantError
from lifeflow_api.google.oauth import GoogleOAuthClient, GoogleTokenResponse
from lifeflow_api.models import AccountStatus, ConnectedAccount
from lifeflow_api.repositories import ConnectedAccountRepository
from lifeflow_api.retry import retry_read
from lifeflow_api.security.credential_context import (
    ACCESS_TOKEN_FIELD,
    REFRESH_TOKEN_FIELD,
    credential_context,
)
from lifeflow_api.security.token_cipher import TokenCipher, peek_key_id

REFRESH_SAFETY_MARGIN = timedelta(minutes=2)
NowFactory = Callable[[], datetime]


class ReauthorisationRequiredError(Exception):
    """The stored grant was rejected by Google (revoked/expired refresh
    token). The account has already been marked AccountStatus.revoked;
    callers must surface a clear re-authorisation state, never a bare 500
    (AC-J2.3)."""


def _field_context(account: ConnectedAccount, field: str) -> str:
    return credential_context(
        connected_account_id=account.id,
        user_id=account.user_id,
        provider=account.provider,
        field=field,
    )


def _encrypt_field(
    cipher: TokenCipher, account: ConnectedAccount, field: str, plaintext: str
) -> None:
    """Encrypt `plaintext` for `field` on `account` and write both the
    ciphertext and its key-id column together, so the two can never drift
    apart (Stage 11A Phase 4A)."""
    envelope = cipher.encrypt(plaintext, context=_field_context(account, field))
    key_id = peek_key_id(envelope)
    if field == ACCESS_TOKEN_FIELD:
        account.encrypted_access_token = envelope
        account.access_token_key_id = key_id
    else:
        account.encrypted_refresh_token = envelope
        account.refresh_token_key_id = key_id


def _decrypt_field(
    cipher: TokenCipher, account: ConnectedAccount, field: str, envelope: str
) -> str:
    return cipher.decrypt(envelope, context=_field_context(account, field))


class ConnectedAccountService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, cipher: TokenCipher) -> None:
        self._session = session
        self._user_id = user_id
        self._cipher = cipher
        self._accounts = ConnectedAccountRepository(session, user_id)

    async def store_tokens(
        self,
        *,
        provider: str,
        access_token: str,
        refresh_token: str | None,
        granted_scopes: list[str],
        expires_at: datetime | None,
    ) -> ConnectedAccount:
        """Create or update the account for `provider`, encrypting both
        tokens. `refresh_token=None` means "unchanged" — Google only returns
        a refresh token on the initial grant (`access_type=offline&
        prompt=consent`); every other response (including an ordinary
        reconnect) omits it, and the previously stored encrypted value must
        never be cleared just because this call didn't receive a new one
        (ADR 0003 D18)."""
        account = await self._accounts.get_by_provider(provider)
        if account is None:
            account = ConnectedAccount(
                user_id=self._user_id, provider=provider, authorisation_revision=1
            )
            self._accounts.add(account)
            # `account.id`'s `default=uuid.uuid4` is applied at flush, not at
            # construction — flushing here (Stage 11A Phase 4A) guarantees
            # `account.id` is real before `_encrypt_field` derives the
            # encryption context from it, so the context used to encrypt
            # below always matches the context a later decrypt will derive
            # from this same, now-persisted, row.
            await self._session.flush()
            event_type = "account.connected"
        else:
            # Every call here represents a fresh consent grant — new
            # connect, reconnect, or a materially different scope grant
            # (this method is only ever reached from the OAuth callback
            # route, never from a silent token refresh) — so the
            # authorisation revision always advances (Stage 7 remediation
            # blocker #1). This is what makes an approval bound to the
            # account's *previous* revision go stale automatically.
            account.authorisation_revision += 1
            event_type = "account.tokens_refreshed"

        _encrypt_field(self._cipher, account, ACCESS_TOKEN_FIELD, access_token)
        if refresh_token is not None:
            _encrypt_field(self._cipher, account, REFRESH_TOKEN_FIELD, refresh_token)
        account.granted_scopes = granted_scopes
        account.expires_at = expires_at
        account.status = AccountStatus.active

        await self._session.flush()
        record_audit_event(
            self._session,
            user_id=self._user_id,
            actor=f"user:{self._user_id}",
            event_type=event_type,
            entity_type="connected_account",
            entity_id=str(account.id),
            metadata={
                "provider": provider,
                "scope_count": len(granted_scopes),
                "authorisation_revision": account.authorisation_revision,
            },
        )
        await self._session.flush()
        return account

    async def get_access_token(self, provider: str) -> str | None:
        """Decrypt and return the current access token, if any."""
        account = await self._accounts.get_by_provider(provider)
        if account is None or account.encrypted_access_token is None:
            return None
        return _decrypt_field(
            self._cipher, account, ACCESS_TOKEN_FIELD, account.encrypted_access_token
        )

    async def disconnect(
        self, provider: str, *, oauth_client: GoogleOAuthClient | None = None
    ) -> bool:
        """Mark the account disconnected and drop stored tokens. Best-effort
        revokes the token with Google first — a failure to reach Google must
        never block the user's local disconnect (D20)."""
        account = await self._accounts.get_by_provider(provider)
        if account is None:
            return False
        if oauth_client is not None and account.encrypted_refresh_token is not None:
            await oauth_client.revoke_token(
                token=_decrypt_field(
                    self._cipher, account, REFRESH_TOKEN_FIELD, account.encrypted_refresh_token
                )
            )
        account.status = AccountStatus.disconnected
        account.encrypted_access_token = None
        account.encrypted_refresh_token = None
        account.access_token_key_id = None
        account.refresh_token_key_id = None
        await self._session.flush()
        record_audit_event(
            self._session,
            user_id=self._user_id,
            actor=f"user:{self._user_id}",
            event_type="account.disconnected",
            entity_type="connected_account",
            entity_id=str(account.id),
            metadata={"provider": provider},
        )
        await self._session.flush()
        return True


class GoogleTokenService:
    """The single path real Google callers use to obtain a valid access
    token. Row-locks the account so concurrent callers never race a refresh
    (D19); a rejected refresh token marks the account revoked and raises a
    typed error rather than surfacing Google's rejection directly (D20).

    `get_valid_access_token_for_execution` (Stage 7 focused remediation) is
    the exact-account variant real action executors use: it re-verifies the
    proposal's approved account identity/authorisation/scope atomically
    under the same row lock that acquires the token, closing the
    post-durability-commit TOCTOU window `get_valid_access_token` alone left
    open (that method only ever checks "is *a* `(user, provider)` account
    active", never which specific authorisation was approved)."""

    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        cipher: TokenCipher,
        oauth_client: GoogleOAuthClient,
        *,
        client_id: str,
        client_secret: str,
        now_factory: NowFactory | None = None,
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._cipher = cipher
        self._oauth = oauth_client
        self._client_id = client_id
        self._client_secret = client_secret
        self._accounts = ConnectedAccountRepository(session, user_id)
        self._now = now_factory or (lambda: datetime.now(UTC))

    @property
    def user_id(self) -> uuid.UUID:
        return self._user_id

    async def get_valid_access_token(self, provider: str) -> str:
        account = await self._accounts.get_by_provider(provider, for_update=True)
        if account is None or account.status != AccountStatus.active:
            raise ReauthorisationRequiredError(f"No active {provider} account is connected.")
        return await self._decrypt_or_refresh(account, provider=provider)

    async def get_valid_access_token_for_execution(
        self,
        *,
        user_id: uuid.UUID,
        connected_account_id: uuid.UUID,
        expected_provider: str,
        expected_authorisation_revision: int,
        required_scope: str,
    ) -> str:
        """Selects the account by BOTH `connected_account_id` and `user_id`
        under `SELECT ... FOR UPDATE` — never merely by `(user_id,
        provider)` — and verifies, under that same lock, that it still
        exactly matches what was approved: correct owner, provider exactly
        `google`, status active, `authorisation_revision` unchanged, and
        `required_scope` still granted. Any mismatch raises
        `ApprovedExecutionContextChangedError` before any token is decrypted
        or refreshed — no substitution, no fallback, no Google HTTP call.

        Once this method returns, the caller must use the returned token
        directly; it must not look the account up again.

        `populate_existing()` is required, not optional: `execute()` already
        loaded this exact row earlier in the same session (`accounts =
        await self._accounts.list()`, before the durability commit), and
        this session's `expire_on_commit=False` configuration means that
        cached copy survives the commit unexpired. Without
        `populate_existing()`, SQLAlchemy's identity map would hand back
        those stale in-memory attribute values for a row it already knows
        about — even though the row lock below is real at the database
        level — silently defeating this exact check against a concurrent
        `authorisation_revision`/scope change."""
        result = await self._session.execute(
            select(ConnectedAccount)
            .where(
                ConnectedAccount.id == connected_account_id,
                ConnectedAccount.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        account = result.scalar_one_or_none()
        if (
            account is None
            or account.provider != expected_provider
            or account.status != AccountStatus.active
            or account.authorisation_revision != expected_authorisation_revision
            or required_scope not in account.granted_scopes
        ):
            raise ApprovedExecutionContextChangedError(
                "The approved account, authorisation, or scope changed since approval."
            )
        return await self._decrypt_or_refresh(account, provider=expected_provider)

    async def _decrypt_or_refresh(self, account: ConnectedAccount, *, provider: str) -> str:
        """Shared by both token-acquisition paths: return the current
        access token if it is still comfortably valid, otherwise refresh it
        under the row lock the caller already holds. A refresh never touches
        `authorisation_revision` (only a genuine consent grant via
        `ConnectedAccountService.store_tokens` does that) — a routine
        refresh must never invalidate an approval bound to that revision."""
        now = self._now()
        if (
            account.encrypted_access_token is not None
            and account.expires_at is not None
            and account.expires_at - now > REFRESH_SAFETY_MARGIN
        ):
            return _decrypt_field(
                self._cipher, account, ACCESS_TOKEN_FIELD, account.encrypted_access_token
            )
        if account.encrypted_refresh_token is None:
            raise ReauthorisationRequiredError(f"No refresh token stored for {provider}.")
        refresh_token = _decrypt_field(
            self._cipher, account, REFRESH_TOKEN_FIELD, account.encrypted_refresh_token
        )
        try:

            async def _refresh() -> GoogleTokenResponse:
                return await self._oauth.refresh_access_token(
                    client_id=self._client_id,
                    client_secret=self._client_secret,
                    refresh_token=refresh_token,
                )

            # Stage 9 Delivery Phase 5: OAuth token refresh is safe to retry
            # a bounded number of times — it is idempotent by the OAuth 2.0
            # refresh-grant contract (RFC 6749 §6): each call either returns
            # a fresh access token or fails, never a duplicate side effect.
            # A retryable failure here (`GoogleTransientError`) is
            # classified by `failure_taxonomy`, exactly like every other
            # Google call; `InvalidGrantError` below is untouched and never
            # retried (the refresh token itself is rejected, not transient).
            token_response = await retry_read(
                _refresh,
                is_retryable=lambda exc: classify_exception(exc).retryable,
            )
        except InvalidGrantError as exc:
            account.status = AccountStatus.revoked
            account.encrypted_access_token = None
            await self._session.flush()
            record_audit_event(
                self._session,
                user_id=self._user_id,
                actor="system:google-token",
                event_type="account.revoked",
                entity_type="connected_account",
                entity_id=str(account.id),
                metadata={"provider": provider},
            )
            await self._session.flush()
            raise ReauthorisationRequiredError(
                f"Google rejected the refresh token for {provider}; reconnect required."
            ) from exc
        _encrypt_field(self._cipher, account, ACCESS_TOKEN_FIELD, token_response.access_token)
        # A refresh response commonly omits refresh_token — never clear the
        # stored one just because this call didn't receive a new one (D18).
        if token_response.refresh_token is not None:
            _encrypt_field(self._cipher, account, REFRESH_TOKEN_FIELD, token_response.refresh_token)
        account.expires_at = now + timedelta(seconds=token_response.expires_in)
        await self._session.flush()
        record_audit_event(
            self._session,
            user_id=self._user_id,
            actor="system:google-token",
            event_type="account.tokens_refreshed",
            entity_type="connected_account",
            entity_id=str(account.id),
            metadata={"provider": provider},
        )
        await self._session.flush()
        return token_response.access_token
