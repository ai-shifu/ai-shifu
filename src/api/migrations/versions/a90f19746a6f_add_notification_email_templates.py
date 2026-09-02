"""add notification email templates.

Revision ID: a90f19746a6f
Revises: 6d568133dd29
Create Date: 2026-09-02 06:53:43.081512

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a90f19746a6f"
down_revision = "6d568133dd29"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_templates",
        sa.Column(
            "locale",
            sa.String(length=16),
            nullable=True,
            comment="Email template locale",
        ),
    )
    op.add_column(
        "notification_templates",
        sa.Column(
            "email_subject",
            sa.Text(),
            nullable=True,
            comment="Email template subject",
        ),
    )
    op.add_column(
        "notification_templates",
        sa.Column(
            "email_html_body",
            sa.Text(),
            nullable=True,
            comment="Email template HTML body",
        ),
    )


def downgrade() -> None:
    op.drop_column("notification_templates", "email_html_body")
    op.drop_column("notification_templates", "email_subject")
    op.drop_column("notification_templates", "locale")
