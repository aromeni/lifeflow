"""Stage 8 Phase 3: transparent inferred memory (ADR 0004 D52/D53/D55).

Adds `memory_items` (one row per user per closed registry key — the unique
constraint on `(user_id, memory_key)` is the final guard against two
conflicting active memories for the same fact) and `memory_evidence` (safe,
deduplicated references to the deliberate user actions that support an item;
the unique constraint on `(memory_item_id, source_proposal_id)` makes
recompute idempotent).

Both tables cascade from `users`, so account deletion removes all inferred
memory. `memory_evidence.source_proposal_id` is SET NULL (not CASCADE): if a
proposal is ever deleted, the evidence's short, safe derived value survives
for history and recompute tolerates the null.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("memory_key", sa.String(length=100), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="candidate"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "application_mode", sa.String(length=20), nullable=False, server_default="suggest_only"
        ),
        sa.Column("corresponding_preference_key", sa.String(length=100), nullable=True),
        sa.Column(
            "overridden_by_explicit", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('candidate', 'confirmed', 'dismissed', 'superseded', 'expired')",
            name="ck_memory_items_status",
        ),
        sa.CheckConstraint(
            "application_mode IN ('suggest_only')",
            name="ck_memory_items_application_mode",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_memory_items_confidence"
        ),
        sa.CheckConstraint("version >= 1", name="ck_memory_items_version"),
        sa.UniqueConstraint("user_id", "memory_key", name="uq_memory_items_user_key"),
    )
    op.create_index("ix_memory_items_user_id", "memory_items", ["user_id"], unique=False)

    op.create_table(
        "memory_evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "memory_item_id",
            sa.Uuid(),
            sa.ForeignKey("memory_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_type", sa.String(length=60), nullable=False),
        sa.Column(
            "source_proposal_id",
            sa.Uuid(),
            sa.ForeignKey("action_proposals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("derived_value", sa.String(length=100), nullable=False),
        sa.Column("reason_code", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "memory_item_id", "source_proposal_id", name="uq_memory_evidence_item_source"
        ),
    )
    op.create_index(
        "ix_memory_evidence_memory_item_id", "memory_evidence", ["memory_item_id"], unique=False
    )
    op.create_index("ix_memory_evidence_user_id", "memory_evidence", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_memory_evidence_user_id", table_name="memory_evidence")
    op.drop_index("ix_memory_evidence_memory_item_id", table_name="memory_evidence")
    op.drop_table("memory_evidence")
    op.drop_index("ix_memory_items_user_id", table_name="memory_items")
    op.drop_table("memory_items")
