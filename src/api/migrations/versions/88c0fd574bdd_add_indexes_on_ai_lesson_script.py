"""Add indexes on ai_lesson_script

Revision ID: 88c0fd574bdd
Revises: 1fd178d512f2
Create Date: 2025-06-03 05:42:34.684450

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "88c0fd574bdd"
down_revision = "1fd178d512f2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ai_lesson_script", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_ai_lesson_script_lesson_status_idx"),
            ["lesson_id", "status", "script_index"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_ai_lesson_script_script_id"), ["script_index"], unique=False
        )


def downgrade():
    with op.batch_alter_table("ai_lesson_script", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ai_lesson_script_lesson_status_idx"))
        batch_op.drop_index(batch_op.f("ix_ai_lesson_script_script_id"))
