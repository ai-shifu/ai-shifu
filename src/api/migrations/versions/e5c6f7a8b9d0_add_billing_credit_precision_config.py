"""add billing credit precision config

Revision ID: e5c6f7a8b9d0
Revises: d2b9a5c4f8e1
Create Date: 2026-04-15 11:30:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e5c6f7a8b9d0"
down_revision = "d2b9a5c4f8e1"
branch_labels = None
depends_on = None


_BILLING_CREDIT_PRECISION_CONFIG = {
    "config_bid": "billing-config-credit-precision",
    "key": "BILLING_CREDIT_PRECISION",
    "value": "2",
    "is_encrypted": 0,
    "remark": "Fractional digits used for billing credit display and settlement rounding",
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
    op.bulk_insert(config_table, [_BILLING_CREDIT_PRECISION_CONFIG])


def downgrade():
    config_table = sa.table("sys_configs", sa.column("key", sa.String(length=255)))
    op.execute(
        config_table.delete().where(
            config_table.c.key == _BILLING_CREDIT_PRECISION_CONFIG["key"]
        )
    )
