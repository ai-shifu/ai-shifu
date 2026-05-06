"""add coupon admin fields

Revision ID: 4d9f6c7b8a1e
Revises: b114d7f5e2c1
Create Date: 2026-04-24 18:30:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "4d9f6c7b8a1e"
down_revision = "b114d7f5e2c1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("promo_coupons", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "name",
                sa.String(length=255),
                nullable=False,
                server_default="",
                comment="Coupon batch name",
            )
        )
        batch_op.add_column(
            sa.Column(
                "updated_user_bid",
                sa.String(length=36),
                nullable=False,
                server_default="",
                comment="Last updater user business identifier",
            )
        )


def downgrade():
    with op.batch_alter_table("promo_coupons", schema=None) as batch_op:
        batch_op.drop_column("updated_user_bid")
        batch_op.drop_column("name")
