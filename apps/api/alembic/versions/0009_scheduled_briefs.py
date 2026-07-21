"""Stage 8 Phase 2: the scheduled daily brief (ADR 0004 D47-D50).

Adds `scheduled_brief_runs` (one row per user per local calendar date; the
unique constraint on `(user_id, local_brief_date)` is the final duplicate
guard, independent of anything the queue does) and two columns on `briefs`:
`generation_trigger` ("manual" | "scheduled") and `scheduled_run_id` (a
unique, nullable back-reference so a crashed-and-retried worker can find an
already-generated brief for a run instead of creating a duplicate).

The two tables reference each other (`scheduled_brief_runs.brief_id` ->
`briefs.id`, `briefs.scheduled_run_id` -> `scheduled_brief_runs.id`), so the
`briefs` side is added after `scheduled_brief_runs` exists — a plain
sequential order in this script, not a real circularity concern for
Alembic. (The ORM's declarative metadata, used directly by
`Base.metadata.create_all` in tests, needs `use_alter` on that same column
for the same reason — see `models.py`.)

Existing brief rows predate scheduling entirely and default to
`generation_trigger='manual'`, `scheduled_run_id=NULL` — accurate, since
every brief generated before this migration was in fact manual.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_brief_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("local_brief_date", sa.Date(), nullable=False),
        sa.Column("scheduled_for_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone_snapshot", sa.String(length=64), nullable=False),
        sa.Column("briefing_time_snapshot", sa.String(length=5), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("queue_job_id", sa.String(length=160), nullable=True),
        sa.Column(
            "brief_id",
            sa.Uuid(),
            sa.ForeignKey("briefs.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')",
            name="ck_scheduled_brief_runs_status",
        ),
        sa.UniqueConstraint(
            "user_id", "local_brief_date", name="uq_scheduled_brief_runs_user_date"
        ),
    )
    op.create_index(
        "ix_scheduled_brief_runs_user_id", "scheduled_brief_runs", ["user_id"], unique=False
    )

    op.add_column(
        "briefs",
        sa.Column(
            "generation_trigger", sa.String(length=20), nullable=False, server_default="manual"
        ),
    )
    op.alter_column("briefs", "generation_trigger", server_default=None)
    op.add_column(
        "briefs",
        sa.Column("scheduled_run_id", sa.Uuid(), nullable=True),
    )
    op.create_unique_constraint("uq_briefs_scheduled_run_id", "briefs", ["scheduled_run_id"])
    op.create_foreign_key(
        "fk_briefs_scheduled_run_id",
        "briefs",
        "scheduled_brief_runs",
        ["scheduled_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_briefs_scheduled_run_id", "briefs", type_="foreignkey")
    op.drop_constraint("uq_briefs_scheduled_run_id", "briefs", type_="unique")
    op.drop_column("briefs", "scheduled_run_id")
    op.drop_column("briefs", "generation_trigger")
    op.drop_index("ix_scheduled_brief_runs_user_id", table_name="scheduled_brief_runs")
    op.drop_table("scheduled_brief_runs")
