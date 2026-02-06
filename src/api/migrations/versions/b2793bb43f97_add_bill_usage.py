"""add bill usage table

Revision ID: b2793bb43f97
Revises: 9f3a0c3aebe0
Create Date: 2026-02-05 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "b2793bb43f97"
down_revision = "9f3a0c3aebe0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bill_usage",
        sa.Column(
            "id",
            mysql.BIGINT(),
            autoincrement=True,
            nullable=False,
            comment="Unique ID",
        ),
        sa.Column(
            "usage_bid",
            sa.String(length=36),
            nullable=False,
            comment="Usage business identifier",
        ),
        sa.Column(
            "parent_usage_bid",
            sa.String(length=36),
            nullable=False,
            comment="Parent usage business identifier",
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
            "outline_item_bid",
            sa.String(length=36),
            nullable=False,
            comment="Outline item business identifier",
        ),
        sa.Column(
            "progress_record_bid",
            sa.String(length=36),
            nullable=False,
            comment="Progress record business identifier",
        ),
        sa.Column(
            "generated_block_bid",
            sa.String(length=36),
            nullable=False,
            comment="Generated block business identifier",
        ),
        sa.Column(
            "audio_bid",
            sa.String(length=36),
            nullable=False,
            comment="Audio business identifier",
        ),
        sa.Column(
            "request_id",
            sa.String(length=64),
            nullable=False,
            comment="Request identifier (X-Request-ID)",
        ),
        sa.Column(
            "trace_id",
            sa.String(length=64),
            nullable=False,
            comment="Trace identifier (Langfuse)",
        ),
        sa.Column(
            "usage_type",
            sa.SmallInteger(),
            nullable=False,
            comment="Usage type: 1=LLM, 2=TTS",
        ),
        sa.Column(
            "record_level",
            sa.SmallInteger(),
            nullable=False,
            comment="Record level: 0=request, 1=segment",
        ),
        sa.Column(
            "usage_scene",
            sa.SmallInteger(),
            nullable=False,
            comment="Usage scene: 0=debug, 1=preview, 2=production",
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
            "is_stream",
            sa.SmallInteger(),
            nullable=False,
            comment="Is stream: 0=no, 1=yes",
        ),
        sa.Column(
            "input",
            sa.Integer(),
            nullable=False,
            comment="Input usage (tokens for LLM, chars for TTS)",
        ),
        sa.Column(
            "input_cache",
            sa.Integer(),
            nullable=False,
            comment="Cached input tokens (LLM only)",
        ),
        sa.Column(
            "output",
            sa.Integer(),
            nullable=False,
            comment="Output usage (tokens for LLM, chars for TTS)",
        ),
        sa.Column(
            "total",
            sa.Integer(),
            nullable=False,
            comment="Total usage (tokens for LLM, chars for TTS)",
        ),
        sa.Column(
            "word_count",
            sa.Integer(),
            nullable=False,
            comment="TTS provider word count",
        ),
        sa.Column(
            "duration_ms",
            sa.Integer(),
            nullable=False,
            comment="TTS duration in milliseconds",
        ),
        sa.Column(
            "latency_ms",
            sa.Integer(),
            nullable=False,
            comment="Latency in milliseconds",
        ),
        sa.Column(
            "segment_index",
            sa.Integer(),
            nullable=False,
            comment="Segment index for segment records",
        ),
        sa.Column(
            "segment_count",
            sa.Integer(),
            nullable=False,
            comment="Number of segments",
        ),
        sa.Column(
            "billable",
            sa.SmallInteger(),
            nullable=False,
            comment="Billable: 0=no, 1=yes",
        ),
        sa.Column(
            "status",
            sa.SmallInteger(),
            nullable=False,
            comment="Status: 0=success, 1=failed",
        ),
        sa.Column("error_message", sa.Text(), nullable=True, comment="Error message"),
        sa.Column("extra", sa.JSON(), nullable=True),
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
    )
    with op.batch_alter_table("bill_usage", schema=None) as batch_op:
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
            "ix_bill_usage_progress_record_bid",
            ["progress_record_bid"],
            unique=False,
        )
        batch_op.create_index("ix_bill_usage_request_id", ["request_id"], unique=False)
        batch_op.create_index("ix_bill_usage_shifu_bid", ["shifu_bid"], unique=False)
        batch_op.create_index("ix_bill_usage_usage_bid", ["usage_bid"], unique=False)
        batch_op.create_index("ix_bill_usage_user_bid", ["user_bid"], unique=False)
        batch_op.create_index("ix_bill_usage_deleted", ["deleted"], unique=False)


def downgrade():
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

    op.drop_table("bill_usage")
