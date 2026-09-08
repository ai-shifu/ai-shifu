"""add user account cancellations.

Revision ID: b1c2d3e4f5a6
Revises: a90f19746a6f
Create Date: 2026-09-08 13:12:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "a90f19746a6f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_users",
        sa.Column(
            "cancelled_at",
            sa.DateTime(),
            nullable=True,
            comment="Account cancellation timestamp",
        ),
    )
    op.add_column(
        "user_users",
        sa.Column(
            "cancellation_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Account cancellation business identifier",
        ),
    )
    op.create_index(
        "ix_user_users_cancelled_at", "user_users", ["cancelled_at"], unique=False
    )
    op.create_index(
        "ix_user_users_cancellation_bid",
        "user_users",
        ["cancellation_bid"],
        unique=False,
    )

    op.create_table(
        "user_account_cancellations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "cancellation_bid",
            sa.String(length=36),
            nullable=False,
            comment="Cancellation business identifier",
        ),
        sa.Column(
            "user_bid",
            sa.String(length=32),
            nullable=False,
            comment="Cancelled user business identifier",
        ),
        sa.Column(
            "operator_user_bid",
            sa.String(length=32),
            nullable=False,
            server_default="",
            comment="Operator user business identifier",
        ),
        sa.Column(
            "actor_type",
            sa.String(length=32),
            nullable=False,
            server_default="operator",
            comment="Cancellation actor type",
        ),
        sa.Column(
            "reason",
            sa.Text(),
            nullable=False,
            comment="Operator-provided audit reason",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="completed",
            comment="Cancellation status",
        ),
        sa.Column(
            "idempotency_key",
            sa.String(length=128),
            nullable=False,
            comment="Cancellation request idempotency key",
        ),
        sa.Column(
            "retention_snapshot",
            sa.JSON(),
            nullable=True,
            comment="Privacy-safe cancellation decision snapshot",
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(),
            nullable=False,
            comment="Cancellation request timestamp",
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(),
            nullable=True,
            comment="Cancellation completion timestamp",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cancellation_bid",
            name="uq_user_account_cancellations_cancellation_bid",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_user_account_cancellations_idempotency_key",
        ),
        sa.UniqueConstraint("user_bid", name="uq_user_account_cancellations_user_bid"),
    )
    op.create_index(
        "ix_user_account_cancellations_cancellation_bid",
        "user_account_cancellations",
        ["cancellation_bid"],
        unique=False,
    )
    op.create_index(
        "ix_user_account_cancellations_operator_user_bid",
        "user_account_cancellations",
        ["operator_user_bid"],
        unique=False,
    )
    op.create_index(
        "ix_user_account_cancellations_status",
        "user_account_cancellations",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_user_account_cancellations_user_bid",
        "user_account_cancellations",
        ["user_bid"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_user_account_cancellations_user_bid",
        table_name="user_account_cancellations",
    )
    op.drop_index(
        "ix_user_account_cancellations_status",
        table_name="user_account_cancellations",
    )
    op.drop_index(
        "ix_user_account_cancellations_operator_user_bid",
        table_name="user_account_cancellations",
    )
    op.drop_index(
        "ix_user_account_cancellations_cancellation_bid",
        table_name="user_account_cancellations",
    )
    op.drop_table("user_account_cancellations")
    op.drop_index("ix_user_users_cancellation_bid", table_name="user_users")
    op.drop_index("ix_user_users_cancelled_at", table_name="user_users")
    op.drop_column("user_users", "cancellation_bid")
    op.drop_column("user_users", "cancelled_at")
