"""fix course_teacher_avator to course_teacher_avatar

Revision ID: ce6996daf20a
Revises: f50666697df7
Create Date: 2025-04-12 16:07:20.761956

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "ce6996daf20a"
down_revision = "f50666697df7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ai_course", schema=None) as batch_op:
        batch_op.alter_column(
            "course_teacher_avator",
            new_column_name="course_teacher_avatar",
            existing_type=sa.String(length=255),
            existing_nullable=False,
            existing_server_default=text("''"),
        )


def downgrade():
    with op.batch_alter_table("ai_course", schema=None) as batch_op:
        batch_op.alter_column(
            "course_teacher_avatar",
            new_column_name="course_teacher_avator",
            existing_type=sa.String(length=255),
            existing_nullable=False,
            existing_server_default=text("''"),
        )
