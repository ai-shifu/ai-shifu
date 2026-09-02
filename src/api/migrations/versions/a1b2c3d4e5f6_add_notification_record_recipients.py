"""add notification record recipients.

Revision ID: a1b2c3d4e5f6
Revises: a3f9c1d05b28
Create Date: 2026-09-02 10:50:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "a3f9c1d05b28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_records",
        sa.Column(
            "recipient_type",
            sa.String(length=32),
            nullable=False,
            server_default="mobile",
            comment="Recipient contact type",
        ),
    )
    op.add_column(
        "notification_records",
        sa.Column(
            "recipient_snapshot",
            sa.String(length=255),
            nullable=False,
            server_default="",
            comment="Recipient contact snapshot",
        ),
    )
    op.execute(
        "UPDATE notification_records SET recipient_snapshot = mobile_snapshot "
        "WHERE recipient_snapshot = ''"
    )
    op.create_index(
        "ix_notification_records_recipient_snapshot",
        "notification_records",
        ["recipient_snapshot"],
        unique=False,
    )
def downgrade() -> None:
    op.drop_index(
        "ix_notification_records_recipient_snapshot", table_name="notification_records"
    )
    op.drop_column("notification_records", "recipient_snapshot")
    op.drop_column("notification_records", "recipient_type")
