"""add learn_generated_elements

Revision ID: 4a1f6c8e9b2d
Revises: e1b2c3d4e5f6
Create Date: 2026-03-17 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4a1f6c8e9b2d"
down_revision = "e1b2c3d4e5f6"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    table_name = "learn_generated_elements"
    if _table_exists(table_name):
        return

    op.create_table(
        table_name,
        sa.Column("id", sa.BIGINT(), autoincrement=True, nullable=False),
        sa.Column(
            "element_bid",
            sa.String(length=64),
            nullable=False,
            server_default="",
            comment="Element business identifier",
        ),
        sa.Column(
            "progress_record_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Learn progress record business identifier",
        ),
        sa.Column(
            "user_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="User business identifier",
        ),
        sa.Column(
            "generated_block_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Source generated block business identifier",
        ),
        sa.Column(
            "outline_item_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Outline business identifier",
        ),
        sa.Column(
            "shifu_bid",
            sa.String(length=36),
            nullable=False,
            server_default="",
            comment="Shifu business identifier",
        ),
        sa.Column(
            "run_session_bid",
            sa.String(length=64),
            nullable=False,
            server_default="",
            comment="Run session business identifier",
        ),
        sa.Column(
            "run_event_seq",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Run event sequence within the session",
        ),
        sa.Column(
            "event_type",
            sa.String(length=32),
            nullable=False,
            server_default="element",
            comment="Event type: element/break/done/error/audio_segment/audio_complete/variable_update/outline_item_update",
        ),
        sa.Column(
            "role",
            sa.String(length=16),
            nullable=False,
            server_default="teacher",
            comment="Element role: teacher/student/ui",
        ),
        sa.Column(
            "element_index",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Listen-mode navigation index",
        ),
        sa.Column(
            "element_type",
            sa.String(length=32),
            nullable=False,
            server_default="",
            comment="Element type: interaction/sandbox/picture/video",
        ),
        sa.Column(
            "element_type_code",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Element type code",
        ),
        sa.Column(
            "change_type",
            sa.String(length=16),
            nullable=False,
            server_default="",
            comment="Change type: render/diff",
        ),
        sa.Column(
            "target_element_bid",
            sa.String(length=64),
            nullable=False,
            server_default="",
            comment="Diff target element business identifier",
        ),
        sa.Column(
            "is_navigable",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
            comment="Navigation flag: 1=navigable, 0=non-navigable",
        ),
        sa.Column(
            "is_final",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Final snapshot flag: 1=final, 0=partial",
        ),
        sa.Column(
            "content_text",
            sa.Text(),
            nullable=False,
            comment="Element textual content snapshot",
        ),
        sa.Column(
            "payload",
            sa.Text(),
            nullable=False,
            comment="Element payload JSON",
        ),
        sa.Column(
            "deleted",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Deletion flag: 0=active, 1=deleted",
        ),
        sa.Column(
            "status",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
            comment="Record status: 1=active, 0=history",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            comment="Last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Listen-mode generated elements",
    )
    op.create_index("ix_lge_element_bid", table_name, ["element_bid"], unique=False)
    op.create_index(
        "ix_lge_progress_record_bid", table_name, ["progress_record_bid"], unique=False
    )
    op.create_index("ix_lge_user_bid", table_name, ["user_bid"], unique=False)
    op.create_index(
        "ix_lge_generated_block_bid", table_name, ["generated_block_bid"], unique=False
    )
    op.create_index(
        "ix_lge_outline_item_bid", table_name, ["outline_item_bid"], unique=False
    )
    op.create_index("ix_lge_shifu_bid", table_name, ["shifu_bid"], unique=False)
    op.create_index(
        "ix_lge_run_session_bid", table_name, ["run_session_bid"], unique=False
    )
    op.create_index("ix_lge_run_event_seq", table_name, ["run_event_seq"], unique=False)
    op.create_index("ix_lge_event_type", table_name, ["event_type"], unique=False)
    op.create_index("ix_lge_element_index", table_name, ["element_index"], unique=False)
    op.create_index("ix_lge_element_type", table_name, ["element_type"], unique=False)
    op.create_index(
        "ix_lge_target_element_bid", table_name, ["target_element_bid"], unique=False
    )
    op.create_index("ix_lge_is_navigable", table_name, ["is_navigable"], unique=False)
    op.create_index("ix_lge_is_final", table_name, ["is_final"], unique=False)
    op.create_index("ix_lge_deleted", table_name, ["deleted"], unique=False)
    op.create_index("ix_lge_status", table_name, ["status"], unique=False)


def downgrade():
    table_name = "learn_generated_elements"
    if not _table_exists(table_name):
        return

    op.drop_index("ix_lge_status", table_name=table_name)
    op.drop_index("ix_lge_deleted", table_name=table_name)
    op.drop_index("ix_lge_is_final", table_name=table_name)
    op.drop_index("ix_lge_is_navigable", table_name=table_name)
    op.drop_index("ix_lge_target_element_bid", table_name=table_name)
    op.drop_index("ix_lge_element_type", table_name=table_name)
    op.drop_index("ix_lge_element_index", table_name=table_name)
    op.drop_index("ix_lge_event_type", table_name=table_name)
    op.drop_index("ix_lge_run_event_seq", table_name=table_name)
    op.drop_index("ix_lge_run_session_bid", table_name=table_name)
    op.drop_index("ix_lge_shifu_bid", table_name=table_name)
    op.drop_index("ix_lge_outline_item_bid", table_name=table_name)
    op.drop_index("ix_lge_generated_block_bid", table_name=table_name)
    op.drop_index("ix_lge_user_bid", table_name=table_name)
    op.drop_index("ix_lge_progress_record_bid", table_name=table_name)
    op.drop_index("ix_lge_element_bid", table_name=table_name)
    op.drop_table(table_name)
