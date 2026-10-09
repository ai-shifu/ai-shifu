"""add deployment scoped lesson retake ledger

Revision ID: 0a3b9866d338
Revises: fde432bceab4
Create Date: 2026-10-03 19:30:31.897098

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0a3b9866d338"
down_revision = "fde432bceab4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade only the retake tables; existing learning data is untouched."""
    op.create_table(
        "course_retake_policies",
        sa.Column("namespace", sa.String(length=32), nullable=False),
        sa.Column("shifu_bid", sa.String(length=36), nullable=False),
        sa.Column("lesson_limit", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("namespace", "shifu_bid"),
    )
    op.create_table(
        "lesson_retake_attempts",
        sa.Column("attempt_id", sa.String(length=64), nullable=False),
        sa.Column("namespace", sa.String(length=32), nullable=False),
        sa.Column("shifu_bid", sa.String(length=36), nullable=False),
        sa.Column("user_bid", sa.String(length=36), nullable=False),
        sa.Column("outline_bid", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("producer_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("attempt_id"),
    )
    with op.batch_alter_table("lesson_retake_attempts", schema=None) as batch_op:
        batch_op.create_index(
            "idx_retake_balance",
            ["namespace", "shifu_bid", "user_bid", "outline_bid", "state"],
            unique=False,
        )

    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade only the retake tables; existing learning data is untouched."""
    with op.batch_alter_table("lesson_retake_attempts", schema=None) as batch_op:
        batch_op.drop_index("idx_retake_balance")
    op.drop_table("lesson_retake_attempts")
    op.drop_table("course_retake_policies")
    # ### end Alembic commands ###
