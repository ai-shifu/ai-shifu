"""add promo campaign tables

Revision ID: c221d355ffb7
Revises: 9f3a0c3aebe0
Create Date: 2026-01-27

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "c221d355ffb7"
down_revision = "9f3a0c3aebe0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "promo_campaigns",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Unique ID",
        ),
        sa.Column(
            "campaign_bid",
            sa.String(length=36),
            nullable=False,
            comment="Campaign business identifier",
        ),
        sa.Column(
            "shifu_bid",
            sa.String(length=36),
            nullable=False,
            comment="Shifu business identifier",
        ),
        sa.Column(
            "name", sa.String(length=255), nullable=False, comment="Campaign name"
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            comment="Campaign description",
        ),
        sa.Column(
            "join_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Join type: 2101=auto, 2102=event, 2103=manual",
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
            comment="Campaign start time",
        ),
        sa.Column(
            "end_at",
            sa.DateTime(),
            nullable=False,
            comment="Campaign end time",
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
            comment="Discount value: interpreted by discount_type",
        ),
        sa.Column(
            "channel",
            sa.String(length=36),
            nullable=False,
            comment="Campaign channel",
        ),
        sa.Column(
            "filter",
            sa.Text(),
            nullable=False,
            comment="Campaign filter: JSON string for user/shifu targeting",
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
        comment="Promo campaigns",
    )
    with op.batch_alter_table("promo_campaigns", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_promo_campaigns_campaign_bid"),
            ["campaign_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_campaigns_created_user_bid"),
            ["created_user_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_campaigns_deleted"), ["deleted"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_promo_campaigns_end_at"), ["end_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_promo_campaigns_shifu_bid"), ["shifu_bid"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_promo_campaigns_start_at"), ["start_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_promo_campaigns_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_promo_campaigns_updated_user_bid"),
            ["updated_user_bid"],
            unique=False,
        )

    op.create_table(
        "promo_campaign_applications",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Unique ID",
        ),
        sa.Column(
            "campaign_application_bid",
            sa.String(length=36),
            nullable=False,
            comment="Campaign application business identifier",
        ),
        sa.Column(
            "campaign_bid",
            sa.String(length=36),
            nullable=False,
            comment="Campaign business identifier",
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
            "campaign_name",
            sa.String(length=255),
            nullable=False,
            comment="Campaign name snapshot",
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
            comment="Applied discount amount for this order",
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
            "campaign_bid",
            "deleted",
            name="uk_promo_campaign_application_order_campaign_deleted",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Promo campaign applications",
    )
    with op.batch_alter_table("promo_campaign_applications", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_promo_campaign_applications_campaign_application_bid"),
            ["campaign_application_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_campaign_applications_campaign_bid"),
            ["campaign_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_campaign_applications_deleted"),
            ["deleted"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_campaign_applications_order_bid"),
            ["order_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_campaign_applications_shifu_bid"),
            ["shifu_bid"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_campaign_applications_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_promo_campaign_applications_user_bid"),
            ["user_bid"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("promo_campaign_applications", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_promo_campaign_applications_user_bid"))
        batch_op.drop_index(batch_op.f("ix_promo_campaign_applications_status"))
        batch_op.drop_index(batch_op.f("ix_promo_campaign_applications_shifu_bid"))
        batch_op.drop_index(batch_op.f("ix_promo_campaign_applications_order_bid"))
        batch_op.drop_index(batch_op.f("ix_promo_campaign_applications_deleted"))
        batch_op.drop_index(batch_op.f("ix_promo_campaign_applications_campaign_bid"))
        batch_op.drop_index(
            batch_op.f("ix_promo_campaign_applications_campaign_application_bid")
        )
    op.drop_table("promo_campaign_applications")

    with op.batch_alter_table("promo_campaigns", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_promo_campaigns_updated_user_bid"))
        batch_op.drop_index(batch_op.f("ix_promo_campaigns_status"))
        batch_op.drop_index(batch_op.f("ix_promo_campaigns_start_at"))
        batch_op.drop_index(batch_op.f("ix_promo_campaigns_shifu_bid"))
        batch_op.drop_index(batch_op.f("ix_promo_campaigns_end_at"))
        batch_op.drop_index(batch_op.f("ix_promo_campaigns_deleted"))
        batch_op.drop_index(batch_op.f("ix_promo_campaigns_created_user_bid"))
        batch_op.drop_index(batch_op.f("ix_promo_campaigns_campaign_bid"))
    op.drop_table("promo_campaigns")
