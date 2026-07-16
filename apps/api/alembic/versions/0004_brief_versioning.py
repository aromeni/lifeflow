"""brief versioning and status (Stage 5: persisted brief versions + honest states).

Safe on existing databases: no writer of the briefs table existed before this
revision, so the NOT NULL additions apply to an empty table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("briefs", sa.Column("version", sa.Integer(), nullable=False))
    op.add_column("briefs", sa.Column("status", sa.String(length=20), nullable=False))
    op.create_unique_constraint(
        "uq_briefs_user_date_version", "briefs", ["user_id", "briefing_date", "version"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_briefs_user_date_version", "briefs", type_="unique")
    op.drop_column("briefs", "status")
    op.drop_column("briefs", "version")
