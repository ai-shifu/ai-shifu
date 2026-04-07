"""add is_operator to user_users

Revision ID: 1f2e3d4c5b6a
Revises: 7b3c5d9e1a2f
Create Date: 2026-04-04 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "1f2e3d4c5b6a"
down_revision = "7b3c5d9e1a2f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_operator",
                sa.SmallInteger(),
                nullable=False,
                server_default="0",
                comment="Operator flag: 0=regular user, 1=operator",
            )
        )
        batch_op.create_index(
            batch_op.f("ix_user_users_is_operator"),
            ["is_operator"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_users_is_operator"))
        batch_op.drop_column("is_operator")
