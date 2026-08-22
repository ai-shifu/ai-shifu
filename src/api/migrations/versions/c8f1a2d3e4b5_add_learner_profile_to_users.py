"""add canonical learning profile to users.

Revision ID: c8f1a2d3e4b5
Revises: b8d5f0a2c3e4
Create Date: 2026-08-03 07:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "c8f1a2d3e4b5"
down_revision = "b8d5f0a2c3e4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "learner_profile",
                sa.Text(),
                nullable=True,
                comment="User-owned learning personalization profile",
            )
        )
        batch_op.add_column(
            sa.Column(
                "learner_profile_updated_at",
                sa.DateTime(),
                nullable=True,
                comment="Timestamp when the learner profile was last changed",
            )
        )


def downgrade():
    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.drop_column("learner_profile_updated_at")
        batch_op.drop_column("learner_profile")
