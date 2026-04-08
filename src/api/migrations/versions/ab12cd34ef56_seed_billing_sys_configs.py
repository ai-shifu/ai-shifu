"""seed billing sys configs

Revision ID: ab12cd34ef56
Revises: 9c1d2e3f4a5b
Create Date: 2026-04-08 01:30:00.000000

"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "ab12cd34ef56"
down_revision = "9c1d2e3f4a5b"
branch_labels = None
depends_on = None


_BILLING_SYS_CONFIG_SEEDS = (
    {
        "config_bid": "billing-config-enabled",
        "key": "BILLING_ENABLED",
        "value": "1",
        "is_encrypted": 0,
        "remark": "Creator billing feature flag",
        "deleted": 0,
        "updated_by": "system",
    },
    {
        "config_bid": "billing-config-low-balance-threshold",
        "key": "BILLING_LOW_BALANCE_THRESHOLD",
        "value": "0.0000000000",
        "is_encrypted": 0,
        "remark": "Low balance alert threshold in credits",
        "deleted": 0,
        "updated_by": "system",
    },
    {
        "config_bid": "billing-config-renewal-task-config",
        "key": "BILLING_RENEWAL_TASK_CONFIG",
        "value": json.dumps(
            {
                "enabled": 0,
                "batch_size": 100,
                "lookahead_minutes": 60,
                "queue": "billing-renewal",
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        "is_encrypted": 0,
        "remark": "Renewal task bootstrap config",
        "deleted": 0,
        "updated_by": "system",
    },
    {
        "config_bid": "billing-config-rate-version",
        "key": "BILLING_RATE_VERSION",
        "value": "bootstrap-v1",
        "is_encrypted": 0,
        "remark": "Billing rate version bootstrap marker",
        "deleted": 0,
        "updated_by": "system",
    },
)


def upgrade():
    config_table = sa.table(
        "sys_configs",
        sa.column("config_bid", sa.String(length=36)),
        sa.column("key", sa.String(length=255)),
        sa.column("value", sa.Text()),
        sa.column("is_encrypted", sa.SmallInteger()),
        sa.column("remark", sa.Text()),
        sa.column("deleted", sa.SmallInteger()),
        sa.column("updated_by", sa.String(length=36)),
    )
    op.bulk_insert(config_table, list(_BILLING_SYS_CONFIG_SEEDS))


def downgrade():
    config_table = sa.table(
        "sys_configs",
        sa.column("key", sa.String(length=255)),
    )
    op.execute(
        config_table.delete().where(
            config_table.c.key.in_([row["key"] for row in _BILLING_SYS_CONFIG_SEEDS])
        )
    )
