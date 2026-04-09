"""add billing new creator trial config

Revision ID: a1b2c3d4e5f7
Revises: f6a7b8c9d0e1
Create Date: 2026-04-09 10:30:00.000000

"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f7"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


_NEW_CREATOR_TRIAL_CONFIG = {
    "config_bid": "billing-config-new-creator-trial-config",
    "key": "BILLING_NEW_CREATOR_TRIAL_CONFIG",
    "value": json.dumps(
        {
            "credit_amount": "100.0000000000",
            "eligible_registered_after": "",
            "enabled": 0,
            "grant_trigger": "billing_overview",
            "program_code": "new_creator_v1",
            "valid_days": 15,
        },
        separators=(",", ":"),
        sort_keys=True,
    ),
    "is_encrypted": 0,
    "remark": "New creator trial credit bootstrap config",
    "deleted": 0,
    "updated_by": "system",
}


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
    op.bulk_insert(config_table, [_NEW_CREATOR_TRIAL_CONFIG])


def downgrade():
    config_table = sa.table(
        "sys_configs",
        sa.column("key", sa.String(length=255)),
    )
    op.execute(
        config_table.delete().where(
            config_table.c.key == _NEW_CREATOR_TRIAL_CONFIG["key"]
        )
    )
