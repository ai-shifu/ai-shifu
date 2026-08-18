"""add generation_prompt to learn_generated_blocks

Revision ID: b8d5f0a2c3e4
Revises: a7c4e9f1b2d3
Create Date: 2026-08-03 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b8d5f0a2c3e4"
down_revision = "a7c4e9f1b2d3"
branch_labels = None
depends_on = None

TABLE_NAME = "learn_generated_blocks"
COLUMN_NAME = "generation_prompt"


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        columns = inspector.get_columns(table_name)
    except Exception:
        return False
    return any(column["name"] == column_name for column in columns)


def upgrade():
    if not _table_exists(TABLE_NAME):
        return
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        return
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                COLUMN_NAME,
                sa.Text(),
                nullable=False,
                comment="Exact user message sent to the LLM when this block was generated",
            )
        )


def downgrade():
    if not _table_exists(TABLE_NAME):
        return
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        return
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.drop_column(COLUMN_NAME)
