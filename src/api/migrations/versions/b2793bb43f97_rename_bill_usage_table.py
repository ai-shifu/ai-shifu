"""rename billing usage table and update codes

Revision ID: b2793bb43f97
Revises: c6b7e7f9a2b1
Create Date: 2026-02-05 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b2793bb43f97"
down_revision = "c6b7e7f9a2b1"
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table("billing_usage_records", "bill_usage")

    with op.batch_alter_table("bill_usage", schema=None) as batch_op:
        batch_op.drop_index("idx_billing_usage_user_created")
        batch_op.drop_index("idx_billing_usage_shifu_created")
        batch_op.drop_index("idx_billing_usage_type_created")
        batch_op.drop_index("ix_billing_usage_records_audio_bid")
        batch_op.drop_index("ix_billing_usage_records_generated_block_bid")
        batch_op.drop_index("ix_billing_usage_records_outline_item_bid")
        batch_op.drop_index("ix_billing_usage_records_parent_usage_bid")
        batch_op.drop_index("ix_billing_usage_records_progress_record_bid")
        batch_op.drop_index("ix_billing_usage_records_request_id")
        batch_op.drop_index("ix_billing_usage_records_shifu_bid")
        batch_op.drop_index("ix_billing_usage_records_usage_bid")
        batch_op.drop_index("ix_billing_usage_records_user_bid")
        batch_op.drop_index("ix_billing_usage_records_deleted")

        batch_op.create_index("idx_bill_usage_user_created", ["user_bid", "created_at"])
        batch_op.create_index(
            "idx_bill_usage_shifu_created", ["shifu_bid", "created_at"]
        )
        batch_op.create_index(
            "idx_bill_usage_type_created", ["usage_type", "created_at"]
        )
        batch_op.create_index("ix_bill_usage_audio_bid", ["audio_bid"], unique=False)
        batch_op.create_index(
            "ix_bill_usage_generated_block_bid", ["generated_block_bid"], unique=False
        )
        batch_op.create_index(
            "ix_bill_usage_outline_item_bid", ["outline_item_bid"], unique=False
        )
        batch_op.create_index(
            "ix_bill_usage_parent_usage_bid", ["parent_usage_bid"], unique=False
        )
        batch_op.create_index(
            "ix_bill_usage_progress_record_bid", ["progress_record_bid"], unique=False
        )
        batch_op.create_index("ix_bill_usage_request_id", ["request_id"], unique=False)
        batch_op.create_index("ix_bill_usage_shifu_bid", ["shifu_bid"], unique=False)
        batch_op.create_index("ix_bill_usage_usage_bid", ["usage_bid"], unique=False)
        batch_op.create_index("ix_bill_usage_user_bid", ["user_bid"], unique=False)
        batch_op.create_index("ix_bill_usage_deleted", ["deleted"], unique=False)

    op.execute("UPDATE bill_usage SET usage_type = 1101 WHERE usage_type = 1")
    op.execute("UPDATE bill_usage SET usage_type = 1102 WHERE usage_type = 2")
    op.execute("UPDATE bill_usage SET usage_scene = 1201 WHERE usage_scene = 0")
    op.execute("UPDATE bill_usage SET usage_scene = 1202 WHERE usage_scene = 1")
    op.execute("UPDATE bill_usage SET usage_scene = 1203 WHERE usage_scene = 2")


def downgrade():
    op.execute("UPDATE bill_usage SET usage_scene = 0 WHERE usage_scene = 1201")
    op.execute("UPDATE bill_usage SET usage_scene = 1 WHERE usage_scene = 1202")
    op.execute("UPDATE bill_usage SET usage_scene = 2 WHERE usage_scene = 1203")
    op.execute("UPDATE bill_usage SET usage_type = 1 WHERE usage_type = 1101")
    op.execute("UPDATE bill_usage SET usage_type = 2 WHERE usage_type = 1102")

    with op.batch_alter_table("bill_usage", schema=None) as batch_op:
        batch_op.drop_index("idx_bill_usage_user_created")
        batch_op.drop_index("idx_bill_usage_shifu_created")
        batch_op.drop_index("idx_bill_usage_type_created")
        batch_op.drop_index("ix_bill_usage_audio_bid")
        batch_op.drop_index("ix_bill_usage_generated_block_bid")
        batch_op.drop_index("ix_bill_usage_outline_item_bid")
        batch_op.drop_index("ix_bill_usage_parent_usage_bid")
        batch_op.drop_index("ix_bill_usage_progress_record_bid")
        batch_op.drop_index("ix_bill_usage_request_id")
        batch_op.drop_index("ix_bill_usage_shifu_bid")
        batch_op.drop_index("ix_bill_usage_usage_bid")
        batch_op.drop_index("ix_bill_usage_user_bid")
        batch_op.drop_index("ix_bill_usage_deleted")

        batch_op.create_index(
            "idx_billing_usage_user_created", ["user_bid", "created_at"]
        )
        batch_op.create_index(
            "idx_billing_usage_shifu_created", ["shifu_bid", "created_at"]
        )
        batch_op.create_index(
            "idx_billing_usage_type_created", ["usage_type", "created_at"]
        )
        batch_op.create_index(
            "ix_billing_usage_records_audio_bid", ["audio_bid"], unique=False
        )
        batch_op.create_index(
            "ix_billing_usage_records_generated_block_bid",
            ["generated_block_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_usage_records_outline_item_bid",
            ["outline_item_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_usage_records_parent_usage_bid",
            ["parent_usage_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_usage_records_progress_record_bid",
            ["progress_record_bid"],
            unique=False,
        )
        batch_op.create_index(
            "ix_billing_usage_records_request_id", ["request_id"], unique=False
        )
        batch_op.create_index(
            "ix_billing_usage_records_shifu_bid", ["shifu_bid"], unique=False
        )
        batch_op.create_index(
            "ix_billing_usage_records_usage_bid", ["usage_bid"], unique=False
        )
        batch_op.create_index(
            "ix_billing_usage_records_user_bid", ["user_bid"], unique=False
        )
        batch_op.create_index(
            "ix_billing_usage_records_deleted", ["deleted"], unique=False
        )

    op.rename_table("bill_usage", "billing_usage_records")
