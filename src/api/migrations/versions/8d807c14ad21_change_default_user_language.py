"""change default user language from zh-CN to en-US

Revision ID: 8d807c14ad21
Revises: d2c6607d312a
Create Date: 2025-09-16 06:08:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "8d807c14ad21"
down_revision = "d2c6607d312a"
branch_labels = None
depends_on = None


def upgrade():
    # Change the default value for user_language column in user_info table
    op.alter_column(
        "user_info",
        "user_language",
        existing_type=sa.String(30),
        server_default="en-US",
        existing_nullable=True,
    )


def downgrade():
    # Revert the default value back to zh-CN
    op.alter_column(
        "user_info",
        "user_language",
        existing_type=sa.String(30),
        server_default="zh-CN",
        existing_nullable=True,
    )
