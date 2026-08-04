"""add course management lookup indexes

Revision ID: c4f6a8b0d2e3
Revises: b8d5f0a2c3e4
Create Date: 2026-08-04 12:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4f6a8b0d2e3"
down_revision = "b8d5f0a2c3e4"
branch_labels = None
depends_on = None


INDEXES = (
    (
        "ai_course_auth",
        "ix_ai_course_auth_user_status_course",
        ["user_id", "status", "course_id"],
    ),
    (
        "shifu_draft_shifus",
        "ix_shifu_draft_shifus_creator_deleted_bid",
        ["created_user_bid", "deleted", "shifu_bid"],
    ),
    (
        "shifu_draft_shifus",
        "ix_shifu_draft_shifus_bid_deleted_id",
        ["shifu_bid", "deleted", "id"],
    ),
    (
        "shifu_published_shifus",
        "ix_shifu_published_shifus_creator_deleted_bid",
        ["created_user_bid", "deleted", "shifu_bid"],
    ),
    (
        "shifu_published_shifus",
        "ix_shifu_published_shifus_bid_deleted_id",
        ["shifu_bid", "deleted", "id"],
    ),
    (
        "shifu_draft_outline_items",
        "ix_shifu_draft_outline_items_shifu_deleted_updated_id",
        ["shifu_bid", "deleted", "updated_at", "id"],
    ),
    (
        "shifu_published_outline_items",
        "ix_shifu_published_outline_items_shifu_deleted_updated_id",
        ["shifu_bid", "deleted", "updated_at", "id"],
    ),
)


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(index.get("name") == index_name for index in indexes)


def upgrade():
    for table_name, index_name, columns in INDEXES:
        if not _table_exists(table_name):
            continue
        if _index_exists(table_name, index_name):
            continue
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.create_index(index_name, columns, unique=False)


def downgrade():
    for table_name, index_name, _columns in reversed(INDEXES):
        if not _table_exists(table_name):
            continue
        if not _index_exists(table_name, index_name):
            continue
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.drop_index(index_name)
