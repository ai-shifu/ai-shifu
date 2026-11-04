"""add billing creator_bid indexes.

Revision ID: c3d8e1f4a6b2
Revises: a7c1e3f5b9d2
Create Date: 2026-11-04 12:00:00.000000

Additive only. The billing models declared these single-column indexes, but no
migration ever created them; production (checked read-only in China on 2026-11-04)
does not have them. Creator-scoped reads on these tables filter by creator_bid
without a leading stat_date or subscription_bid, so they cannot use the existing
composite indexes. The other undeclared indexes were redundant and were removed
from the models instead.
"""

from __future__ import annotations

from alembic import op

revision = "c3d8e1f4a6b2"
down_revision = "a7c1e3f5b9d2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("bill_daily_ledger_summary", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_bill_daily_ledger_summary_creator_bid"),
            ["creator_bid"],
            unique=False,
        )
    with op.batch_alter_table("bill_daily_usage_metrics", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_bill_daily_usage_metrics_creator_bid"),
            ["creator_bid"],
            unique=False,
        )
    with op.batch_alter_table("bill_renewal_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_bill_renewal_events_creator_bid"),
            ["creator_bid"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("bill_renewal_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_bill_renewal_events_creator_bid"))
    with op.batch_alter_table("bill_daily_usage_metrics", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_bill_daily_usage_metrics_creator_bid"))
    with op.batch_alter_table("bill_daily_ledger_summary", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_bill_daily_ledger_summary_creator_bid"))
