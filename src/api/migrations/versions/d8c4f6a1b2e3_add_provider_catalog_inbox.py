"""add provider catalog inbox.

Revision ID: d8c4f6a1b2e3
Revises: c7b9e1a2d4f6
Create Date: 2026-08-24 03:35:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "d8c4f6a1b2e3"
down_revision = "c7b9e1a2d4f6"
branch_labels = None
depends_on = None


def _billing_base_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "deleted", sa.SmallInteger(), nullable=False, comment="Deletion flag"
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, comment="Creation timestamp"
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, comment="Last update timestamp"
        ),
    ]


def upgrade():
    op.create_table(
        "bill_provider_catalog_snapshots",
        sa.Column(
            "catalog_snapshot_bid",
            sa.String(length=36),
            nullable=False,
            comment="Provider catalog snapshot business identifier",
        ),
        sa.Column(
            "provider",
            sa.String(length=32),
            nullable=False,
            comment="Payment provider name",
        ),
        sa.Column(
            "provider_account_id",
            sa.String(length=255),
            nullable=False,
            comment="Provider account identifier",
        ),
        sa.Column(
            "livemode",
            sa.SmallInteger(),
            nullable=False,
            comment="Provider live mode flag",
        ),
        sa.Column(
            "object_type",
            sa.String(length=32),
            nullable=False,
            comment="Provider catalog object type",
        ),
        sa.Column(
            "object_id",
            sa.String(length=255),
            nullable=False,
            comment="Provider catalog object identifier",
        ),
        sa.Column(
            "parent_object_id",
            sa.String(length=255),
            nullable=False,
            comment="Parent provider catalog object identifier",
        ),
        sa.Column(
            "active", sa.SmallInteger(), nullable=False, comment="Provider active flag"
        ),
        sa.Column(
            "provider_created_at",
            sa.DateTime(),
            nullable=True,
            comment="Provider creation timestamp",
        ),
        sa.Column(
            "last_event_id",
            sa.String(length=255),
            nullable=False,
            comment="Latest applied provider event identifier",
        ),
        sa.Column(
            "last_event_type",
            sa.String(length=128),
            nullable=False,
            comment="Latest applied provider event type",
        ),
        sa.Column(
            "last_event_created_at",
            sa.DateTime(),
            nullable=True,
            comment="Latest applied provider event timestamp",
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(),
            nullable=True,
            comment="Latest local sync timestamp",
        ),
        sa.Column(
            "health_status",
            sa.SmallInteger(),
            nullable=False,
            comment="Provider catalog health status",
        ),
        sa.Column(
            "pending_issue_code",
            sa.String(length=128),
            nullable=False,
            comment="Pending catalog issue code",
        ),
        sa.Column(
            "linked_product_bid",
            sa.String(length=36),
            nullable=False,
            comment="Suggested or linked billing product business identifier",
        ),
        sa.Column(
            "metadata", sa.JSON(), nullable=True, comment="Provider catalog metadata"
        ),
        sa.Column(
            "raw_payload",
            sa.JSON(),
            nullable=True,
            comment="Provider catalog raw payload",
        ),
        sa.Column(
            "live_scope",
            sa.String(length=16),
            sa.Computed(
                "CASE WHEN deleted = 0 THEN 'live' ELSE NULL END", persisted=True
            ),
            nullable=True,
            comment="Generated key enforcing one live catalog snapshot",
        ),
        *_billing_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "catalog_snapshot_bid", name="uq_bill_provider_catalog_snapshots_bid"
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_account_id",
            "livemode",
            "object_type",
            "object_id",
            "live_scope",
            name="uq_bill_provider_catalog_snapshots_object",
        ),
        comment="Provider catalog object snapshots",
    )
    op.create_index(
        "ix_bill_provider_catalog_snapshots_catalog_snapshot_bid",
        "bill_provider_catalog_snapshots",
        ["catalog_snapshot_bid"],
    )
    op.create_index(
        "ix_bill_provider_catalog_snapshots_deleted",
        "bill_provider_catalog_snapshots",
        ["deleted"],
    )
    op.create_index(
        "ix_bill_provider_catalog_snapshots_health",
        "bill_provider_catalog_snapshots",
        ["provider", "health_status", "updated_at"],
    )
    op.create_index(
        "ix_bill_provider_catalog_snapshots_linked_product_bid",
        "bill_provider_catalog_snapshots",
        ["linked_product_bid"],
    )
    op.create_index(
        "ix_bill_provider_catalog_snapshots_object_id",
        "bill_provider_catalog_snapshots",
        ["object_id"],
    )
    op.create_index(
        "ix_bill_provider_catalog_snapshots_object_type",
        "bill_provider_catalog_snapshots",
        ["object_type"],
    )
    op.create_index(
        "ix_bill_provider_catalog_snapshots_parent",
        "bill_provider_catalog_snapshots",
        ["provider", "provider_account_id", "parent_object_id"],
    )
    op.create_index(
        "ix_bill_provider_catalog_snapshots_provider",
        "bill_provider_catalog_snapshots",
        ["provider"],
    )

    op.create_table(
        "bill_provider_catalog_events",
        sa.Column(
            "catalog_event_bid",
            sa.String(length=36),
            nullable=False,
            comment="Provider catalog event business identifier",
        ),
        sa.Column(
            "provider",
            sa.String(length=32),
            nullable=False,
            comment="Payment provider name",
        ),
        sa.Column(
            "provider_event_id",
            sa.String(length=255),
            nullable=False,
            comment="Provider event identifier",
        ),
        sa.Column(
            "event_type",
            sa.String(length=128),
            nullable=False,
            comment="Provider event type",
        ),
        sa.Column(
            "event_source",
            sa.String(length=32),
            nullable=False,
            comment="Webhook, reconcile, or manual sync source",
        ),
        sa.Column(
            "provider_account_id",
            sa.String(length=255),
            nullable=False,
            comment="Provider account identifier",
        ),
        sa.Column(
            "livemode",
            sa.SmallInteger(),
            nullable=False,
            comment="Provider live mode flag",
        ),
        sa.Column(
            "object_type",
            sa.String(length=32),
            nullable=False,
            comment="Provider catalog object type",
        ),
        sa.Column(
            "object_id",
            sa.String(length=255),
            nullable=False,
            comment="Provider catalog object identifier",
        ),
        sa.Column(
            "parent_object_id",
            sa.String(length=255),
            nullable=False,
            comment="Parent provider catalog object identifier",
        ),
        sa.Column(
            "event_created_at",
            sa.DateTime(),
            nullable=True,
            comment="Provider event timestamp",
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(),
            nullable=True,
            comment="Local processing timestamp",
        ),
        sa.Column(
            "processing_status",
            sa.SmallInteger(),
            nullable=False,
            comment="Provider catalog event processing status",
        ),
        sa.Column(
            "processing_error",
            sa.Text(),
            nullable=True,
            comment="Safe processing error summary",
        ),
        sa.Column(
            "raw_payload",
            sa.JSON(),
            nullable=True,
            comment="Provider catalog event raw payload",
        ),
        sa.Column(
            "live_scope",
            sa.String(length=16),
            sa.Computed(
                "CASE WHEN deleted = 0 THEN 'live' ELSE NULL END", persisted=True
            ),
            nullable=True,
            comment="Generated key enforcing one live provider event",
        ),
        *_billing_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "catalog_event_bid", name="uq_bill_provider_catalog_events_bid"
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_event_id",
            "live_scope",
            name="uq_bill_provider_catalog_events_provider_event",
        ),
        comment="Provider catalog event inbox",
    )
    op.create_index(
        "ix_bill_provider_catalog_events_catalog_event_bid",
        "bill_provider_catalog_events",
        ["catalog_event_bid"],
    )
    op.create_index(
        "ix_bill_provider_catalog_events_deleted",
        "bill_provider_catalog_events",
        ["deleted"],
    )
    op.create_index(
        "ix_bill_provider_catalog_events_event_type",
        "bill_provider_catalog_events",
        ["event_type"],
    )
    op.create_index(
        "ix_bill_provider_catalog_events_object_id",
        "bill_provider_catalog_events",
        ["object_id"],
    )
    op.create_index(
        "ix_bill_provider_catalog_events_object_type",
        "bill_provider_catalog_events",
        ["object_type"],
    )
    op.create_index(
        "ix_bill_provider_catalog_events_object",
        "bill_provider_catalog_events",
        ["provider", "provider_account_id", "object_type", "object_id"],
    )
    op.create_index(
        "ix_bill_provider_catalog_events_processing_status",
        "bill_provider_catalog_events",
        ["processing_status"],
    )
    op.create_index(
        "ix_bill_provider_catalog_events_provider",
        "bill_provider_catalog_events",
        ["provider"],
    )
    op.create_index(
        "ix_bill_provider_catalog_events_status",
        "bill_provider_catalog_events",
        ["processing_status", "created_at"],
    )


def downgrade():
    op.drop_table("bill_provider_catalog_events")
    op.drop_table("bill_provider_catalog_snapshots")
