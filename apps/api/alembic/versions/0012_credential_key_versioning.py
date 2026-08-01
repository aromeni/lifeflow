"""Stage 11A Phase 4A: credential key-version tracking (F-P3-03).

Additive. Adds two nullable, non-secret columns to `connected_accounts`:

- `access_token_key_id` / `refresh_token_key_id` — the `key_id` recorded
  inside the matching ciphertext envelope's own `v1:<key_id>:...`/
  `v2:<key_id>:...` prefix, kept as a queryable column so the rotation
  service (`credential_rotation.py`) can select "rows not yet on the active
  key" with a plain indexed `WHERE`, without decrypting anything.

Existing rows are backfilled by parsing their already-stored envelope
strings — this never requires (and never has access to) `TOKEN_KEY`. A row
with no stored credential (`encrypted_access_token IS NULL`) is left with a
NULL key id, matching "no credential, no key" honestly.

Downgrade drops the two columns. This is safe: it only removes queryable
metadata this migration itself added — the ciphertext columns, which still
carry their own key id inside the envelope string, are never touched.
Downgrading loses the ability to select "rows needing rotation" by a plain
column filter until the columns are re-added and re-backfilled by re-running
this migration's upgrade step.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENVELOPE_KEY_ID_INDEX = 1  # "v1:<key_id>:...".split(":")[1]


def _parse_key_id(envelope: str | None) -> str | None:
    if envelope is None:
        return None
    parts = envelope.split(":")
    if len(parts) != 4 or parts[0] not in ("v1", "v2"):
        return None  # unrecognised shape — leave untagged rather than guess
    return parts[_ENVELOPE_KEY_ID_INDEX]


def upgrade() -> None:
    op.add_column(
        "connected_accounts", sa.Column("access_token_key_id", sa.String(length=40), nullable=True)
    )
    op.add_column(
        "connected_accounts", sa.Column("refresh_token_key_id", sa.String(length=40), nullable=True)
    )
    op.create_index(
        "ix_connected_accounts_access_token_key_id",
        "connected_accounts",
        ["access_token_key_id"],
        unique=False,
    )
    op.create_index(
        "ix_connected_accounts_refresh_token_key_id",
        "connected_accounts",
        ["refresh_token_key_id"],
        unique=False,
    )

    connection = op.get_bind()
    accounts = sa.table(
        "connected_accounts",
        sa.column("id", sa.Uuid()),
        sa.column("encrypted_access_token", sa.Text()),
        sa.column("encrypted_refresh_token", sa.Text()),
        sa.column("access_token_key_id", sa.String(length=40)),
        sa.column("refresh_token_key_id", sa.String(length=40)),
    )
    rows = connection.execute(
        sa.select(
            accounts.c.id, accounts.c.encrypted_access_token, accounts.c.encrypted_refresh_token
        )
    ).fetchall()
    for row in rows:
        access_key_id = _parse_key_id(row.encrypted_access_token)
        refresh_key_id = _parse_key_id(row.encrypted_refresh_token)
        if access_key_id is None and refresh_key_id is None:
            continue
        connection.execute(
            sa.update(accounts)
            .where(accounts.c.id == row.id)
            .values(access_token_key_id=access_key_id, refresh_token_key_id=refresh_key_id)
        )


def downgrade() -> None:
    op.drop_index("ix_connected_accounts_refresh_token_key_id", table_name="connected_accounts")
    op.drop_index("ix_connected_accounts_access_token_key_id", table_name="connected_accounts")
    op.drop_column("connected_accounts", "refresh_token_key_id")
    op.drop_column("connected_accounts", "access_token_key_id")
