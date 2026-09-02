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
    bind = op.get_bind()
    user_users = sa.table("user_users", sa.column("avatar", sa.Text()))
    avatar_length = (
        sa.func.char_length(user_users.c.avatar)
        if bind.dialect.name == "mysql"
        else sa.func.length(user_users.c.avatar)
    )
    oversized_avatar = bind.execute(
        sa.select(sa.literal(1))
        .select_from(user_users)
        .where(avatar_length > 255)
        .limit(1)
    ).first()
    if oversized_avatar is not None:
        raise RuntimeError(
            "Cannot downgrade user_users.avatar to VARCHAR(255): "
            "at least one avatar exceeds 255 characters"
        )

    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.alter_column(
            "avatar",
            existing_type=sa.Text(),
            type_=sa.String(length=255),
            existing_nullable=False,
            existing_comment="User avatar",
        )
