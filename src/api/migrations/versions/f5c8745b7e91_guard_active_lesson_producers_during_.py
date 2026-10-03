"""Guard active lesson producers during retakes

Revision ID: f5c8745b7e91
Revises: 48efe7c245af
Create Date: 2026-10-03 20:03:35.271890

"""

from alembic import op
import sqlalchemy as sa

revision = "f5c8745b7e91"
down_revision = "48efe7c245af"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "lesson_retake_runs",
        sa.Column("namespace", sa.String(length=32), nullable=False),
        sa.Column("shifu_bid", sa.String(length=36), nullable=False),
        sa.Column("user_bid", sa.String(length=36), nullable=False),
        sa.Column("outline_bid", sa.String(length=36), nullable=False),
        sa.Column("producer_id", sa.String(length=36), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("repair_log", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("namespace", "shifu_bid", "user_bid", "outline_bid"),
    )


def downgrade():
    op.drop_table("lesson_retake_runs")
