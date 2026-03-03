"""add composite index for draft outline lookup

Revision ID: f0c1e2d3a4b5
Revises: 3ef04a9b5d37
Create Date: 2026-03-03 16:30:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError


# revision identifiers, used by Alembic.
revision = "f0c1e2d3a4b5"
down_revision = "3ef04a9b5d37"
branch_labels = None
depends_on = None

TABLE_NAME = "shifu_draft_outline_items"
INDEX_NAME = "ix_shifu_draft_outline_items_shifu_outline_deleted_id"
INDEX_COLUMNS = ["shifu_bid", "outline_item_bid", "deleted", "id"]


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        indexes = inspector.get_indexes(table_name)
    except SQLAlchemyError:
        return False
    return any(index.get("name") == index_name for index in indexes)


def upgrade():
    if not _table_exists(TABLE_NAME):
        return
    if _index_exists(TABLE_NAME, INDEX_NAME):
        return

    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.create_index(INDEX_NAME, INDEX_COLUMNS, unique=False)


def downgrade():
    if not _table_exists(TABLE_NAME):
        return
    if not _index_exists(TABLE_NAME, INDEX_NAME):
        return

    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.drop_index(INDEX_NAME)
