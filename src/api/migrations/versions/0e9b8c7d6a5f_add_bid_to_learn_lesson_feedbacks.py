"""add learn lesson feedback table

Revision ID: 0e9b8c7d6a5f
Revises: f0c1e2d3a4b5
Create Date: 2026-03-09 21:05:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "0e9b8c7d6a5f"
down_revision = "f0c1e2d3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learn_lesson_feedbacks",
        sa.Column("id", mysql.BIGINT(), autoincrement=True, nullable=False),
        sa.Column(
            "bid",
            sa.String(length=36),
            nullable=False,
            server_default=sa.text("''"),
            comment="Lesson feedback business identifier",
        ),
        sa.Column(
            "lesson_feedback_bid",
            sa.String(length=36),
            nullable=False,
            comment="Lesson feedback business identifier",
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
            comment="Learn progress record business identifier",
        ),
        sa.Column(
            "user_bid",
            sa.String(length=36),
            nullable=False,
            comment="User business identifier",
        ),
        sa.Column(
            "score",
            sa.SmallInteger(),
            nullable=False,
            comment="Lesson score: 1-5",
        ),
        sa.Column(
            "comment",
            sa.Text(),
            nullable=False,
            comment="Optional feedback comment",
        ),
        sa.Column(
            "mode",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'read'"),
            comment="Submit mode: read or listen",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Deletion flag: 0=active, 1=deleted",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Learn lesson feedback records",
    )

    with op.batch_alter_table("learn_lesson_feedbacks", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_learn_lesson_feedbacks_bid"),
            ["bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_learn_lesson_feedbacks_lesson_feedback_bid"),
            ["lesson_feedback_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_learn_lesson_feedbacks_shifu_bid"),
            ["shifu_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_learn_lesson_feedbacks_outline_item_bid"),
            ["outline_item_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_learn_lesson_feedbacks_progress_record_bid"),
            ["progress_record_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_learn_lesson_feedbacks_user_bid"),
            ["user_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_learn_lesson_feedbacks_mode"),
            ["mode"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_learn_lesson_feedbacks_deleted"),
            ["deleted"],
            unique=False,
        )
        batch_op.create_index(
            "idx_learn_lesson_feedback_unique_active",
            ["shifu_bid", "outline_item_bid", "user_bid", "deleted"],
            unique=True,
        )


def downgrade():
    with op.batch_alter_table("learn_lesson_feedbacks", schema=None) as batch_op:
        batch_op.drop_index("idx_learn_lesson_feedback_unique_active")
        batch_op.drop_index(batch_op.f("ix_learn_lesson_feedbacks_deleted"))
        batch_op.drop_index(batch_op.f("ix_learn_lesson_feedbacks_mode"))
        batch_op.drop_index(batch_op.f("ix_learn_lesson_feedbacks_user_bid"))
        batch_op.drop_index(batch_op.f("ix_learn_lesson_feedbacks_progress_record_bid"))
        batch_op.drop_index(batch_op.f("ix_learn_lesson_feedbacks_outline_item_bid"))
        batch_op.drop_index(batch_op.f("ix_learn_lesson_feedbacks_shifu_bid"))
        batch_op.drop_index(batch_op.f("ix_learn_lesson_feedbacks_lesson_feedback_bid"))
        batch_op.drop_index(batch_op.f("ix_learn_lesson_feedbacks_bid"))

    op.drop_table("learn_lesson_feedbacks")
