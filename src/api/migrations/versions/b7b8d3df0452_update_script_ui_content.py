"""update script ui content from continue to empty string

Revision ID: b7b8d3df0452
Revises: f50666697df7
Create Date: 2025-04-21 02:30:10.286887

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b7b8d3df0452"
down_revision = "f50666697df7"
branch_labels = None
depends_on = None


def upgrade():
    ai_lesson_script_table = sa.table('ai_lesson_script',
                                      sa.column('script_ui_content', sa.String))
    op.execute(
        ai_lesson_script_table.update().
        where(ai_lesson_script_table.c.script_ui_content == '继续').
        values(script_ui_content='')
    )


def downgrade():
    # Downgrade logic is not necessary.
    # The old code works with empty string as well.
    pass
