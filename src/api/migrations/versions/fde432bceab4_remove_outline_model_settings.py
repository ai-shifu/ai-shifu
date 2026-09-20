"""Remove outline models and temperatures in favor of course-owned settings.

Revision ID: fde432bceab4
Revises: e5a7c9d1f3b4
Create Date: 2026-09-18 10:59:38 UTC

Regenerated from the narrowed SQLAlchemy change; prompts and follow-up status
remain on both outline tables. Deploy with the matching application code; older
versions read these columns. Downgrade restores empty inherited settings, not
discarded overrides.
"""

from alembic import op
import sqlalchemy as sa

revision = "fde432bceab4"
down_revision = "e5a7c9d1f3b4"
branch_labels = None
depends_on = None

_TABLES = ("shifu_draft_outline_items", "shifu_published_outline_items")
_COLUMNS = (
    "llm",
    "llm_temperature",
    "ask_llm",
    "ask_llm_temperature",
)


def upgrade() -> None:
    """Remove outline models and temperatures, preserving prompts and content."""
    for table in _TABLES:
        if op.get_bind().dialect.name == "mysql":
            # One online table rebuild; refuse a fallback that would lock writers.
            drops = ", ".join(f"DROP COLUMN `{column}`" for column in _COLUMNS)
            op.execute(f"ALTER TABLE `{table}` {drops}, ALGORITHM=INPLACE, LOCK=NONE")
        else:
            with op.batch_alter_table(table) as batch_op:
                for column in _COLUMNS:
                    batch_op.drop_column(column)


def downgrade() -> None:
    """Restore the legacy shape with empty settings on existing rows."""
    for table in reversed(_TABLES):
        definitions = (
            ("llm", sa.String(100), "", "LLM model name"),
            ("llm_temperature", sa.DECIMAL(10, 2), 0, "LLM temperature parameter"),
            ("ask_llm", sa.String(100), "", "Ask agent LLM model"),
            ("ask_llm_temperature", sa.DECIMAL(10, 2), 0, "Ask agent LLM temperature"),
        )
        # Add nullable columns first so populated tables can be downgraded,
        # without replacing retained prompts or follow-up status.
        with op.batch_alter_table(table) as batch_op:
            for name, column_type, _default, comment in definitions:
                batch_op.add_column(
                    sa.Column(name, column_type, nullable=True, comment=comment)
                )
        restored = sa.table(table, *(sa.column(name) for name in _COLUMNS))
        op.execute(
            restored.update().values(
                {name: default for name, _type, default, _comment in definitions}
            )
        )
        with op.batch_alter_table(table) as batch_op:
            for name, column_type, _default, _comment in definitions:
                batch_op.alter_column(name, existing_type=column_type, nullable=False)
