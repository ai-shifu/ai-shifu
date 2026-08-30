"""Add first-party course visitors.

Revision ID: 8527c3bbd6a0
Revises: e9a1b2c3d4f5
Create Date: 2026-08-30 09:45:29.502025
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "8527c3bbd6a0"
down_revision = "e9a1b2c3d4f5"
branch_labels = None
depends_on = None

TABLE_NAME = "learn_course_visitors"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column(
            "shifu_bid",
            sa.String(length=32),
            nullable=False,
            comment="Shifu business identifier",
        ),
        sa.Column(
            "user_bid",
            sa.String(length=32),
            nullable=False,
            comment="User business identifier",
        ),
        sa.Column(
            "first_visited_at",
            sa.DateTime(),
            nullable=False,
            comment="First eligible visit timestamp",
        ),
        sa.Column(
            "last_visited_at",
            sa.DateTime(),
            nullable=False,
            comment="Most recent eligible visit timestamp",
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
            "shifu_bid",
            "user_bid",
            name="uk_learn_course_visitors_shifu_user",
        ),
        comment="First-party course visitors by registered learner",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_learn_course_visitors_shifu_last_visit",
        TABLE_NAME,
        ["shifu_bid", "last_visited_at"],
        unique=False,
    )
    op.create_index(
        "ix_learn_course_visitors_user_bid",
        TABLE_NAME,
        ["user_bid"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_learn_course_visitors_user_bid", table_name=TABLE_NAME)
    op.drop_index(
        "ix_learn_course_visitors_shifu_last_visit",
        table_name=TABLE_NAME,
    )
    op.drop_table(TABLE_NAME)
