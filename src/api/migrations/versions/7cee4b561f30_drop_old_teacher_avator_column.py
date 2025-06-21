"""drop old teacher_avator column

Revision ID: 7cee4b561f30
Revises: afa6fecf9698
Create Date: 2025-06-18 04:11:54.864178

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7cee4b561f30"
down_revision = "afa6fecf9698"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ai_course", schema=None) as batch_op:
        batch_op.drop_column("course_teacher_avator")


def downgrade():
    with op.batch_alter_table("ai_course", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "course_teacher_avator",
                sa.String(255),
                nullable=False,
                default="",
                comment="Course teacher avatar",
            )
        )
