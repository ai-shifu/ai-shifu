"""add demo shifu json file

Revision ID: a4d68cce5ce6
Revises: 21a3e778ef01
Create Date: 2025-11-12 14:41:07.381333

NOTE:
    Demo shifu import/update has been moved out of Alembic migrations and is now
    executed at container startup via `flask console update_demo_shifu`.
    This migration is intentionally kept as a no-op to preserve revision
    history and dependencies.

"""

# revision identifiers, used by Alembic.
revision = "a4d68cce5ce6"
down_revision = "21a3e778ef01"
branch_labels = None
depends_on = None


def upgrade():
    """No-op migration.

    Demo shifu import/update is now executed at container startup.
    """
    pass


def downgrade():
    pass
