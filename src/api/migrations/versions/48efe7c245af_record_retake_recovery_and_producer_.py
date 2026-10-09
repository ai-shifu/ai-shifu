"""Record retake recovery and producer completion

Revision ID: 48efe7c245af
Revises: 0a3b9866d338
Create Date: 2026-10-03 19:44:35.252531

"""

from alembic import op
import sqlalchemy as sa

revision = "48efe7c245af"
down_revision = "0a3b9866d338"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("lesson_retake_attempts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("producer_finished_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(sa.Column("recovery_data", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("lesson_retake_attempts", schema=None) as batch_op:
        batch_op.drop_column("recovery_data")
        batch_op.drop_column("producer_finished_at")
