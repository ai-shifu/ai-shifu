"""Add Google OAuth support to user table

Revision ID: 001_add_google_oauth
Revises:
Create Date: 2025-07-25 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "001_add_google_oauth"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Add google_id column to user_info table"""
    op.add_column(
        "user_info",
        sa.Column(
            "google_id",
            sa.String(255),
            nullable=True,
            unique=True,
            default=None,
            comment="Google OAuth ID",
        ),
    )


def downgrade():
    """Remove google_id column from user_info table"""
    op.drop_column("user_info", "google_id")
