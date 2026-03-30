"""add api_key field to user_users table

Revision ID: b596b767bde5
Revises: e1b2c3d4e5f6
Create Date: 2026-03-28 05:50:47.416996

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b596b767bde5"
down_revision = "e1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "api_key",
                sa.String(length=64),
                nullable=False,
                server_default="",
                comment="Open API key for external partner integration",
            )
        )
        batch_op.create_index(
            batch_op.f("ix_user_users_api_key"), ["api_key"], unique=False
        )


def downgrade():
    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_users_api_key"))
        batch_op.drop_column("api_key")
