"""rerun demo shifu import after tts columns

Revision ID: 9f1183de9d1f
Revises: b5f2d3a9c1e4
Create Date: 2026-01-14 18:27:18.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "9f1183de9d1f"
down_revision = "b5f2d3a9c1e4"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade():
    from flask import current_app as app
    from flaskr.command.update_shifu_demo import update_demo_shifu

    if not _column_exists("shifu_draft_shifus", "tts_enabled"):
        return

    with app.app_context():
        update_demo_shifu(app)


def downgrade():
    pass
