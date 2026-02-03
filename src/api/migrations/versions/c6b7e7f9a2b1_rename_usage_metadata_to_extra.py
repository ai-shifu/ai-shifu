"""rename usage metadata to extra

Revision ID: c6b7e7f9a2b1
Revises: b7c1d6e9f2a3
Create Date: 2026-02-03 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c6b7e7f9a2b1"
down_revision = "b7c1d6e9f2a3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("billing_usage_records", schema=None) as batch_op:
        batch_op.add_column(sa.Column("extra", sa.JSON(), nullable=True))

    op.execute("UPDATE billing_usage_records SET extra = metadata")

    with op.batch_alter_table("billing_usage_records", schema=None) as batch_op:
        batch_op.drop_column("metadata")


def downgrade():
    with op.batch_alter_table("billing_usage_records", schema=None) as batch_op:
        batch_op.add_column(sa.Column("metadata", sa.JSON(), nullable=True))

    op.execute("UPDATE billing_usage_records SET metadata = extra")

    with op.batch_alter_table("billing_usage_records", schema=None) as batch_op:
        batch_op.drop_column("extra")
