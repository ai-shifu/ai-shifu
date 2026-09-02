"""Expand user avatar URL storage.

Revision ID: 6d568133dd29
Revises: a1b2c3d4e5f6
Create Date: 2026-09-02 08:44:01.595336

"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "6d568133dd29"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.alter_column(
            "avatar",
            existing_type=sa.String(length=255),
            type_=sa.Text(),
            existing_nullable=False,
            existing_comment="User avatar",
        )


def downgrade():
    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.alter_column(
            "avatar",
            existing_type=sa.Text(),
            type_=sa.String(length=255),
            existing_nullable=False,
            existing_comment="User avatar",
        )
