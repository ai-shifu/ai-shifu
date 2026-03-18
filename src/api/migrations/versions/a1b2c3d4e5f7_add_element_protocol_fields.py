"""add element protocol fields: is_renderable, is_new, is_marker, sequence_number, is_speakable, audio_url, audio_segments

Revision ID: a1b2c3d4e5f7
Revises: 4a1f6c8e9b2d
Create Date: 2026-03-18 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f7"
down_revision = "4a1f6c8e9b2d"
branch_labels = None
depends_on = None

TABLE_NAME = "learn_generated_elements"


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    if not _table_exists(TABLE_NAME):
        return

    new_columns = [
        (
            "is_renderable",
            sa.SmallInteger(),
            1,
            "Renderable flag: 1=renderable, 0=non-renderable",
        ),
        (
            "is_new",
            sa.SmallInteger(),
            1,
            "New element flag: 1=creates new, 0=patches existing",
        ),
        (
            "is_marker",
            sa.SmallInteger(),
            0,
            "Marker flag: 1=navigation anchor, 0=normal",
        ),
        (
            "sequence_number",
            sa.Integer(),
            0,
            "Element generation sequence within run session",
        ),
        ("is_speakable", sa.SmallInteger(), 0, "Speakable flag: 1=needs TTS, 0=silent"),
        ("audio_url", sa.String(512), "", "Complete audio URL"),
        ("audio_segments", sa.Text(), "[]", "Audio segment trail as JSON array"),
    ]

    for col_name, col_type, default, comment in new_columns:
        if _column_exists(TABLE_NAME, col_name):
            continue
        try:
            # MySQL TEXT/BLOB columns do not support DEFAULT values
            col_kwargs = dict(nullable=False, comment=comment)
            if not isinstance(col_type, (sa.Text, sa.LargeBinary)):
                col_kwargs["server_default"] = str(default)
            op.add_column(
                TABLE_NAME,
                sa.Column(col_name, col_type, **col_kwargs),
            )
        except SQLAlchemyError:
            pass

    # Add indexes for high-frequency query columns
    index_columns = [
        "is_renderable",
        "is_new",
        "is_marker",
        "sequence_number",
        "is_speakable",
    ]
    for col_name in index_columns:
        idx_name = f"ix_{TABLE_NAME}_{col_name}"
        try:
            op.create_index(idx_name, TABLE_NAME, [col_name])
        except SQLAlchemyError:
            pass


def downgrade() -> None:
    if not _table_exists(TABLE_NAME):
        return

    index_columns = [
        "is_renderable",
        "is_new",
        "is_marker",
        "sequence_number",
        "is_speakable",
    ]
    for col_name in index_columns:
        idx_name = f"ix_{TABLE_NAME}_{col_name}"
        try:
            op.drop_index(idx_name, table_name=TABLE_NAME)
        except SQLAlchemyError:
            pass

    drop_columns = [
        "audio_segments",
        "audio_url",
        "is_speakable",
        "sequence_number",
        "is_marker",
        "is_new",
        "is_renderable",
    ]
    for col_name in drop_columns:
        if _column_exists(TABLE_NAME, col_name):
            try:
                op.drop_column(TABLE_NAME, col_name)
            except SQLAlchemyError:
                pass
