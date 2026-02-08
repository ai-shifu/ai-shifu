"""backfill variable tables

Revision ID: 6b956399315e
Revises: 716efaaeb662
Create Date: 2026-01-27 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "6b956399315e"
down_revision = "716efaaeb662"
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
    except Exception:  # pragma: no cover - best effort for migration environments
        return False
    return any(col.get("name") == column_name for col in columns)


def upgrade():
    if not _table_exists("var_variables"):
        return
    if not _table_exists("var_variable_values"):
        return

    # Backfill definitions from legacy profile_item.
    if _table_exists("profile_item"):
        is_hidden_expr = (
            "COALESCE(p.is_hidden, 0)"
            if _column_exists("profile_item", "is_hidden")
            else "0"
        )
        created_user_expr = (
            "COALESCE(p.created_by, '')"
            if _column_exists("profile_item", "created_by")
            else "''"
        )
        updated_user_expr = (
            "COALESCE(p.updated_by, '')"
            if _column_exists("profile_item", "updated_by")
            else "''"
        )
        op.execute(
            sa.text(
                f"""
                INSERT INTO var_variables (
                    variable_bid,
                    shifu_bid,
                    `key`,
                    is_hidden,
                    deleted,
                    created_at,
                    created_user_bid,
                    updated_at,
                    updated_user_bid
                )
                SELECT
                    p.profile_id,
                    p.parent_id,
                    p.profile_key,
                    {is_hidden_expr},
                    CASE WHEN COALESCE(p.status, 0) = 1 THEN 0 ELSE 1 END,
                    p.created,
                    {created_user_expr},
                    p.updated,
                    {updated_user_expr}
                FROM profile_item p
                LEFT JOIN var_variables d
                    ON d.variable_bid = p.profile_id
                WHERE d.id IS NULL
                """
            )
        )

    # Backfill user values from legacy user_profile.
    if _table_exists("user_profile"):
        op.execute(
            sa.text(
                """
                INSERT INTO var_variable_values (
                    variable_value_bid,
                    user_bid,
                    shifu_bid,
                    variable_bid,
                    `key`,
                    `value`,
                    deleted,
                    created_at,
                    updated_at
                )
                SELECT
                    REPLACE(UUID(), '-', ''),
                    u.user_id,
                    '',
                    u.profile_id,
                    u.profile_key,
                    u.profile_value,
                    CASE WHEN COALESCE(u.status, 0) = 1 THEN 0 ELSE 1 END,
                    u.created,
                    u.updated
                FROM (
                    SELECT
                        user_id,
                        profile_id,
                        profile_key,
                        profile_value,
                        MAX(COALESCE(status, 0)) AS status,
                        created,
                        MAX(updated) AS updated
                    FROM user_profile
                    GROUP BY
                        user_id,
                        profile_id,
                        profile_key,
                        profile_value,
                        created
                ) u
                LEFT JOIN var_variable_values v
                    ON v.user_bid = u.user_id
                    AND v.variable_bid = u.profile_id
                    AND v.`key` = u.profile_key
                    AND v.created_at = u.created
                    AND v.`value` = u.profile_value
                WHERE v.id IS NULL
                """
            )
        )


def downgrade():
    # Data backfill is intentionally irreversible.
    pass
