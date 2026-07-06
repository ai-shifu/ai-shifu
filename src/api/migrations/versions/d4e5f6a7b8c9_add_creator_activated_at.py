"""add creator activated at

Revision ID: d4e5f6a7b8c9
Revises: c6a4f8d9b2e1
Create Date: 2026-06-17 00:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "c6a4f8d9b2e1"
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
    if _column_exists("user_users", "creator_activated_at"):
        return

    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "creator_activated_at",
                sa.DateTime(),
                nullable=True,
                comment="Timestamp when creator access was first activated",
            )
        )


def downgrade():
    if not _column_exists("user_users", "creator_activated_at"):
        return

    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.drop_column("creator_activated_at")
