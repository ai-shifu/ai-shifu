"""add session metadata to user token.

Revision ID: a3f9c1d05b28
Revises: e9a1b2c3d4f5
Create Date: 2026-08-30 21:30:00.000000
"""

from __future__ import annotations

import datetime
import uuid

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

    # Sessions that already exist have no public id, and a session without one
    # can be listed but never revoked -- the id is how the client names it.
    # Only live sessions are backfilled: expired ones are never shown, and
    # skipping them keeps this to a few hundred rows instead of every row ever
    # issued.
    bind = op.get_bind()
    # The column stores naive UTC, matching the repository's datetime contract,
    # so the comparison value has to be naive UTC too rather than a database
    # CURRENT_TIMESTAMP, whose time zone differs between MySQL and SQLite.
    now_naive_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    live_sessions = bind.execute(
        sa.text(
            "SELECT id FROM user_token "
            "WHERE session_bid = '' AND token_expired_at > :now"
        ),
        {"now": now_naive_utc},
    ).fetchall()
    for (row_id,) in live_sessions:
        bind.execute(
            sa.text("UPDATE user_token SET session_bid = :bid WHERE id = :id"),
            {"bid": str(uuid.uuid4()), "id": row_id},
        )


def downgrade() -> None:
    """Remove the session metadata columns and their indexes."""
    op.drop_index("ix_user_token_session_bid", table_name="user_token")
    op.drop_index("ix_user_token_user_id", table_name="user_token")
    with op.batch_alter_table("user_token") as batch_op:
        for column in reversed(_COLUMNS):
            batch_op.drop_column(column.name)
