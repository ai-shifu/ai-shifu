"""Add the durable billing refund operation journal.

Revision ID: 444f5ed66d94
Revises: fde432bceab4
Create Date: 2026-09-21 05:30:14.431338

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "444f5ed66d94"
down_revision = "fde432bceab4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the refund journal without altering existing billing records."""
    op.create_table(
        "bill_refund_operations",
        sa.Column("refund_operation_bid", sa.String(length=36), nullable=False),
        sa.Column("bill_order_bid", sa.String(length=36), nullable=False),
        sa.Column("creator_bid", sa.String(length=36), nullable=False),
        sa.Column("payment_provider", sa.String(length=32), nullable=False),
        sa.Column("amount", mysql.BIGINT(), nullable=False),
        sa.Column("payment_amount", mysql.BIGINT(), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("payment_intent_id", sa.String(length=255), nullable=False),
        sa.Column("charge_id", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("product_bid", sa.String(length=36), nullable=False),
        sa.Column("subscription_bid", sa.String(length=36), nullable=False),
        sa.Column("order_type", sa.SmallInteger(), nullable=False),
        sa.Column("credit_amount", sa.Numeric(precision=20, scale=10), nullable=False),
        sa.Column("provider_refund_id", sa.String(length=255), nullable=False),
        sa.Column("provider_status", sa.String(length=32), nullable=False),
        sa.Column("provider_result_version", sa.Integer(), nullable=False),
        sa.Column("provider_payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("finalized_at", sa.DateTime(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bill_order_bid", name="uq_bill_refund_operations_bill_order_bid"
        ),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_bill_refund_operations_idempotency_key"
        ),
        sa.UniqueConstraint(
            "refund_operation_bid", name="uq_bill_refund_operations_operation_bid"
        ),
        comment="Durable billing refund requests and reconciliation outcomes",
    )
    with op.batch_alter_table("bill_refund_operations", schema=None) as batch_op:
        batch_op.create_index(
            "ix_bill_refund_operations_creator_status",
            ["creator_bid", "status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_bill_refund_operations_deleted"), ["deleted"], unique=False
        )


def downgrade() -> None:
    """Remove the refund journal when intentionally rolling back its schema."""
    with op.batch_alter_table("bill_refund_operations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_bill_refund_operations_deleted"))
        batch_op.drop_index("ix_bill_refund_operations_creator_status")

    op.drop_table("bill_refund_operations")
