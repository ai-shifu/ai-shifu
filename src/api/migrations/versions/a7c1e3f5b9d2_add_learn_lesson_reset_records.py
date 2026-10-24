"""add learn lesson reset records.

Revision ID: a7c1e3f5b9d2
Revises: f569f2199973
Create Date: 2026-10-24 12:00:00.000000

Additive only: one new table, nothing existing is touched. Existing resets are not
backfilled; learner reset allowances start counting from the first reset after this
revision is applied.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "a7c1e3f5b9d2"
down_revision = "f569f2199973"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learn_lesson_reset_records",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column(
            "reset_record_bid",
            sa.String(length=36),
            nullable=False,
            comment="Reset record business identifier",
        ),
        sa.Column(
            "user_bid",
            sa.String(length=36),
            nullable=False,
            comment="User business identifier",
        ),
        sa.Column(
            "shifu_bid",
            sa.String(length=36),
            nullable=False,
            comment="Shifu business identifier",
        ),
        sa.Column(
            "outline_item_bid",
            sa.String(length=36),
            nullable=False,
            comment="Outline item business identifier",
        ),
        sa.Column(
            "progress_record_bid",
            sa.String(length=36),
            nullable=False,
            comment="Newest progress record retired by this reset, empty when only a session was retired",
        ),
        sa.Column(
            "preview_mode",
            sa.SmallInteger(),
            nullable=False,
            comment="Scope: 0=published learning, 1=draft preview",
        ),
        sa.Column(
            "counted",
            sa.SmallInteger(),
            nullable=False,
            comment="Quota: 1=counts against the learner limit, 0=exempt or preview",
        ),
        sa.Column(
            "request_id",
            sa.String(length=64),
            nullable=True,
            comment="Hashed client request id for idempotent retries",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted (refunded)",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="Creation time"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="Update time"),
        sa.PrimaryKeyConstraint("id"),
        comment="Learn lesson reset records",
    )
    op.create_index(
        "ix_learn_lesson_reset_records_reset_record_bid",
        "learn_lesson_reset_records",
        ["reset_record_bid"],
    )
    op.create_index(
        "ix_learn_lesson_reset_records_shifu_bid",
        "learn_lesson_reset_records",
        ["shifu_bid"],
    )
    op.create_index(
        "idx_learn_lesson_reset_records_scope",
        "learn_lesson_reset_records",
        ["user_bid", "shifu_bid", "outline_item_bid"],
    )
    op.create_index(
        "uq_learn_lesson_reset_records_request",
        "learn_lesson_reset_records",
        ["user_bid", "request_id"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "uq_learn_lesson_reset_records_request",
        table_name="learn_lesson_reset_records",
    )
    op.drop_index(
        "idx_learn_lesson_reset_records_scope",
        table_name="learn_lesson_reset_records",
    )
    op.drop_index(
        "ix_learn_lesson_reset_records_shifu_bid",
        table_name="learn_lesson_reset_records",
    )
    op.drop_index(
        "ix_learn_lesson_reset_records_reset_record_bid",
        table_name="learn_lesson_reset_records",
    )
    op.drop_table("learn_lesson_reset_records")
