"""add session metadata to user token.

Revision ID: a3f9c1d05b28
Revises: e9a1b2c3d4f5
Create Date: 2026-08-30 21:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a3f9c1d05b28"
down_revision = "e9a1b2c3d4f5"
branch_labels = None
depends_on = None


# Every column is added NOT NULL with an empty default so existing rows stay
# valid: sessions issued before this change simply have no metadata to show.
_COLUMNS = (
    sa.Column(
        "session_bid",
        sa.String(length=36),
        nullable=False,
        server_default="",
        comment="Public session identifier, safe to expose (the token is not)",
    ),
    sa.Column(
        "source",
        sa.String(length=32),
        nullable=False,
        server_default="",
        comment="How the session was created, for example web or cli",
    ),
    sa.Column(
        "device_name",
        sa.String(length=64),
        nullable=False,
        server_default="",
        comment="Device name reported at sign-in, display only",
    ),
    sa.Column(
        "device_os",
        sa.String(length=64),
        nullable=False,
        server_default="",
        comment="Operating system reported at sign-in, display only",
    ),
    sa.Column(
        "created_ip",
        sa.String(length=64),
        nullable=False,
        server_default="",
        comment="Address the session was created from, display only",
    ),
)


def upgrade() -> None:
    """Add session metadata columns and the lookup indexes they need."""
    with op.batch_alter_table("user_token") as batch_op:
        for column in _COLUMNS:
            batch_op.add_column(column)
    # Listing a user's sessions and revoking one by its public id are both
    # lookups this table never had an index for.
    op.create_index("ix_user_token_user_id", "user_token", ["user_id"])
    op.create_index("ix_user_token_session_bid", "user_token", ["session_bid"])


def downgrade() -> None:
    """Remove the session metadata columns and their indexes."""
    op.drop_index("ix_user_token_session_bid", table_name="user_token")
    op.drop_index("ix_user_token_user_id", table_name="user_token")
    with op.batch_alter_table("user_token") as batch_op:
        for column in reversed(_COLUMNS):
            batch_op.drop_column(column.name)
