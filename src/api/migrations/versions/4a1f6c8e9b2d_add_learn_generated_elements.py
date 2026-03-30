"""add learn_generated_elements with element protocol fields

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

TABLE_NAME = "learn_generated_elements"
BASE_INDEX_NAMES = [
    "ix_lge_element_bid",
    "ix_lge_progress_record_bid",
    "ix_lge_user_bid",
    "ix_lge_generated_block_bid",
    "ix_lge_outline_item_bid",
    "ix_lge_shifu_bid",
    "ix_lge_run_session_bid",
    "ix_lge_run_event_seq",
    "ix_lge_event_type",
    "ix_lge_element_index",
    "ix_lge_element_type",
    "ix_lge_target_element_bid",
    "ix_lge_is_navigable",
    "ix_lge_is_final",
    "ix_lge_deleted",
    "ix_lge_status",
]
ELEMENT_PROTOCOL_COLUMNS = [
    (
        "is_renderable",
        sa.SmallInteger(),
        sa.text("1"),
        "Renderable flag: 1=renderable, 0=non-renderable",
    ),
    (
        "is_new",
        sa.SmallInteger(),
        sa.text("1"),
        "New element flag: 1=creates new, 0=patches existing",
    ),
    (
        "is_marker",
        sa.SmallInteger(),
        sa.text("0"),
        "Marker flag: 1=navigation anchor, 0=normal",
    ),
    (
        "sequence_number",
        sa.Integer(),
        sa.text("0"),
        "Element generation sequence within run session",
    ),
    (
        "is_speakable",
        sa.SmallInteger(),
        sa.text("0"),
        "Speakable flag: 1=needs TTS, 0=silent",
    ),
    ("audio_url", sa.String(length=512), "", "Complete audio URL"),
    ("audio_segments", sa.Text(), None, "Audio segment trail as JSON array"),
]
ELEMENT_PROTOCOL_INDEX_COLUMNS = [
    "is_renderable",
    "is_new",
    "is_marker",
    "sequence_number",
    "is_speakable",
]


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column.get("name") == column_name for column in columns)


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(index.get("name") == index_name for index in indexes)


def _add_element_protocol_columns() -> None:
    for column_name, column_type, server_default, comment in ELEMENT_PROTOCOL_COLUMNS:
        if _column_exists(TABLE_NAME, column_name):
            continue

        if column_name == "audio_segments":
            op.add_column(
                TABLE_NAME,
                sa.Column(
                    column_name,
                    column_type,
                    nullable=True,
                    comment=comment,
                ),
            )
            continue

        column_kwargs = {
            "nullable": False,
            "comment": comment,
        }
        if server_default is not None:
            column_kwargs["server_default"] = server_default

        op.add_column(
            TABLE_NAME,
            sa.Column(column_name, column_type, **column_kwargs),
        )

    if _column_exists(TABLE_NAME, "audio_segments"):
        op.execute(
            f"UPDATE {TABLE_NAME} SET audio_segments = '[]' WHERE audio_segments IS NULL"
        )
        with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
            batch_op.alter_column(
                "audio_segments",
                existing_type=sa.Text(),
                nullable=False,
            )


def _create_element_protocol_indexes() -> None:
    for column_name in ELEMENT_PROTOCOL_INDEX_COLUMNS:
        index_name = f"ix_{TABLE_NAME}_{column_name}"
        if _index_exists(TABLE_NAME, index_name):
            continue
        op.create_index(index_name, TABLE_NAME, [column_name], unique=False)


def upgrade():
    if _table_exists(TABLE_NAME):
        _add_element_protocol_columns()
        _create_element_protocol_indexes()
        return

    op.create_table(
        TABLE_NAME,
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
            "is_renderable",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
            comment="Renderable flag: 1=renderable, 0=non-renderable",
        ),
        sa.Column(
            "is_new",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
            comment="New element flag: 1=creates new, 0=patches existing",
        ),
        sa.Column(
            "is_marker",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Marker flag: 1=navigation anchor, 0=normal",
        ),
        sa.Column(
            "sequence_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Element generation sequence within run session",
        ),
        sa.Column(
            "is_speakable",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Speakable flag: 1=needs TTS, 0=silent",
        ),
        sa.Column(
            "audio_url",
            sa.String(length=512),
            nullable=False,
            server_default="",
            comment="Complete audio URL",
        ),
        sa.Column(
            "audio_segments",
            sa.Text(),
            nullable=False,
            comment="Audio segment trail as JSON array",
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
    op.create_index("ix_lge_element_bid", TABLE_NAME, ["element_bid"], unique=False)
    op.create_index(
        "ix_lge_progress_record_bid", TABLE_NAME, ["progress_record_bid"], unique=False
    )
    op.create_index("ix_lge_user_bid", TABLE_NAME, ["user_bid"], unique=False)
    op.create_index(
        "ix_lge_generated_block_bid", TABLE_NAME, ["generated_block_bid"], unique=False
    )
    op.create_index(
        "ix_lge_outline_item_bid", TABLE_NAME, ["outline_item_bid"], unique=False
    )
    op.create_index("ix_lge_shifu_bid", TABLE_NAME, ["shifu_bid"], unique=False)
    op.create_index(
        "ix_lge_run_session_bid", TABLE_NAME, ["run_session_bid"], unique=False
    )
    op.create_index("ix_lge_run_event_seq", TABLE_NAME, ["run_event_seq"], unique=False)
    op.create_index("ix_lge_event_type", TABLE_NAME, ["event_type"], unique=False)
    op.create_index("ix_lge_element_index", TABLE_NAME, ["element_index"], unique=False)
    op.create_index("ix_lge_element_type", TABLE_NAME, ["element_type"], unique=False)
    op.create_index(
        "ix_lge_target_element_bid", TABLE_NAME, ["target_element_bid"], unique=False
    )
    op.create_index("ix_lge_is_navigable", TABLE_NAME, ["is_navigable"], unique=False)
    op.create_index("ix_lge_is_final", TABLE_NAME, ["is_final"], unique=False)
    op.create_index("ix_lge_deleted", TABLE_NAME, ["deleted"], unique=False)
    op.create_index("ix_lge_status", TABLE_NAME, ["status"], unique=False)
    _create_element_protocol_indexes()


def downgrade():
    if not _table_exists(TABLE_NAME):
        return

    for column_name in ELEMENT_PROTOCOL_INDEX_COLUMNS:
        index_name = f"ix_{TABLE_NAME}_{column_name}"
        if _index_exists(TABLE_NAME, index_name):
            op.drop_index(index_name, table_name=TABLE_NAME)

    for index_name in reversed(BASE_INDEX_NAMES):
        if _index_exists(TABLE_NAME, index_name):
            op.drop_index(index_name, table_name=TABLE_NAME)

    op.drop_table(TABLE_NAME)
