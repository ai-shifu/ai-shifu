"""add promo tables

Revision ID: c221d355ffb7
Revises: b2793bb43f97
Create Date: 2026-01-27

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "c221d355ffb7"
down_revision = "b2793bb43f97"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "promo_promos",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Unique ID",
        ),
        sa.Column(
            "promo_bid",
            sa.String(length=36),
            nullable=False,
            comment="Promotion business identifier",
        ),
        sa.Column(
            "shifu_bid",
            sa.String(length=36),
            nullable=False,
            comment="Shifu business identifier",
        ),
        sa.Column(
            "name", sa.String(length=255), nullable=False, comment="Promotion name"
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            comment="Promotion description",
        ),
        sa.Column(
            "apply_type",
            sa.SmallInteger(),
            nullable=False,
            comment=(
                "Apply/join type: 2101=auto(eligible users get it automatically), "
                "2102=event(granted on specific events), 2103=manual(granted manually)"
            ),
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Status: 0=inactive, 1=active",
        ),
        sa.Column(
            "start_at",
            sa.DateTime(),
            nullable=False,
            comment="Promotion start time(inclusive)",
        ),
        sa.Column(
            "end_at",
            sa.DateTime(),
            nullable=False,
            comment="Promotion end time(recommended exclusive): start_at <= now < end_at",
        ),
        sa.Column(
            "discount_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Discount type: 701=fixed, 702=percent",
        ),
        sa.Column(
            "value",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            comment=(
                "Discount value: interpreted by discount_type(fixed = amount off; percent = percentage off)"
            ),
        ),
        sa.Column(
            "channel",
            sa.String(length=36),
            nullable=False,
            comment="Promotion channel(e.g., web/app/partner; business-defined)",
        ),
        sa.Column(
            "filter",
            sa.Text(),
            nullable=False,
            comment="Promotion filter: JSON string for user/shifu targeting;{} means no restriction.",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            comment="Creation timestamp",
        ),
        sa.Column(
            "created_user_bid",
            sa.String(length=36),
            nullable=False,
            comment="Creator user business identifier",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            comment="Last update timestamp",
        ),
        sa.Column(
            "updated_user_bid",
            sa.String(length=36),
            nullable=False,
            comment="Last updater user business identifier",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment=(
            "Promotion campaign definition table. Defines a discount campaign for a specific "
            "Shifu (join/apply type, time window, discount configuration, channel, and targeting "
            "filter). Stores configuration only; user participation/claim/redemption records are "
            "stored in table promo_redemptions."
        ),
    )
    with op.batch_alter_table("promo_promos", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_promo_promos_promo_bid"),
            ["promo_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_promos_created_user_bid"),
            ["created_user_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_promos_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_promo_promos_end_at"), ["end_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_promo_promos_shifu_bid"), ["shifu_bid"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_promo_promos_start_at"), ["start_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_promo_promos_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_promo_promos_updated_user_bid"),
            ["updated_user_bid"],
            unique=False,
        )

    op.create_table(
        "promo_redemptions",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Unique ID",
        ),
        sa.Column(
            "redemption_bid",
            sa.String(length=36),
            nullable=False,
            comment="Promotion application business identifier",
        ),
        sa.Column(
            "promo_bid",
            sa.String(length=36),
            nullable=False,
            comment="Promotion business identifier",
        ),
        sa.Column(
            "order_bid",
            sa.String(length=36),
            nullable=False,
            comment="Order business identifier",
        ),
        sa.Column(
            "user_bid",
            sa.String(length=36),
            nullable=False,
            comment="User business identifier",
        ),
        sa.Column(
            "shifu_bid",
            sa.String(length=36),
            nullable=False,
            comment="Shifu business identifier",
        ),
        sa.Column(
            "promo_name",
            sa.String(length=255),
            nullable=False,
            comment="Promotion name snapshot",
        ),
        sa.Column(
            "discount_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Discount type snapshot: 701=fixed, 702=percent",
        ),
        sa.Column(
            "value",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            comment="Discount value snapshot: interpreted by discount_type",
        ),
        sa.Column(
            "discount_amount",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            comment=(
                "Discount amount actually applied to this order (computed result for this redemption)"
            ),
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Status: 4101=applied, 4102=voided",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            comment="Deletion flag: 0=active, 1=deleted",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            comment="Last update timestamp",
        ),
        sa.UniqueConstraint(
            "order_bid",
            "promo_bid",
            "deleted",
            name="uk_promo_campaign_application_order_campaign_deleted",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment=(
            "Promotion campaign redemption ledger. Records each time a user redeems/applies a "
            "promo campaign to an order, including snapshot fields (campaign name/discount "
            "type/value) and the computed discount amount. This table is transactional/"
            "immutable-by-intent; campaign definitions live in promo_promos."
        ),
    )
    with op.batch_alter_table("promo_redemptions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_promo_redemptions_redemption_bid"),
            ["redemption_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_redemptions_promo_bid"),
            ["promo_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_redemptions_deleted"),
            ["deleted"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_redemptions_order_bid"),
            ["order_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_redemptions_shifu_bid"),
            ["shifu_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_redemptions_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_redemptions_user_bid"),
            ["user_bid"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("promo_redemptions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_promo_redemptions_user_bid"))
        batch_op.drop_index(batch_op.f("ix_promo_redemptions_status"))
        batch_op.drop_index(batch_op.f("ix_promo_redemptions_shifu_bid"))
        batch_op.drop_index(batch_op.f("ix_promo_redemptions_order_bid"))
        batch_op.drop_index(batch_op.f("ix_promo_redemptions_deleted"))
        batch_op.drop_index(batch_op.f("ix_promo_redemptions_promo_bid"))
        batch_op.drop_index(batch_op.f("ix_promo_redemptions_redemption_bid"))
    op.drop_table("promo_redemptions")

    with op.batch_alter_table("promo_promos", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_promo_promos_updated_user_bid"))
        batch_op.drop_index(batch_op.f("ix_promo_promos_status"))
        batch_op.drop_index(batch_op.f("ix_promo_promos_start_at"))
        batch_op.drop_index(batch_op.f("ix_promo_promos_shifu_bid"))
        batch_op.drop_index(batch_op.f("ix_promo_promos_end_at"))
        batch_op.drop_index(batch_op.f("ix_promo_promos_deleted"))
        batch_op.drop_index(batch_op.f("ix_promo_promos_created_user_bid"))
        batch_op.drop_index(batch_op.f("ix_promo_promos_promo_bid"))
    op.drop_table("promo_promos")
