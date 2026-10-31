"""use contact identifiers for local administrators

Revision ID: 207321e55031
Revises: b8e4a1d3c9f0
Create Date: 2026-10-26 04:26:09.534835 UTC

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "207321e55031"
down_revision = "b8e4a1d3c9f0"
branch_labels = None
depends_on = None


def upgrade():
    # Autogenerate proposed DROP username / ADD identifier. Rename instead so
    # existing local credentials retain their exact user and credential mapping.
    with op.batch_alter_table("user_local_admin_accounts", schema=None) as batch_op:
        batch_op.alter_column(
            "username",
            new_column_name="identifier",
            existing_type=sa.String(length=64),
            type_=sa.String(length=255),
            existing_nullable=False,
        )
        batch_op.add_column(
            sa.Column(
                "identifier_kind",
                sa.String(length=16),
                server_default="legacy_username",
                nullable=False,
            )
        )


def downgrade():
    # Earlier code only accepts local names, even when an email fits 64 bytes.
    # Refuse before DDL rather than truncate or strand contact-based accounts.
    if op.get_context().as_sql:
        raise RuntimeError("Local contact downgrade requires an online account check.")
    incompatible = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM user_local_admin_accounts "
                "WHERE identifier_kind != 'legacy_username' OR length(identifier) > 64 LIMIT 1"
            )
        )
        .first()
    )
    if incompatible is not None:
        raise RuntimeError(
            "Cannot downgrade contact administrator accounts. Preserve compatible "
            "local login or migrate these accounts before downgrading."
        )
    with op.batch_alter_table("user_local_admin_accounts", schema=None) as batch_op:
        batch_op.drop_column("identifier_kind")
        batch_op.alter_column(
            "identifier",
            new_column_name="username",
            existing_type=sa.String(length=255),
            type_=sa.String(length=64),
            existing_nullable=False,
        )
