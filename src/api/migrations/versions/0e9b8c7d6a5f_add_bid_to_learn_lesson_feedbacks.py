"""add bid to learn lesson feedback table

Revision ID: 0e9b8c7d6a5f
Revises: 4e7a1c9d2b6f
Create Date: 2026-03-09 21:05:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0e9b8c7d6a5f"
down_revision = "4e7a1c9d2b6f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("learn_lesson_feedbacks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "bid",
                sa.String(length=36),
                nullable=False,
                server_default=sa.text("''"),
                comment="Lesson feedback business identifier",
            )
        )
        batch_op.create_index(
            batch_op.f("ix_learn_lesson_feedbacks_bid"), ["bid"], unique=False
        )

    op.execute(
        "UPDATE learn_lesson_feedbacks "
        "SET bid = lesson_feedback_bid "
        "WHERE bid = '' OR bid IS NULL"
    )


def downgrade():
    with op.batch_alter_table("learn_lesson_feedbacks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_learn_lesson_feedbacks_bid"))
        batch_op.drop_column("bid")
