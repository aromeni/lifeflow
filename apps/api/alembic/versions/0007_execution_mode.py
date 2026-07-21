"""Stage 7 remediation: persist which path actually executed an action.

`action_executions.execution_mode` ('simulation'/'real') is set once, at
creation, and never recomputed later — so a historical execution record stays
truthful even after the user's connected accounts change (independent-review
blocker #3). Every execution row created before this migration ran through
the (only-ever-wired) simulated path, so backfilling `'simulation'` is exact,
not a guess.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "action_executions",
        sa.Column("execution_mode", sa.String(length=20), nullable=True),
    )
    op.execute("UPDATE action_executions SET execution_mode = 'simulation'")
    op.alter_column("action_executions", "execution_mode", nullable=False)
    op.create_check_constraint(
        "ck_action_executions_execution_mode",
        "action_executions",
        "execution_mode IN ('simulation', 'real')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_action_executions_execution_mode", "action_executions", type_="check")
    op.drop_column("action_executions", "execution_mode")
