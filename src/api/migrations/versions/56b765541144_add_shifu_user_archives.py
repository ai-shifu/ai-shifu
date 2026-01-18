"""add shifu_user_archives and drop legacy archive columns

Revision ID: 56b765541144
Revises: b5f2d3a9c1e4
Create Date: 2026-01-18 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "56b765541144"
down_revision = "b5f2d3a9c1e4"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        columns = inspector.get_columns(table_name)
    except Exception:
        return False
    return any(column["name"] == column_name for column in columns)


def _create_shifu_user_archives_table() -> None:
    op.create_table(
        "shifu_user_archives",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "shifu_bid",
            sa.String(length=32),
            nullable=False,
            index=True,
            server_default="",
            comment="Shifu business identifier",
        ),
        sa.Column(
            "user_bid",
            sa.String(length=32),
            nullable=False,
            index=True,
            server_default="",
            comment="User business identifier",
        ),
        sa.Column(
            "archived",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Archive flag: 0=active, 1=archived",
        ),
        sa.Column(
            "archived_at",
            sa.DateTime(),
            nullable=True,
            comment="Archived timestamp",
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
            onupdate=sa.func.now(),
            comment="Last update timestamp",
        ),
        sa.UniqueConstraint(
            "shifu_bid", "user_bid", name="uk_shifu_user_archive_bid_user"
        ),
        mysql_engine="InnoDB",
    )


def _backfill_owner_archives_from_table(source_table_name: str) -> None:
    if not _table_exists(source_table_name):
        return
    required_columns = ("shifu_bid", "created_user_bid", "archived", "deleted")
    if not all(_column_exists(source_table_name, name) for name in required_columns):
        return

    bind = op.get_bind()
    dialect = bind.dialect.name
    now_expr = "NOW()" if dialect == "mysql" else "CURRENT_TIMESTAMP"
    archived_at_expr = (
        f"COALESCE(s.archived_at, {now_expr})"
        if _column_exists(source_table_name, "archived_at")
        else now_expr
    )

    if dialect == "mysql":
        op.execute(
            f"""
            INSERT INTO shifu_user_archives (shifu_bid, user_bid, archived, archived_at, created_at, updated_at)
            SELECT DISTINCT
                s.shifu_bid,
                s.created_user_bid,
                1,
                {archived_at_expr},
                {now_expr},
                {now_expr}
            FROM {source_table_name} s
            WHERE s.deleted = 0 AND s.archived = 1 AND s.created_user_bid <> ''
            ON DUPLICATE KEY UPDATE
                archived = VALUES(archived),
                archived_at = VALUES(archived_at),
                updated_at = VALUES(updated_at)
            """
        )
        return

    # Best-effort for SQLite/Postgres: do not attempt vendor-specific upsert.
    op.execute(
        f"""
        INSERT INTO shifu_user_archives (shifu_bid, user_bid, archived, archived_at, created_at, updated_at)
        SELECT DISTINCT
            s.shifu_bid,
            s.created_user_bid,
            1,
            {archived_at_expr},
            {now_expr},
            {now_expr}
        FROM {source_table_name} s
        WHERE s.deleted = 0 AND s.archived = 1 AND s.created_user_bid <> ''
        """
    )


def _drop_legacy_archive_columns(table_name: str) -> None:
    if not _table_exists(table_name):
        return
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        if _column_exists(table_name, "archived_at"):
            batch_op.drop_column("archived_at")
        if _column_exists(table_name, "archived"):
            batch_op.drop_column("archived")


def upgrade():
    if not _table_exists("shifu_user_archives"):
        _create_shifu_user_archives_table()

    # Backfill from legacy global archive columns (if they exist), then drop them.
    _backfill_owner_archives_from_table("shifu_draft_shifus")
    _backfill_owner_archives_from_table("shifu_published_shifus")

    _drop_legacy_archive_columns("shifu_published_shifus")
    _drop_legacy_archive_columns("shifu_draft_shifus")


def downgrade():
    archived_column = sa.Column(
        "archived",
        sa.SmallInteger(),
        nullable=False,
        server_default=sa.text("0"),
        comment="Archive flag: 0=active, 1=archived",
    )
    archived_at_column = sa.Column(
        "archived_at",
        sa.DateTime(),
        nullable=True,
        comment="Archived timestamp",
    )

    for table_name in ("shifu_draft_shifus", "shifu_published_shifus"):
        if not _table_exists(table_name):
            continue
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            if not _column_exists(table_name, "archived"):
                batch_op.add_column(archived_column.copy())
            if not _column_exists(table_name, "archived_at"):
                batch_op.add_column(archived_at_column.copy())

    if _table_exists("shifu_user_archives"):
        op.drop_table("shifu_user_archives")
