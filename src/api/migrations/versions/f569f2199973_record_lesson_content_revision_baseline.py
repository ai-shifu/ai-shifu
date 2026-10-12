"""Record the lesson content revision for a learning attempt.

Revision ID: f569f2199973
Revises: fde432bceab4
Create Date: 2026-10-12 06:10:42.328380

Generated against an isolated pre-change schema, then reviewed for online MySQL
DDL. Existing sessions remain NULL; current content cannot establish history.
"""

from alembic import op
from sqlalchemy import Column
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.exc import OperationalError

revision = "f569f2199973"
down_revision = "fde432bceab4"
branch_labels = None
depends_on = None

_COMMENT = (
    "Lesson content (MarkdownFlow script) revision saved with the first "
    "messages of a learning attempt; NULL legacy/unstarted, 0 unknown"
)


def upgrade():
    if op.get_bind().dialect.name == "mysql":
        statement = (
            "ALTER TABLE `learn_agent_sessions` "
            f"ADD COLUMN `content_revision` BIGINT NULL COMMENT '{_COMMENT}', "
        )
        try:
            # INSTANT only permits the default lock clause. Offline SQL keeps
            # this explicit algorithm and requires deployment-time review.
            op.execute(f"{statement}ALGORITHM=INSTANT")
        except OperationalError as exc:
            args = getattr(exc.orig, "args", ())
            if not args or args[0] not in (1845, 1846):
                raise
            # Some deployed builds reject INSTANT. Only that explicit refusal
            # permits a rebuild; never fall back to COPY or a blocking lock.
            op.execute(f"{statement}ALGORITHM=INPLACE, LOCK=NONE")
    else:
        op.add_column(
            "learn_agent_sessions",
            Column("content_revision", BIGINT(), nullable=True, comment=_COMMENT),
        )


def downgrade():
    op.drop_column("learn_agent_sessions", "content_revision")
