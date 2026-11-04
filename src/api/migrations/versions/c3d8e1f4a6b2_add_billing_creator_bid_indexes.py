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

MySQL DDL is not transactional: if the upgrade stops after one CREATE INDEX,
Alembic has not stamped the revision and a retry would fail with a duplicate
index name. The upgrade therefore creates each index only when it is missing
(the documented non-transactional DDL recovery case in src/api/AGENTS.md).
The downgrade reverses this revision's schema with plain drops.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3d8e1f4a6b2"
down_revision = "a7c1e3f5b9d2"
branch_labels = None
depends_on = None


def _index_exists(table_name: str, index_name: str) -> bool:
    """Return whether this revision's index is already there.

    A same-named index with another definition is not a partial run of this
    revision, so it stops the upgrade instead of being accepted.
    """
    inspector = sa.inspect(op.get_bind())
    for index in inspector.get_indexes(table_name):
        if index.get("name") != index_name:
            continue
        if list(index.get("column_names") or []) == ["creator_bid"] and not bool(
            index.get("unique")
        ):
            return True
        raise RuntimeError(
            f"{table_name}.{index_name} exists with an unexpected definition; "
            "drop it before upgrading"
        )
    return False


def upgrade():
    if not _index_exists(
        "bill_daily_ledger_summary", "ix_bill_daily_ledger_summary_creator_bid"
    ):
        with op.batch_alter_table("bill_daily_ledger_summary", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_bill_daily_ledger_summary_creator_bid"),
                ["creator_bid"],
                unique=False,
            )
    if not _index_exists(
        "bill_daily_usage_metrics", "ix_bill_daily_usage_metrics_creator_bid"
    ):
        with op.batch_alter_table("bill_daily_usage_metrics", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_bill_daily_usage_metrics_creator_bid"),
                ["creator_bid"],
                unique=False,
            )
    if not _index_exists("bill_renewal_events", "ix_bill_renewal_events_creator_bid"):
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
