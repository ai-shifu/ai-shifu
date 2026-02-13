"""add position to learn_generated_audios

Revision ID: 4f1e9a6d2c8b
Revises: 6b956399315e
Create Date: 2026-02-13 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4f1e9a6d2c8b"
down_revision = "6b956399315e"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("learn_generated_audios", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "position",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
                comment="Audio unit position within generated block",
            )
        )
        batch_op.create_index(
            batch_op.f("ix_learn_generated_audios_generated_block_bid_position"),
            ["generated_block_bid", "position"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("learn_generated_audios", schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_learn_generated_audios_generated_block_bid_position")
        )
        batch_op.drop_column("position")
