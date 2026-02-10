"""add position to learn_generated_audios

Revision ID: 3c0f3a7b2c1a
Revises: 6b956399315e
Create Date: 2026-02-10 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "3c0f3a7b2c1a"
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
                comment="Audio part position within the generated block (0-based)",
            )
        )
        batch_op.create_index(
            batch_op.f("ix_learn_generated_audios_position"),
            ["position"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f(
                "ix_learn_generated_audios_generated_block_bid_position_status_deleted"
            ),
            ["generated_block_bid", "position", "status", "deleted"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("learn_generated_audios", schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f(
                "ix_learn_generated_audios_generated_block_bid_position_status_deleted"
            )
        )
        batch_op.drop_index(batch_op.f("ix_learn_generated_audios_position"))
        batch_op.drop_column("position")
