"""add use_learner_language to shifu tables

Revision ID: d7a8e2f1b3c9
Revises: b5f2d3a9c1e4
Create Date: 2026-01-21 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d7a8e2f1b3c9"
down_revision = "56b765541144"
branch_labels = None
depends_on = None


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
    for table_name in ("shifu_draft_shifus", "shifu_published_shifus"):
        if not _table_exists(table_name):
            continue
        if _column_exists(table_name, "use_learner_language"):
            continue
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "use_learner_language",
                    sa.SmallInteger(),
                    nullable=False,
                    server_default=sa.text("0"),
                    comment="Use learner language for output: 0=disabled (default), 1=enabled",
                )
            )


def downgrade():
    for table_name in ("shifu_draft_shifus", "shifu_published_shifus"):
        if not _table_exists(table_name):
            continue
        if not _column_exists(table_name, "use_learner_language"):
            continue
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.drop_column("use_learner_language")
