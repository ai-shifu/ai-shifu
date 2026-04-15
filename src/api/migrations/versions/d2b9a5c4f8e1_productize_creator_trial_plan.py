"""productize creator trial plan

Revision ID: d2b9a5c4f8e1
Revises: c225e8a6f3d2
Create Date: 2026-04-15 10:30:00.000000

"""

from __future__ import annotations

from decimal import Decimal
import json

from alembic import op
import sqlalchemy as sa


revision = "d2b9a5c4f8e1"
down_revision = "c225e8a6f3d2"
branch_labels = None
depends_on = None


_TRIAL_PRODUCT = {
    "product_bid": "billing-product-plan-trial",
    "product_code": "creator-plan-trial",
    "product_type": 7111,
    "billing_mode": 7123,
    "billing_interval": 7131,
    "billing_interval_count": 0,
    "display_name_i18n_key": "module.billing.package.free.title",
    "description_i18n_key": "module.billing.package.free.description",
    "currency": "CNY",
    "price_amount": 0,
    "credit_amount": Decimal("100.0000000000"),
    "allocation_interval": 7143,
    "auto_renew_enabled": 0,
    "entitlement_payload": None,
    "metadata": {
        "public_trial_offer": True,
        "trial_valid_days": 15,
        "starts_on_first_grant": True,
        "highlights": [
            "module.billing.package.features.free.publish",
            "module.billing.package.features.free.preview",
        ],
    },
    "status": 7151,
    "sort_order": 5,
    "deleted": 0,
}

_LEGACY_TRIAL_CONFIG = {
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
    product_table = sa.table(
        "billing_products",
        sa.column("product_bid", sa.String(length=36)),
        sa.column("product_code", sa.String(length=64)),
        sa.column("product_type", sa.SmallInteger()),
        sa.column("billing_mode", sa.SmallInteger()),
        sa.column("billing_interval", sa.SmallInteger()),
        sa.column("billing_interval_count", sa.Integer()),
        sa.column("display_name_i18n_key", sa.String(length=128)),
        sa.column("description_i18n_key", sa.String(length=128)),
        sa.column("currency", sa.String(length=16)),
        sa.column("price_amount", sa.BigInteger()),
        sa.column("credit_amount", sa.Numeric(precision=20, scale=10)),
        sa.column("allocation_interval", sa.SmallInteger()),
        sa.column("auto_renew_enabled", sa.SmallInteger()),
        sa.column("entitlement_payload", sa.JSON()),
        sa.column("metadata", sa.JSON()),
        sa.column("status", sa.SmallInteger()),
        sa.column("sort_order", sa.Integer()),
        sa.column("deleted", sa.SmallInteger()),
    )
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

    op.bulk_insert(product_table, [_TRIAL_PRODUCT])
    op.execute(
        config_table.delete().where(config_table.c.key == _LEGACY_TRIAL_CONFIG["key"])
    )


def downgrade():
    product_table = sa.table(
        "billing_products",
        sa.column("product_bid", sa.String(length=36)),
        sa.column("product_code", sa.String(length=64)),
    )
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

    op.execute(
        product_table.delete().where(
            product_table.c.product_bid == _TRIAL_PRODUCT["product_bid"]
        )
    )
    op.bulk_insert(config_table, [_LEGACY_TRIAL_CONFIG])
