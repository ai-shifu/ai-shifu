"""add demo shifu json file

Revision ID: a4d68cce5ce6
Revises: 21a3e778ef01
Create Date: 2025-11-12 14:41:07.381333

"""

from alembic import op
import sqlalchemy as sa
import os

# revision identifiers, used by Alembic.
revision = "a4d68cce5ce6"
down_revision = "21a3e778ef01"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _add_tts_columns(table_name: str) -> None:
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        if not _column_exists(table_name, "tts_enabled"):
            batch_op.add_column(
                sa.Column(
                    "tts_enabled",
                    sa.SmallInteger(),
                    nullable=False,
                    server_default=sa.text("0"),
                    comment="TTS enabled: 0=disabled, 1=enabled",
                )
            )
        if not _column_exists(table_name, "tts_provider"):
            batch_op.add_column(
                sa.Column(
                    "tts_provider",
                    sa.String(length=32),
                    nullable=False,
                    server_default=sa.text("''"),
                    comment=(
                        "TTS provider: minimax, volcengine, baidu, aliyun "
                        "(empty=use system default)"
                    ),
                )
            )
        if not _column_exists(table_name, "tts_model"):
            batch_op.add_column(
                sa.Column(
                    "tts_model",
                    sa.String(length=64),
                    nullable=False,
                    server_default=sa.text("''"),
                    comment=(
                        "TTS model/resource ID (e.g., seed-tts-1.0, seed-tts-2.0, "
                        "speech-01-turbo)"
                    ),
                )
            )
        if not _column_exists(table_name, "tts_voice_id"):
            batch_op.add_column(
                sa.Column(
                    "tts_voice_id",
                    sa.String(length=64),
                    nullable=False,
                    server_default=sa.text("''"),
                    comment="TTS voice ID",
                )
            )
        if not _column_exists(table_name, "tts_speed"):
            batch_op.add_column(
                sa.Column(
                    "tts_speed",
                    sa.DECIMAL(precision=6, scale=2),
                    nullable=False,
                    server_default=sa.text("1.0"),
                    comment="TTS speech speed (provider-specific range)",
                )
            )
        if not _column_exists(table_name, "tts_pitch"):
            batch_op.add_column(
                sa.Column(
                    "tts_pitch",
                    sa.SmallInteger(),
                    nullable=False,
                    server_default=sa.text("0"),
                    comment="TTS pitch adjustment (provider-specific range)",
                )
            )
        if not _column_exists(table_name, "tts_emotion"):
            batch_op.add_column(
                sa.Column(
                    "tts_emotion",
                    sa.String(length=32),
                    nullable=False,
                    server_default=sa.text("''"),
                    comment="TTS emotion setting",
                )
            )


def _drop_tts_columns(table_name: str) -> None:
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        if _column_exists(table_name, "tts_emotion"):
            batch_op.drop_column("tts_emotion")
        if _column_exists(table_name, "tts_pitch"):
            batch_op.drop_column("tts_pitch")
        if _column_exists(table_name, "tts_speed"):
            batch_op.drop_column("tts_speed")
        if _column_exists(table_name, "tts_voice_id"):
            batch_op.drop_column("tts_voice_id")
        if _column_exists(table_name, "tts_model"):
            batch_op.drop_column("tts_model")
        if _column_exists(table_name, "tts_provider"):
            batch_op.drop_column("tts_provider")
        if _column_exists(table_name, "tts_enabled"):
            batch_op.drop_column("tts_enabled")


def upgrade():
    from flask import current_app as app
    from flaskr.command.update_shifu_demo import update_demo_shifu

    _add_tts_columns("shifu_draft_shifus")
    _add_tts_columns("shifu_published_shifus")
    try:
        with app.app_context():
            if os.getenv("SKIP_DEMO_SHIFU_IMPORT"):
                app.logger.info("Skip demo shifu import due to SKIP_DEMO_SHIFU_IMPORT")
                return
            update_demo_shifu(app)
    finally:
        _drop_tts_columns("shifu_published_shifus")
        _drop_tts_columns("shifu_draft_shifus")


def downgrade():
    pass
