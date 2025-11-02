"""Move creator flag to user_users and drop legacy admin flag.

Revision ID: 4d8f8b9a1c2e
Revises: b99fb0d80bab
Create Date: 2025-10-31 08:12:34.000000

"""

from __future__ import annotations

from typing import Iterable, Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "4d8f8b9a1c2e"
down_revision = "b99fb0d80bab"
branch_labels = None
depends_on = None

TRUTHY_VALUES = {"1", "true", "yes", "on", "t", "y"}
CHUNK_SIZE = 500


def _has_table(inspector: sa.engine.reflection.Inspector, table_name: str) -> bool:
    try:
        return inspector.has_table(table_name)
    except Exception:  # pragma: no cover - defensive
        return False


def _has_column(
    inspector: sa.engine.reflection.Inspector, table_name: str, column_name: str
) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return column_name in {
        column["name"] for column in inspector.get_columns(table_name)
    }


def _has_index(
    inspector: sa.engine.reflection.Inspector, table_name: str, index_name: str
) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def _chunked(values: Sequence[str], size: int = CHUNK_SIZE) -> Iterable[Sequence[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def upgrade() -> None:
    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_creator",
                sa.SmallInteger(),
                nullable=False,
                server_default="0",
                comment="Creator flag: 0=regular user, 1=creator",
            )
        )
        batch_op.create_index(
            "ix_user_users_is_creator",
            ["is_creator"],
            unique=False,
        )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    metadata = sa.MetaData(bind=bind)
    user_users = sa.Table("user_users", metadata, autoload_with=bind)

    def apply_updates(user_ids: Sequence[str]) -> None:
        for chunk in _chunked(list(user_ids)):
            if not chunk:
                continue
            bind.execute(
                user_users.update()
                .where(user_users.c.user_bid.in_(tuple(chunk)))
                .values(is_creator=1)
            )

    user_profile_table = None

    # Backfill from user_profile role flags when available.
    if _has_table(inspector, "user_profile"):
        user_profile_table = sa.Table("user_profile", metadata, autoload_with=bind)
        query = (
            sa.select(user_profile_table.c.user_id, user_profile_table.c.profile_value)
            .where(
                user_profile_table.c.profile_key == sa.literal("sys_user_is_creator")
            )
            .where(user_profile_table.c.status != 0)
            .order_by(user_profile_table.c.id.desc())
        )
        result = bind.execute(query)
        seen = set()
        updates = []
        for row in result:
            user_id = row.user_id
            if user_id in seen:
                continue
            seen.add(user_id)
            value = row.profile_value
            if value is None:
                continue
            if str(value).strip().lower() in TRUTHY_VALUES:
                updates.append(user_id)
        if updates:
            apply_updates(updates)

    # Fall back to legacy user_info columns when present.
    if _has_column(inspector, "user_info", "is_creator"):
        user_info = sa.Table("user_info", metadata, autoload_with=bind)
        result = bind.execute(sa.select(user_info.c.user_id, user_info.c.is_creator))
        updates = [
            row.user_id
            for row in result
            if row.is_creator is not None
            and str(row.is_creator).strip().lower() in TRUTHY_VALUES
        ]
        if updates:
            apply_updates(updates)

    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.alter_column("is_creator", server_default=None)

    if _has_column(inspector, "user_info", "is_admin"):
        with op.batch_alter_table("user_info", schema=None) as batch_op:
            batch_op.drop_column("is_admin")

    if user_profile_table is not None:
        bind.execute(
            user_profile_table.delete().where(
                user_profile_table.c.profile_key.in_(
                    ("sys_user_is_admin", "sys_user_is_creator")
                )
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "user_info") and not _has_column(
        inspector, "user_info", "is_admin"
    ):
        with op.batch_alter_table("user_info", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "is_admin",
                    sa.Boolean(),
                    nullable=False,
                    server_default="0",
                    comment="is admin",
                )
            )
            batch_op.alter_column("is_admin", server_default=None)

    if _has_index(inspector, "user_users", "ix_user_users_is_creator"):
        with op.batch_alter_table("user_users", schema=None) as batch_op:
            batch_op.drop_index("ix_user_users_is_creator")
    with op.batch_alter_table("user_users", schema=None) as batch_op:
        batch_op.drop_column("is_creator")
