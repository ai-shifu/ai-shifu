"""add learn generated element active lookup indexes

Revision ID: 7b3c5d9e1a2f
Revises: 4a1f6c8e9b2d
Create Date: 2026-03-30 18:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7b3c5d9e1a2f"
down_revision = "4a1f6c8e9b2d"
branch_labels = None
depends_on = None

TABLE_NAME = "learn_generated_elements"
INDEX_DEFINITIONS = {
    "ix_lge_active_lookup_element_bid": [
        "run_session_bid",
        "event_type",
        "deleted",
        "status",
        "element_bid",
        "generated_block_bid",
        "id",
    ],
    "ix_lge_active_lookup_target_element_bid": [
        "run_session_bid",
        "event_type",
        "deleted",
        "status",
        "target_element_bid",
        "generated_block_bid",
        "id",
    ],
}


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(index.get("name") == index_name for index in indexes)


def upgrade():
    for index_name, columns in INDEX_DEFINITIONS.items():
        if _index_exists(TABLE_NAME, index_name):
            continue
        op.create_index(index_name, TABLE_NAME, columns, unique=False)


def downgrade():
    for index_name in reversed(list(INDEX_DEFINITIONS.keys())):
        if _index_exists(TABLE_NAME, index_name):
            op.drop_index(index_name, table_name=TABLE_NAME)
