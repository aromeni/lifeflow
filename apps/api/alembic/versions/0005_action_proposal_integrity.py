"""Stage 6 action proposal integrity, approvals, and execution snapshots.

The Stage 2 tables were deliberate skeletons with no application writer.
The backfill remains defensive for development databases: any legacy rows get
stable fingerprints, hashes, versions, expiries, and execution snapshots
before the new constraints become active.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-16
"""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _payload_hash(action_type: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"action_type": action_type, "payload": payload},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def upgrade() -> None:
    op.add_column("action_proposals", sa.Column("origin_brief_id", sa.Uuid(), nullable=True))
    op.add_column(
        "action_proposals", sa.Column("origin_fingerprint", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "action_proposals", sa.Column("payload_hash", sa.String(length=64), nullable=True)
    )
    op.add_column("action_proposals", sa.Column("version", sa.Integer(), nullable=True))
    op.add_column(
        "action_proposals", sa.Column("approved_action_type", sa.String(length=40), nullable=True)
    )
    op.add_column("action_proposals", sa.Column("approved_payload_json", sa.JSON(), nullable=True))
    op.add_column(
        "action_proposals",
        sa.Column("approved_payload_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "action_proposals",
        sa.Column("approved_binding_hash", sa.String(length=64), nullable=True),
    )
    op.add_column("action_proposals", sa.Column("approved_version", sa.Integer(), nullable=True))
    op.add_column(
        "action_proposals", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "action_proposals", sa.Column("user_edited_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "action_proposals", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("action_proposals", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column(
        "action_proposals",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "action_proposals",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    proposals = sa.table(
        "action_proposals",
        sa.column("id", sa.Uuid()),
        sa.column("action_type", sa.String()),
        sa.column("payload_json", sa.JSON()),
        sa.column("origin_fingerprint", sa.String()),
        sa.column("payload_hash", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("expires_at", sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    expires_at = datetime.now(UTC) + timedelta(days=7)
    rows = bind.execute(
        sa.select(proposals.c.id, proposals.c.action_type, proposals.c.payload_json)
    ).mappings()
    for row in rows:
        action_type = str(row["action_type"])
        payload = dict(row["payload_json"] or {})
        origin = hashlib.sha256(f"legacy|{row['id']}|{action_type}".encode()).hexdigest()
        bind.execute(
            proposals.update()
            .where(proposals.c.id == row["id"])
            .values(
                origin_fingerprint=origin,
                payload_hash=_payload_hash(action_type, payload),
                version=1,
                expires_at=expires_at,
            )
        )

    op.alter_column("action_proposals", "origin_fingerprint", nullable=False)
    op.alter_column("action_proposals", "payload_hash", nullable=False)
    op.alter_column("action_proposals", "version", nullable=False)
    op.alter_column("action_proposals", "expires_at", nullable=False)
    op.create_foreign_key(
        "fk_action_proposals_origin_brief",
        "action_proposals",
        "briefs",
        ["origin_brief_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_action_proposals_origin_brief_id",
        "action_proposals",
        ["origin_brief_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_action_proposals_user_origin",
        "action_proposals",
        ["user_id", "origin_fingerprint"],
    )
    op.create_check_constraint(
        "ck_action_proposals_action_type",
        "action_proposals",
        "action_type IN ('create_task', 'create_gmail_draft', 'create_calendar_event')",
    )
    op.create_check_constraint(
        "ck_action_proposals_risk",
        "action_proposals",
        "risk_level IN ('low', 'medium')",
    )
    op.create_check_constraint(
        "ck_action_proposals_status",
        "action_proposals",
        "status IN ('proposed', 'edited', 'approved', 'rejected', "
        "'executing', 'executed', 'failed', 'expired')",
    )
    op.create_check_constraint("ck_action_proposals_version", "action_proposals", "version >= 1")

    op.add_column(
        "action_executions",
        sa.Column("approved_action_type", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "action_executions", sa.Column("approved_proposal_version", sa.Integer(), nullable=True)
    )
    op.add_column("action_executions", sa.Column("executed_payload_json", sa.JSON(), nullable=True))
    op.add_column(
        "action_executions",
        sa.Column("executed_payload_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "action_executions",
        sa.Column("approval_binding_hash", sa.String(length=64), nullable=True),
    )

    executions = sa.table(
        "action_executions",
        sa.column("id", sa.Uuid()),
        sa.column("proposal_id", sa.Uuid()),
        sa.column("approved_action_type", sa.String()),
        sa.column("approved_proposal_version", sa.Integer()),
        sa.column("executed_payload_json", sa.JSON()),
        sa.column("executed_payload_hash", sa.String()),
        sa.column("approval_binding_hash", sa.String()),
    )
    legacy = bind.execute(
        sa.text(
            "SELECT e.id, p.action_type, p.payload_json, p.payload_hash "
            "FROM action_executions e JOIN action_proposals p ON p.id = e.proposal_id"
        )
    ).mappings()
    for row in legacy:
        payload = dict(row["payload_json"] or {})
        payload_hash = str(row["payload_hash"])
        binding = hashlib.sha256(f"{payload_hash}|1".encode("ascii")).hexdigest()
        bind.execute(
            executions.update()
            .where(executions.c.id == row["id"])
            .values(
                approved_action_type=str(row["action_type"]),
                approved_proposal_version=1,
                executed_payload_json=payload,
                executed_payload_hash=payload_hash,
                approval_binding_hash=binding,
            )
        )

    op.alter_column("action_executions", "approved_action_type", nullable=False)
    op.alter_column("action_executions", "approved_proposal_version", nullable=False)
    op.alter_column("action_executions", "executed_payload_json", nullable=False)
    op.alter_column("action_executions", "executed_payload_hash", nullable=False)
    op.alter_column("action_executions", "approval_binding_hash", nullable=False)
    op.create_unique_constraint(
        "uq_action_executions_proposal", "action_executions", ["proposal_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_action_executions_proposal", "action_executions", type_="unique")
    op.drop_column("action_executions", "approval_binding_hash")
    op.drop_column("action_executions", "executed_payload_hash")
    op.drop_column("action_executions", "executed_payload_json")
    op.drop_column("action_executions", "approved_proposal_version")
    op.drop_column("action_executions", "approved_action_type")

    op.drop_constraint("ck_action_proposals_version", "action_proposals", type_="check")
    op.drop_constraint("ck_action_proposals_status", "action_proposals", type_="check")
    op.drop_constraint("ck_action_proposals_risk", "action_proposals", type_="check")
    op.drop_constraint("ck_action_proposals_action_type", "action_proposals", type_="check")
    op.drop_constraint("uq_action_proposals_user_origin", "action_proposals", type_="unique")
    op.drop_index("ix_action_proposals_origin_brief_id", table_name="action_proposals")
    op.drop_constraint("fk_action_proposals_origin_brief", "action_proposals", type_="foreignkey")
    op.alter_column("action_proposals", "expires_at", nullable=True)
    op.drop_column("action_proposals", "updated_at")
    op.drop_column("action_proposals", "created_at")
    op.drop_column("action_proposals", "rejection_reason")
    op.drop_column("action_proposals", "rejected_at")
    op.drop_column("action_proposals", "user_edited_at")
    op.drop_column("action_proposals", "approved_at")
    op.drop_column("action_proposals", "approved_version")
    op.drop_column("action_proposals", "approved_binding_hash")
    op.drop_column("action_proposals", "approved_payload_hash")
    op.drop_column("action_proposals", "approved_payload_json")
    op.drop_column("action_proposals", "approved_action_type")
    op.drop_column("action_proposals", "version")
    op.drop_column("action_proposals", "payload_hash")
    op.drop_column("action_proposals", "origin_fingerprint")
    op.drop_column("action_proposals", "origin_brief_id")
