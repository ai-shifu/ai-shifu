"""drop legacy order, variable, and active tables

Revision ID: 8f4c1a2b7d9e
Revises: 6b956399315e
Create Date: 2026-02-21 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "8f4c1a2b7d9e"
down_revision = "6b956399315e"
branch_labels = None
depends_on = None


LEGACY_TABLES = (
    # Legacy order source tables
    "ai_course_buy_record",
    "pingxx_order",
    # Legacy variable tables
    "profile_item_i18n",
    "profile_item_value",
    "profile_item",
    "user_profile",
    # Legacy activity tables
    "active_user_record",
    "active",
)


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    for table_name in LEGACY_TABLES:
        if _table_exists(table_name):
            op.drop_table(table_name)


def downgrade():
    # Irreversible on purpose: legacy tables are removed permanently.
    pass
