"""add password_hash to user_auth_credentials

Revision ID: f1a2b3c4d5e6
Revises: d7a8e2f1b3c9
Create Date: 2026-02-13 17:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "d7a8e2f1b3c9"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        columns = inspector.get_columns(table_name)
    except Exception:
        return False
    return any(column["name"] == column_name for column in columns)


def upgrade():
    table_name = "user_auth_credentials"
    if not _table_exists(table_name):
        return
    if _column_exists(table_name, "password_hash"):
        return
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "password_hash",
                sa.String(255),
                nullable=True,
                comment="bcrypt password hash",
            )
        )


def downgrade():
    table_name = "user_auth_credentials"
    if not _table_exists(table_name):
        return
    if not _column_exists(table_name, "password_hash"):
        return
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        batch_op.drop_column("password_hash")
