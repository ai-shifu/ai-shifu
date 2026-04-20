"""add ask_provider_config to shifu draft/published tables

Revision ID: e1b2c3d4e5f6
Revises: 0e9b8c7d6a5f
Create Date: 2026-03-04 15:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e1b2c3d4e5f6"
down_revision = "0e9b8c7d6a5f"
branch_labels = None
depends_on = None


TABLES = ("shifu_draft_shifus", "shifu_published_shifus")
COLUMN_NAME = "ask_provider_config"
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
    for table_name in TABLES:
        if not _table_exists(table_name):
            continue
        if not _column_exists(table_name, COLUMN_NAME):
            with op.batch_alter_table(table_name, schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column(
                        COLUMN_NAME,
                        sa.Text(),
                        nullable=True,
                        comment=(
                            "Ask provider config JSON, e.g. "
                            '{"provider":"llm","mode":"provider_then_llm","config":{}}'
                        ),
                    )
                )
        op.execute(
            f"UPDATE {table_name} SET {COLUMN_NAME} = '{DEFAULT_VALUE}' WHERE {COLUMN_NAME} IS NULL"
        )
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.alter_column(COLUMN_NAME, existing_type=sa.Text(), nullable=False)


def downgrade():
    for table_name in TABLES:
        if not _table_exists(table_name):
            continue
        if not _column_exists(table_name, COLUMN_NAME):
            continue
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.drop_column(COLUMN_NAME)
