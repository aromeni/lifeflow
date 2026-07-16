"""ConnectedAccountService — the secure storage path for OAuth tokens.

Tokens pass through the TokenCipher before they touch the database; there is
no code path that stores plaintext (threat model T1). The real Google OAuth
flow (Stage 7) will call this service; Stage 2 proves the path with tests.
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.audit import record_audit_event
from lifeflow_api.models import AccountStatus, ConnectedAccount
from lifeflow_api.repositories import ConnectedAccountRepository
from lifeflow_api.security.token_cipher import TokenCipher


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
        """Create or update the account for `provider`, encrypting both tokens."""
        account = await self._accounts.get_by_provider(provider)
        if account is None:
            account = ConnectedAccount(user_id=self._user_id, provider=provider)
            self._accounts.add(account)
            event_type = "account.connected"
        else:
            event_type = "account.tokens_refreshed"

        account.encrypted_access_token = self._cipher.encrypt(access_token)
        account.encrypted_refresh_token = (
            self._cipher.encrypt(refresh_token) if refresh_token else None
        )
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
            metadata={"provider": provider, "scope_count": len(granted_scopes)},
        )
        await self._session.flush()
        return account

    async def get_access_token(self, provider: str) -> str | None:
        """Decrypt and return the current access token, if any."""
        account = await self._accounts.get_by_provider(provider)
        if account is None or account.encrypted_access_token is None:
            return None
        return self._cipher.decrypt(account.encrypted_access_token)

    async def disconnect(self, provider: str) -> bool:
        """Mark the account disconnected and drop stored tokens."""
        account = await self._accounts.get_by_provider(provider)
        if account is None:
            return False
        account.status = AccountStatus.disconnected
        account.encrypted_access_token = None
        account.encrypted_refresh_token = None
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
