"""Stage 7 Google integration: identity linking, sync cursors, execution outcomes.

Three additive changes (ADR 0003): `users.google_subject` is the sole
identity key for Google sign-in (D15); `connected_accounts.sync_cursors`
holds per-source-type incremental-sync cursors (D21); `action_executions.
outcome` carries the pending/succeeded/failed/uncertain state that Stage 6
deliberately left implicit (D16). Legacy execution rows are backfilled from
their existing `completed_at`/`error_code` shape so the new NOT NULL column
and CHECK constraint apply safely to development data.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_subject", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_users_google_subject", "users", ["google_subject"])

    op.add_column(
        "connected_accounts",
        sa.Column("sync_cursors", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.alter_column("connected_accounts", "sync_cursors", server_default=None)

    op.add_column("action_executions", sa.Column("outcome", sa.String(length=20), nullable=True))
    executions = sa.table(
        "action_executions",
        sa.column("id", sa.Uuid()),
        sa.column("completed_at", sa.DateTime(timezone=True)),
        sa.column("error_code", sa.String()),
        sa.column("outcome", sa.String()),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(executions.c.id, executions.c.completed_at, executions.c.error_code)
    ).mappings()
    for row in rows:
        if row["completed_at"] is None:
            outcome = "pending"
        elif row["error_code"] is not None:
            outcome = "failed"
        else:
            outcome = "succeeded"
        bind.execute(
            executions.update().where(executions.c.id == row["id"]).values(outcome=outcome)
        )
    op.alter_column("action_executions", "outcome", nullable=False)
    op.create_check_constraint(
        "ck_action_executions_outcome",
        "action_executions",
        "outcome IN ('pending', 'succeeded', 'failed', 'uncertain')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_action_executions_outcome", "action_executions", type_="check")
    op.drop_column("action_executions", "outcome")
    op.drop_column("connected_accounts", "sync_cursors")
    op.drop_constraint("uq_users_google_subject", "users", type_="unique")
    op.drop_column("users", "google_subject")
