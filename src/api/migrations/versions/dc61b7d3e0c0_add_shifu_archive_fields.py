"""add shifu archive fields

Revision ID: dc61b7d3e0c0
Revises: c9c92880fc67
Create Date: 2026-01-14 14:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "dc61b7d3e0c0"
down_revision = "c9c92880fc67"
branch_labels = None
depends_on = None


def upgrade():
    archived_column = sa.Column(
        "archived",
        sa.SmallInteger(),
        nullable=False,
        server_default=sa.text("0"),
        comment="Archive flag: 0=active, 1=archived",
    )
    archived_at_column = sa.Column(
        "archived_at",
        sa.DateTime(),
        nullable=True,
        comment="Archived timestamp",
    )

    for table_name in ("shifu_draft_shifus", "shifu_published_shifus"):
        op.add_column(table_name, archived_column.copy())
        op.add_column(table_name, archived_at_column.copy())


def downgrade():
    for table_name in ("shifu_draft_shifus", "shifu_published_shifus"):
        op.drop_column(table_name, "archived_at")
        op.drop_column(table_name, "archived")
