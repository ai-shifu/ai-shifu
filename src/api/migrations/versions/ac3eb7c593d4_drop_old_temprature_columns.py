"""drop old temprature columns

Revision ID: ac3eb7c593d4
Revises: 9c4403dc2f1f
Create Date: 2025-06-18 03:20:58.054786

"""

from alembic import op
import sqlalchemy as sa
from decimal import Decimal

# revision identifiers, used by Alembic.
revision = "ac3eb7c593d4"
down_revision = "9c4403dc2f1f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ai_lesson_script", schema=None) as batch_op:
        batch_op.drop_column("script_temprature")

    with op.batch_alter_table("ai_lesson", schema=None) as batch_op:
        batch_op.drop_column("lesson_default_temprature")

    with op.batch_alter_table("ai_course", schema=None) as batch_op:
        batch_op.drop_column("course_default_temprature")


def downgrade():
    with op.batch_alter_table("ai_lesson_script", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "script_temprature",
                sa.DECIMAL(10, 2),
                nullable=False,
                default=Decimal("0.3"),
                comment="Script Temprature",
            )
        )

    with op.batch_alter_table("ai_lesson", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "lesson_default_temprature",
                sa.DECIMAL(10, 2),
                nullable=False,
                default=Decimal("0.3"),
                comment="Lesson Default Temprature",
            )
        )

    with op.batch_alter_table("ai_course", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "course_default_temprature",
                sa.DECIMAL(10, 2),
                nullable=False,
                default=Decimal("0.3"),
                comment="Course Default Temprature",
            )
        )
