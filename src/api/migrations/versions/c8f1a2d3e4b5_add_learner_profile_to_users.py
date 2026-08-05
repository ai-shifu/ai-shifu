"""add canonical learning profile to users

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


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        columns = inspector.get_columns(table_name)
    except (sa.exc.NoSuchTableError, sa.exc.DatabaseError):
        return False
    return any(column.get("name") == column_name for column in columns)


def upgrade():
    add_learner_profile = not _column_exists("user_users", "learner_profile")
    add_updated_at = not _column_exists("user_users", "learner_profile_updated_at")
    if not add_learner_profile and not add_updated_at:
        return

    with op.batch_alter_table("user_users", schema=None) as batch_op:
        if add_learner_profile:
            batch_op.add_column(
                sa.Column(
                    "learner_profile",
                    sa.Text(),
                    nullable=True,
                    comment="User-owned learning personalization profile",
                )
            )
        if add_updated_at:
            batch_op.add_column(
                sa.Column(
                    "learner_profile_updated_at",
                    sa.DateTime(),
                    nullable=True,
                    comment="Timestamp when the learning profile was last changed",
                )
            )


def downgrade():
    drop_learner_profile = _column_exists("user_users", "learner_profile")
    drop_updated_at = _column_exists("user_users", "learner_profile_updated_at")
    if not drop_learner_profile and not drop_updated_at:
        return

    with op.batch_alter_table("user_users", schema=None) as batch_op:
        if drop_updated_at:
            batch_op.drop_column("learner_profile_updated_at")
        if drop_learner_profile:
            batch_op.drop_column("learner_profile")
