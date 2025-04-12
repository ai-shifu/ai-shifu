"""fix: rename course_teacher_avator to course_teacher_avatar

Revision ID: f74a445
Revises: a7806e012c77
Create Date: 2025-04-12 13:42:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "f74a445"
down_revision = "a7806e012c77"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ai_course", schema=None) as batch_op:
        batch_op.alter_column(
            "course_teacher_avator",
            new_column_name="course_teacher_avatar",
            existing_type=sa.String(length=255),
            existing_nullable=False,
            existing_comment="Course teacher avatar",
            existing_server_default=sa.text("''"),
        )


def downgrade():
    with op.batch_alter_table("ai_course", schema=None) as batch_op:
        batch_op.alter_column(
            "course_teacher_avatar",
            new_column_name="course_teacher_avator",
            existing_type=sa.String(length=255),
            existing_nullable=False,
            existing_comment="Course teacher avatar",
            existing_server_default=sa.text("''"),
        )
