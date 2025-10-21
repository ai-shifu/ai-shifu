"""alter log struct

Revision ID: b99fb0d80bab
Revises: 335301139812
Create Date: 2025-10-21 13:57:04.842402

"""

from alembic import op
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = "b99fb0d80bab"
down_revision = "335301139812"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("shifu_log_draft_structs", schema=None) as batch_op:
        batch_op.alter_column("struct", type_=mysql.LONGTEXT)
    with op.batch_alter_table("shifu_log_published_structs", schema=None) as batch_op:
        batch_op.alter_column("struct", type_=mysql.LONGTEXT)


def downgrade():
    with op.batch_alter_table("shifu_log_draft_structs", schema=None) as batch_op:
        batch_op.alter_column("struct", type_=mysql.TEXT)
    with op.batch_alter_table("shifu_log_published_structs", schema=None) as batch_op:
        batch_op.alter_column("struct", type_=mysql.TEXT)
