"""add default listen mode setting.

Revision ID: a9c3d5e7f1b2
Revises: f9a2b3c4d5e6
Create Date: 2026-08-18 13:18:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "a9c3d5e7f1b2"
down_revision = "f9a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "shifu_draft_shifus",
        sa.Column(
            "default_listen_mode_enabled",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
            comment="Default learner mode to listen when TTS is enabled",
        ),
    )
    op.add_column(
        "shifu_published_shifus",
        sa.Column(
            "default_listen_mode_enabled",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
            comment="Default learner mode to listen when TTS is enabled",
        ),
    )


def downgrade():
    op.drop_column("shifu_published_shifus", "default_listen_mode_enabled")
    op.drop_column("shifu_draft_shifus", "default_listen_mode_enabled")
