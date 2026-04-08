"""add billing daily aggregate tables

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-04-08 23:30:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "d4e5f6a7b8c9"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_daily_usage_metrics",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "daily_usage_metric_bid",
            sa.String(length=36),
            nullable=False,
            comment="Daily usage metric business identifier",
        ),
        sa.Column(
            "stat_date",
            sa.String(length=10),
            nullable=False,
            comment="Statistic date",
        ),
        sa.Column(
            "creator_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator business identifier",
        ),
        sa.Column(
            "shifu_bid",
            sa.String(length=36),
            nullable=False,
            comment="Shifu business identifier",
        ),
        sa.Column(
            "usage_scene",
            sa.SmallInteger(),
            nullable=False,
            comment="Usage scene code",
        ),
        sa.Column(
            "usage_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Usage type code",
        ),
        sa.Column(
            "provider",
            sa.String(length=32),
            nullable=False,
            comment="Provider name",
        ),
        sa.Column(
            "model",
            sa.String(length=100),
            nullable=False,
            comment="Provider model",
        ),
        sa.Column(
            "billing_metric",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing metric code",
        ),
        sa.Column(
            "raw_amount",
            mysql.BIGINT(),
            nullable=False,
            comment="Raw amount",
        ),
        sa.Column(
            "record_count",
            mysql.BIGINT(),
            nullable=False,
            comment="Record count",
        ),
        sa.Column(
            "consumed_credits",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Consumed credits",
        ),
        sa.Column(
            "window_started_at",
            sa.DateTime(),
            nullable=False,
            comment="Window start timestamp",
        ),
        sa.Column(
            "window_ended_at",
            sa.DateTime(),
            nullable=False,
            comment="Window end timestamp",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "daily_usage_metric_bid",
            name="uq_billing_daily_usage_metrics_daily_usage_metric_bid",
        ),
        sa.UniqueConstraint(
            "stat_date",
            "creator_bid",
            "shifu_bid",
            "usage_scene",
            "usage_type",
            "provider",
            "model",
            "billing_metric",
            name="uq_billing_daily_usage_metrics_lookup",
        ),
        comment="Billing daily usage metrics",
    )
    with op.batch_alter_table("billing_daily_usage_metrics", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_daily_usage_metrics_billing_metric"),
            ["billing_metric"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_daily_usage_metrics_creator_bid"),
            ["creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_daily_usage_metrics_daily_usage_metric_bid"),
            ["daily_usage_metric_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_daily_usage_metrics_deleted"),
            ["deleted"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_daily_usage_metrics_model"),
            ["model"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_daily_usage_metrics_provider"),
            ["provider"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_daily_usage_metrics_shifu_bid"),
            ["shifu_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_daily_usage_metrics_stat_creator",
            ["stat_date", "creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_daily_usage_metrics_stat_date"),
            ["stat_date"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_daily_usage_metrics_usage_scene"),
            ["usage_scene"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_daily_usage_metrics_usage_type"),
            ["usage_type"],
            unique=False,
        )

    op.create_table(
        "billing_daily_ledger_summary",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "daily_ledger_summary_bid",
            sa.String(length=36),
            nullable=False,
            comment="Daily ledger summary business identifier",
        ),
        sa.Column(
            "stat_date",
            sa.String(length=10),
            nullable=False,
            comment="Statistic date",
        ),
        sa.Column(
            "creator_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator business identifier",
        ),
        sa.Column(
            "entry_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing ledger entry type code",
        ),
        sa.Column(
            "source_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing ledger source type code",
        ),
        sa.Column(
            "amount",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Ledger amount total",
        ),
        sa.Column(
            "entry_count",
            mysql.BIGINT(),
            nullable=False,
            comment="Ledger entry count",
        ),
        sa.Column(
            "window_started_at",
            sa.DateTime(),
            nullable=False,
            comment="Window start timestamp",
        ),
        sa.Column(
            "window_ended_at",
            sa.DateTime(),
            nullable=False,
            comment="Window end timestamp",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "daily_ledger_summary_bid",
            name="uq_billing_daily_ledger_summary_daily_ledger_summary_bid",
        ),
        sa.UniqueConstraint(
            "stat_date",
            "creator_bid",
            "entry_type",
            "source_type",
            name="uq_billing_daily_ledger_summary_lookup",
        ),
        comment="Billing daily ledger summary",
    )
    with op.batch_alter_table("billing_daily_ledger_summary", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_daily_ledger_summary_creator_bid"),
            ["creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_daily_ledger_summary_daily_ledger_summary_bid"),
            ["daily_ledger_summary_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_daily_ledger_summary_deleted"),
            ["deleted"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_daily_ledger_summary_entry_type"),
            ["entry_type"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_daily_ledger_summary_stat_creator",
            ["stat_date", "creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_daily_ledger_summary_stat_date"),
            ["stat_date"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_daily_ledger_summary_source_type"),
            ["source_type"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("billing_daily_ledger_summary", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_billing_daily_ledger_summary_source_type"))
        batch_op.drop_index(batch_op.f("ix_billing_daily_ledger_summary_stat_date"))
        batch_op.drop_index("ix_billing_daily_ledger_summary_stat_creator")
        batch_op.drop_index(batch_op.f("ix_billing_daily_ledger_summary_entry_type"))
        batch_op.drop_index(batch_op.f("ix_billing_daily_ledger_summary_deleted"))
        batch_op.drop_index(
            batch_op.f("ix_billing_daily_ledger_summary_daily_ledger_summary_bid")
        )
        batch_op.drop_index(batch_op.f("ix_billing_daily_ledger_summary_creator_bid"))

    op.drop_table("billing_daily_ledger_summary")

    with op.batch_alter_table("billing_daily_usage_metrics", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_billing_daily_usage_metrics_usage_type"))
        batch_op.drop_index(batch_op.f("ix_billing_daily_usage_metrics_usage_scene"))
        batch_op.drop_index(batch_op.f("ix_billing_daily_usage_metrics_stat_date"))
        batch_op.drop_index("ix_billing_daily_usage_metrics_stat_creator")
        batch_op.drop_index(batch_op.f("ix_billing_daily_usage_metrics_shifu_bid"))
        batch_op.drop_index(batch_op.f("ix_billing_daily_usage_metrics_provider"))
        batch_op.drop_index(batch_op.f("ix_billing_daily_usage_metrics_model"))
        batch_op.drop_index(batch_op.f("ix_billing_daily_usage_metrics_deleted"))
        batch_op.drop_index(
            batch_op.f("ix_billing_daily_usage_metrics_daily_usage_metric_bid")
        )
        batch_op.drop_index(batch_op.f("ix_billing_daily_usage_metrics_creator_bid"))
        batch_op.drop_index(batch_op.f("ix_billing_daily_usage_metrics_billing_metric"))

    op.drop_table("billing_daily_usage_metrics")
