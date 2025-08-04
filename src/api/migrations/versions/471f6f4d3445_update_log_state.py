"""update log state

Revision ID: 471f6f4d3445
Revises: 9cfc776b11f4
Create Date: 2025-08-04 08:43:22.063533

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "471f6f4d3445"
down_revision = "9cfc776b11f4"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE ai_course_lesson_attendscript SET status = 1 WHERE status = 0")


def downgrade():
    pass
