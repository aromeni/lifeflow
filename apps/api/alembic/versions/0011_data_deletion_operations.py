"""Stage 9 Delivery Phase 2: durable deletion engine (ADR 0005 D61-D63).

Additive. Adds:

- `data_deletion_operations` — one durable, content-free record per
  destructive operation (imported-data deletion, retention enforcement,
  account deletion) processed by the shared engine. The partial unique index
  `uq_data_deletion_operations_active_scope` guarantees at most one *active*
  (previewed/pending/running) operation per (user, type, scope), so two
  equivalent preview/confirm requests can never create two concurrent
  destructive operations.
- account-deletion lifecycle columns on `users`: `account_state`
  (active/deletion_pending/deleted), `deleted_at`, and a unique random
  `deletion_subject_id` assigned at anonymisation. Keeping the terminal user
  row (rather than a hard delete) preserves the content-free audit/execution
  tombstones `AuditEvent.user_id` references under ON DELETE CASCADE.
- retention support indexes on terminal timestamps used by the daily
  retention scan.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE_STATES_PREDICATE = "state IN ('previewed', 'pending', 'running')"


def upgrade() -> None:
    # --- account-deletion lifecycle on users -----------------------------
    op.add_column(
        "users",
        sa.Column(
            "account_state",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deletion_subject_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint("uq_users_deletion_subject_id", "users", ["deletion_subject_id"])

    # --- durable deletion operations -------------------------------------
    op.create_table(
        "data_deletion_operations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation_type", sa.String(length=20), nullable=False),
        sa.Column("requester_type", sa.String(length=10), nullable=False),
        sa.Column(
            "source_account_id",
            sa.Uuid(),
            sa.ForeignKey("connected_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("scope_key", sa.String(length=80), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="previewed"),
        sa.Column("typed_confirmation_kind", sa.String(length=30), nullable=True),
        sa.Column("preview_counts_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("preserved_counts_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("deleted_counts_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("plan_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("plan_policy_version", sa.String(length=16), nullable=True),
        sa.Column("resume_cursor_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preview_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safe_error_code", sa.String(length=64), nullable=True),
        sa.Column("safe_error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "operation_type IN ('imported_data', 'retention', 'account_deletion')",
            name="ck_data_deletion_operations_type",
        ),
        sa.CheckConstraint(
            "requester_type IN ('user', 'system')",
            name="ck_data_deletion_operations_requester",
        ),
        sa.CheckConstraint(
            "state IN ('previewed', 'pending', 'running', 'succeeded', "
            "'partially_failed', 'failed', 'cancelled')",
            name="ck_data_deletion_operations_state",
        ),
        sa.CheckConstraint("version >= 1", name="ck_data_deletion_operations_version"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_data_deletion_operations_attempts"),
    )
    op.create_index(
        "ix_data_deletion_operations_user_id",
        "data_deletion_operations",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_data_deletion_operations_user_state",
        "data_deletion_operations",
        ["user_id", "state"],
        unique=False,
    )
    op.create_index(
        "ix_data_deletion_operations_type_state",
        "data_deletion_operations",
        ["operation_type", "state"],
        unique=False,
    )
    op.create_index(
        "uq_data_deletion_operations_active_scope",
        "data_deletion_operations",
        ["user_id", "operation_type", "scope_key"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE_STATES_PREDICATE),
    )

    # --- source-item import timestamp (snapshot boundary) ----------------
    # Backfills existing rows to the migration instant — they were all imported
    # before now, so any subsequently-scoped deletion correctly includes them.
    op.add_column(
        "source_items",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- retention support indexes on terminal timestamps ----------------
    op.create_index(
        "ix_source_items_retention_expires_at",
        "source_items",
        ["retention_expires_at"],
        unique=False,
    )
    op.create_index("ix_source_items_created_at", "source_items", ["created_at"], unique=False)
    op.create_index("ix_briefs_generated_at", "briefs", ["generated_at"], unique=False)
    op.create_index(
        "ix_scheduled_brief_runs_completed_at",
        "scheduled_brief_runs",
        ["completed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_scheduled_brief_runs_completed_at", table_name="scheduled_brief_runs")
    op.drop_index("ix_briefs_generated_at", table_name="briefs")
    op.drop_index("ix_source_items_created_at", table_name="source_items")
    op.drop_index("ix_source_items_retention_expires_at", table_name="source_items")
    op.drop_column("source_items", "created_at")

    op.drop_index("uq_data_deletion_operations_active_scope", table_name="data_deletion_operations")
    op.drop_index("ix_data_deletion_operations_type_state", table_name="data_deletion_operations")
    op.drop_index("ix_data_deletion_operations_user_state", table_name="data_deletion_operations")
    op.drop_index("ix_data_deletion_operations_user_id", table_name="data_deletion_operations")
    op.drop_table("data_deletion_operations")

    op.drop_constraint("uq_users_deletion_subject_id", "users", type_="unique")
    op.drop_column("users", "deletion_subject_id")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "account_state")
