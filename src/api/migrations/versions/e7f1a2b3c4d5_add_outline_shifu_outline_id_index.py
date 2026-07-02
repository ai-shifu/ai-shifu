"""add (shifu_bid, outline_item_bid, id) index for draft outline

Revision ID: e7f1a2b3c4d5
Revises: d4e5f6a7b8c9
Create Date: 2026-07-02 12:30:00.000000

Adds an index whose id column directly follows the (shifu_bid,
outline_item_bid) prefix, so "latest version" lookups that order by id
without a deleted filter (notably the FOR UPDATE in save_shifu_mdflow) can
stop at the first index record and lock a single row instead of scanning and
locking the whole version range. This removes the deadlock observed under
concurrent saves of the same outline.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError


# revision identifiers, used by Alembic.
revision = "e7f1a2b3c4d5"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None

TABLE_NAME = "shifu_draft_outline_items"
INDEX_NAME = "ix_shifu_draft_outline_items_shifu_outline_id"
INDEX_COLUMNS = ["shifu_bid", "outline_item_bid", "id"]


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
