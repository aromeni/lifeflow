"""Stage 11A Phase 4A (F-P3-03): the credential key-rotation service.

An internal, operator-only batch process — never a public API route, never
reachable from a user-controlled identifier (§7/§45-046 of the governing
task). It moves `ConnectedAccount` credential rows from a legacy key to the
active key one bounded batch at a time, safely alongside concurrent token
refreshes and account deletions, and is fully resumable if interrupted.

Design:

- Selection is `SELECT ... FOR UPDATE SKIP LOCKED` — a row a concurrent
  `GoogleTokenService` refresh is already holding is simply left for the
  next batch, never blocked on or corrupted.
- A row is migrated by decrypting each stored field under whichever key the
  ring resolves (active or legacy) and re-encrypting it under the active
  key, always producing a `v2`, context-bound envelope — closing both the
  key-rotation gap and the cross-account-binding gap in the same pass.
- A field whose key id is unknown to the ring (already retired, or never
  configured) is left untouched and the row is reported BLOCKED, never
  deleted and never marked migrated.
- Nothing here ever returns, logs, or persists plaintext or key material —
  only bounded counts flow to the caller and to `credential_key_rotation_total`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from lifeflow_api.metrics import credential_key_rotation_total
from lifeflow_api.models import ConnectedAccount
from lifeflow_api.security.credential_context import (
    ACCESS_TOKEN_FIELD,
    REFRESH_TOKEN_FIELD,
    credential_context,
)
from lifeflow_api.security.token_cipher import TokenCipherError, TokenKeyRing


@dataclass
class RotationBatchResult:
    """Bounded, content-free counts — safe to log or expose to an operator."""

    migrated: int = 0
    skipped_current: int = 0
    blocked: int = 0
    blocked_account_ids: list[str] = field(default_factory=list)

    @property
    def processed(self) -> int:
        return self.migrated + self.skipped_current + self.blocked


def _select_candidates(
    key_ring: TokenKeyRing, *, batch_size: int
) -> Select[tuple[ConnectedAccount]]:
    active_id = key_ring.active_key_id
    access_stale = ConnectedAccount.access_token_key_id.isnot(None) & (
        ConnectedAccount.access_token_key_id != active_id
    )
    refresh_stale = ConnectedAccount.refresh_token_key_id.isnot(None) & (
        ConnectedAccount.refresh_token_key_id != active_id
    )
    return (
        select(ConnectedAccount)
        .where(access_stale | refresh_stale)
        .order_by(ConnectedAccount.id)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )


def _migrate_field(key_ring: TokenKeyRing, account: ConnectedAccount, field_name: str) -> bool:
    """Returns True if this field was migrated, False if it was already
    current or absent. Raises TokenCipherError if the stored key is unknown
    to the ring — the caller classifies that row as BLOCKED."""
    is_access = field_name == ACCESS_TOKEN_FIELD
    envelope_attr = "encrypted_access_token" if is_access else "encrypted_refresh_token"
    key_id_attr = "access_token_key_id" if is_access else "refresh_token_key_id"
    envelope = getattr(account, envelope_attr)
    current_key_id = getattr(account, key_id_attr)
    if envelope is None or current_key_id is None:
        return False
    if not key_ring.needs_rotation(current_key_id):
        return False
    context = credential_context(
        connected_account_id=account.id,
        user_id=account.user_id,
        provider=account.provider,
        field=field_name,
    )
    plaintext = key_ring.decrypt(envelope, context=context)
    new_envelope = key_ring.encrypt(plaintext, context=context)
    setattr(account, envelope_attr, new_envelope)
    setattr(account, key_id_attr, key_ring.active_key_id)
    return True


async def rotate_batch(
    session: AsyncSession, key_ring: TokenKeyRing, *, batch_size: int = 50
) -> RotationBatchResult:
    """Migrate up to `batch_size` rows in one transaction. The caller commits
    (or rolls back) — an interruption before commit loses nothing beyond
    this batch's work, which the next invocation simply picks up again
    (resumable by construction, never partially-marked-migrated)."""
    result = RotationBatchResult()
    query = _select_candidates(key_ring, batch_size=batch_size)
    rows = (await session.execute(query)).scalars().all()
    for account in rows:
        try:
            access_migrated = _migrate_field(key_ring, account, ACCESS_TOKEN_FIELD)
            refresh_migrated = _migrate_field(key_ring, account, REFRESH_TOKEN_FIELD)
        except TokenCipherError:
            result.blocked += 1
            result.blocked_account_ids.append(str(account.id))
            credential_key_rotation_total.labels(outcome="blocked").inc()
            continue
        if access_migrated or refresh_migrated:
            result.migrated += 1
            credential_key_rotation_total.labels(outcome="migrated").inc()
        else:
            result.skipped_current += 1
            credential_key_rotation_total.labels(outcome="skipped_current").inc()
    await session.flush()
    return result


async def dry_run_inventory(session: AsyncSession, key_ring: TokenKeyRing) -> dict[str, int]:
    """Counts of rows needing rotation, by their current (pre-migration) key
    id, without locking or modifying anything."""
    active_id = key_ring.active_key_id
    rows = (
        await session.execute(
            select(ConnectedAccount.access_token_key_id, ConnectedAccount.refresh_token_key_id)
        )
    ).all()
    counts: dict[str, int] = {}
    for access_key_id, refresh_key_id in rows:
        for key_id in (access_key_id, refresh_key_id):
            if key_id is not None and key_id != active_id:
                counts[key_id] = counts.get(key_id, 0) + 1
    return counts


async def verify_key_retirement_safe(session: AsyncSession, key_id: str) -> bool:
    """True only if zero rows reference `key_id` in either key-version
    column — the sole condition under which retiring that key from the
    configured key ring is safe."""
    result = await session.execute(
        select(ConnectedAccount.id)
        .where(
            (ConnectedAccount.access_token_key_id == key_id)
            | (ConnectedAccount.refresh_token_key_id == key_id)
        )
        .limit(1)
    )
    return result.first() is None


@dataclass
class ConnectionGateReport:
    """Bounded, content-free counts for the Phase 4B pre-connection gate
    (governing-instruction §3): no Google account may be connected while any
    stored credential field remains outside the active v2 key. Every count
    here comes from the non-secret key-version columns only — nothing is
    decrypted or displayed to produce this report."""

    unversioned: int = 0
    """Rows with a stored envelope but no key-version id recorded at all —
    would indicate a write path that bypassed key-id bookkeeping; expected
    to always be zero given the migration backfill and the encrypt helpers."""
    legacy_known: int = 0
    """Field-references on a legacy key this ring can still read and
    migrate — the ordinary, expected pre-rotation state."""
    legacy_unknown: int = 0
    """Field-references on a key id this ring does not hold (already
    retired, or never configured) — would block migration and must be
    resolved before any key can be retired or any new account connected."""

    @property
    def clear_to_connect(self) -> bool:
        return self.unversioned == 0 and self.legacy_known == 0 and self.legacy_unknown == 0


async def credential_connection_gate(
    session: AsyncSession, key_ring: TokenKeyRing
) -> ConnectionGateReport:
    """The authoritative Phase 4B pre-connection check: every stored
    credential field must already be on the active v2 key before a Google
    account may be connected, so the legacy v1 format (which lacks
    owner/account/field AAD binding) never has to coexist with a live
    connection. Callers must fail closed when `clear_to_connect` is False."""
    report = ConnectionGateReport()
    rows = (
        await session.execute(
            select(
                ConnectedAccount.encrypted_access_token,
                ConnectedAccount.access_token_key_id,
                ConnectedAccount.encrypted_refresh_token,
                ConnectedAccount.refresh_token_key_id,
            )
        )
    ).all()
    active_id = key_ring.active_key_id
    legacy_ids = key_ring.legacy_key_ids
    for access_envelope, access_key_id, refresh_envelope, refresh_key_id in rows:
        for envelope, key_id in (
            (access_envelope, access_key_id),
            (refresh_envelope, refresh_key_id),
        ):
            if envelope is None:
                continue
            if key_id is None:
                report.unversioned += 1
            elif key_id == active_id:
                continue
            elif key_id in legacy_ids:
                report.legacy_known += 1
            else:
                report.legacy_unknown += 1
    return report


__all__ = [
    "ConnectionGateReport",
    "RotationBatchResult",
    "credential_connection_gate",
    "dry_run_inventory",
    "rotate_batch",
    "verify_key_retirement_safe",
]
