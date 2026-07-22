"""Stage 7 remediation: bind approval to an execution-context snapshot.

Adds `connected_accounts.authorisation_revision` (a monotonic counter bumped
on every connector consent grant — new connect, reconnect, or a materially
different scope grant — never on an ordinary access-token refresh) and the
immutable approved-execution-context snapshot columns on `action_proposals`
(independent-review blocker #1): `approved_execution_mode`,
`approved_provider`, `approved_connected_account_id`,
`approved_authorisation_revision`, `approved_required_scope`,
`approved_source_account_id`, `approved_execution_context_hash`.

Existing `approved` rows predate execution-context binding entirely, so
backfilling a snapshot for them would mean guessing at security-relevant
state that was never actually captured. They are deliberately left with a
NULL snapshot instead: `ActionPolicyEngine.validate_execution` treats an
incomplete snapshot as `approval_missing` and refuses to execute, so any
proposal approved before this migration simply requires fresh approval
under the new binding — never a silent guess.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "connected_accounts",
        sa.Column(
            "authorisation_revision", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
    )
    op.alter_column("connected_accounts", "authorisation_revision", server_default=None)

    op.add_column(
        "action_proposals",
        sa.Column("approved_execution_mode", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "action_proposals", sa.Column("approved_provider", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "action_proposals",
        sa.Column("approved_connected_account_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "action_proposals",
        sa.Column("approved_authorisation_revision", sa.Integer(), nullable=True),
    )
    op.add_column(
        "action_proposals",
        sa.Column("approved_required_scope", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "action_proposals",
        sa.Column("approved_source_account_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "action_proposals",
        sa.Column("approved_execution_context_hash", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_action_proposals_approved_connected_account_id",
        "action_proposals",
        "connected_accounts",
        ["approved_connected_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_action_proposals_approved_source_account_id",
        "action_proposals",
        "connected_accounts",
        ["approved_source_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_action_proposals_approved_execution_mode",
        "action_proposals",
        "approved_execution_mode IN ('simulation', 'real')",
    )

    # Any row already `approved` under the old (unbound) scheme has no
    # execution-context snapshot to migrate — clear its approval so it
    # falls back through the ordinary "requires fresh approval" path
    # instead of being stuck `approved` with an incomplete snapshot.
    op.execute(
        """
        UPDATE action_proposals
        SET status = 'edited',
            approved_action_type = NULL,
            approved_payload_json = NULL,
            approved_payload_hash = NULL,
            approved_binding_hash = NULL,
            approved_version = NULL,
            approved_at = NULL
        WHERE status = 'approved'
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_action_proposals_approved_execution_mode", "action_proposals", type_="check"
    )
    op.drop_constraint(
        "fk_action_proposals_approved_source_account_id", "action_proposals", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_action_proposals_approved_connected_account_id", "action_proposals", type_="foreignkey"
    )
    op.drop_column("action_proposals", "approved_execution_context_hash")
    op.drop_column("action_proposals", "approved_source_account_id")
    op.drop_column("action_proposals", "approved_required_scope")
    op.drop_column("action_proposals", "approved_authorisation_revision")
    op.drop_column("action_proposals", "approved_connected_account_id")
    op.drop_column("action_proposals", "approved_provider")
    op.drop_column("action_proposals", "approved_execution_mode")
    op.drop_column("connected_accounts", "authorisation_revision")
