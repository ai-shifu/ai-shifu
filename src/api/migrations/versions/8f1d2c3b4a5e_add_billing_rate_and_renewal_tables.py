"""add billing rate and renewal tables

Revision ID: 8f1d2c3b4a5e
Revises: 4fd52d0d9a01
Create Date: 2026-04-08 00:30:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "8f1d2c3b4a5e"
down_revision = "4fd52d0d9a01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "credit_usage_rates",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "rate_bid",
            sa.String(length=36),
            nullable=False,
            comment="Credit usage rate business identifier",
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
            "usage_scene",
            sa.SmallInteger(),
            nullable=False,
            comment="Usage scene code",
        ),
        sa.Column(
            "billing_metric",
            sa.SmallInteger(),
            nullable=False,
            comment="Billing metric code",
        ),
        sa.Column(
            "unit_size",
            sa.Integer(),
            nullable=False,
            comment="Billing unit size",
        ),
        sa.Column(
            "credits_per_unit",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
            comment="Credits per unit",
        ),
        sa.Column(
            "rounding_mode",
            sa.SmallInteger(),
            nullable=False,
            comment="Rounding mode code",
        ),
        sa.Column(
            "effective_from",
            sa.DateTime(),
            nullable=False,
            comment="Effective from timestamp",
        ),
        sa.Column(
            "effective_to",
            sa.DateTime(),
            nullable=True,
            comment="Effective to timestamp",
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Credit usage rate status code",
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
        comment="Credit usage rates",
    )
    with op.batch_alter_table("credit_usage_rates", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_credit_usage_rates_billing_metric"),
            ["billing_metric"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_usage_rates_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_credit_usage_rates_effective_from"),
            ["effective_from"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_usage_rates_effective_to"),
            ["effective_to"],
            unique=False,
        )
        batch_op.create_index(
            "ix_credit_usage_rates_lookup",
            [
                "usage_type",
                "provider",
                "model",
                "usage_scene",
                "billing_metric",
                "effective_from",
            ],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_usage_rates_model"), ["model"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_credit_usage_rates_provider"), ["provider"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_credit_usage_rates_rate_bid"), ["rate_bid"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_credit_usage_rates_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_credit_usage_rates_usage_scene"),
            ["usage_scene"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_credit_usage_rates_usage_type"),
            ["usage_type"],
            unique=False,
        )

    op.create_table(
        "billing_renewal_events",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "renewal_event_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing renewal event business identifier",
        ),
        sa.Column(
            "subscription_bid",
            sa.String(length=36),
            nullable=False,
            comment="Billing subscription business identifier",
        ),
        sa.Column(
            "creator_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator business identifier",
        ),
        sa.Column(
            "event_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Renewal event type code",
        ),
        sa.Column(
            "scheduled_at",
            sa.DateTime(),
            nullable=False,
            comment="Scheduled timestamp",
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Renewal event status code",
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            comment="Attempt count",
        ),
        sa.Column(
            "last_error",
            sa.String(length=255),
            nullable=False,
            comment="Last error message",
        ),
        sa.Column(
            "payload",
            sa.JSON(),
            nullable=True,
            comment="Renewal event payload",
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(),
            nullable=True,
            comment="Processed timestamp",
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
        comment="Billing renewal events",
    )
    with op.batch_alter_table("billing_renewal_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_billing_renewal_events_creator_bid"),
            ["creator_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_renewal_events_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_billing_renewal_events_event_type"),
            ["event_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_renewal_events_renewal_event_bid"),
            ["renewal_event_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_renewal_events_scheduled_at"),
            ["scheduled_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_renewal_events_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_renewal_events_status_scheduled",
            ["status", "scheduled_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_billing_renewal_events_subscription_bid"),
            ["subscription_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_renewal_events_subscription_event_scheduled",
            ["subscription_bid", "event_type", "scheduled_at"],
            unique=False,
        )


def downgrade():
    op.drop_table("billing_renewal_events")
    op.drop_table("credit_usage_rates")
