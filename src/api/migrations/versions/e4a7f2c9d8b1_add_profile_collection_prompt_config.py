"""add profile collection prompt config

Revision ID: e4a7f2c9d8b1
Revises: d2f4a7c9b8e1
Create Date: 2026-05-22 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "e4a7f2c9d8b1"
down_revision = "d2f4a7c9b8e1"
branch_labels = None
depends_on = None


TABLE_NAME = "shifu_published_shifus"
COLUMN_NAME = "profile_collection_prompt_config"
DEFAULT_VALUE = "{}"


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(col.get("name") == column_name for col in columns)


def upgrade():
    if not _table_exists(TABLE_NAME):
        return
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    COLUMN_NAME,
                    sa.Text(),
                    nullable=True,
                    comment="Course-level profile collection prompt config JSON",
                )
            )
    op.execute(
        f"UPDATE {TABLE_NAME} SET {COLUMN_NAME} = '{DEFAULT_VALUE}' WHERE {COLUMN_NAME} IS NULL"
    )
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.alter_column(COLUMN_NAME, existing_type=sa.Text(), nullable=False)


def downgrade():
    if not _table_exists(TABLE_NAME):
        return
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        return
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.drop_column(COLUMN_NAME)
