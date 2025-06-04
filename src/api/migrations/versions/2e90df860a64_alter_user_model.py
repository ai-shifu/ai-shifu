"""alter user model

Revision ID: 2e90df860a64
Revises: 4562bef00e0d
Create Date: 2025-05-13 06:55:22.769617

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2e90df860a64"
down_revision = "4562bef00e0d"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_info", schema=None) as batch_op:
        batch_op.drop_column("default_model")


def downgrade():
    with op.batch_alter_table("user_info", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "default_model",
                sa.String(length=255),
                nullable=False,
                comment="Default model",
            )
        )
