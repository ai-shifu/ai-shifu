"""backfill promo campaign tables from active tables

Revision ID: ef7dbc5a8be3
Revises: c221d355ffb7
Create Date: 2026-01-27

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "ef7dbc5a8be3"
down_revision = "c221d355ffb7"
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


def upgrade():
    if not _table_exists("promo_campaigns") or not _table_exists(
        "promo_campaign_applications"
    ):
        return

    if not _table_exists("active") or not _table_exists("active_user_record"):
        return

    required_active_cols = (
        "id",
        "active_id",
        "active_name",
        "active_desc",
        "active_join_type",
        "active_status",
        "active_start_time",
        "active_end_time",
        "active_price",
        "active_discount_type",
        "active_filter",
        "active_course",
        "created",
        "updated",
    )
    if not all(_column_exists("active", name) for name in required_active_cols):
        return

    required_record_cols = (
        "id",
        "record_id",
        "active_id",
        "active_name",
        "user_id",
        "price",
        "order_id",
        "status",
        "created",
        "updated",
    )
    if not all(
        _column_exists("active_user_record", name) for name in required_record_cols
    ):
        return

    bind = op.get_bind()
    dialect = bind.dialect.name
    now_expr = "NOW()" if dialect == "mysql" else "CURRENT_TIMESTAMP"

    # Deduplicate by active_id (pick the latest row by id).
    op.execute(
        f"""
        INSERT INTO promo_campaigns (
            campaign_bid,
            shifu_bid,
            name,
            description,
            join_type,
            status,
            start_at,
            end_at,
            discount_type,
            value,
            channel,
            filter,
            deleted,
            created_at,
            created_user_bid,
            updated_at,
            updated_user_bid
        )
        SELECT
            a.active_id,
            a.active_course,
            a.active_name,
            a.active_desc,
            a.active_join_type,
            a.active_status,
            a.active_start_time,
            a.active_end_time,
            CASE
                WHEN a.active_discount_type IN (701, 702) THEN a.active_discount_type
                ELSE 701
            END,
            a.active_price,
            '',
            a.active_filter,
            0,
            COALESCE(a.created, {now_expr}),
            '',
            COALESCE(a.updated, {now_expr}),
            ''
        FROM active a
        INNER JOIN (
            SELECT active_id, MAX(id) AS max_id
            FROM active
            GROUP BY active_id
        ) latest ON latest.active_id = a.active_id AND latest.max_id = a.id
        WHERE NOT EXISTS (
            SELECT 1
            FROM promo_campaigns pc
            WHERE pc.campaign_bid = a.active_id
        )
        """
    )

    # Deduplicate per (order_id, active_id) (pick the latest row by id).
    op.execute(
        f"""
        INSERT INTO promo_campaign_applications (
            campaign_application_bid,
            campaign_bid,
            order_bid,
            user_bid,
            shifu_bid,
            campaign_name,
            discount_type,
            value,
            discount_amount,
            status,
            deleted,
            created_at,
            updated_at
        )
        SELECT
            r.record_id,
            r.active_id,
            r.order_id,
            r.user_id,
            COALESCE(a.active_course, ''),
            r.active_name,
            701,
            r.price,
            r.price,
            r.status,
            0,
            COALESCE(r.created, {now_expr}),
            COALESCE(r.updated, {now_expr})
        FROM active_user_record r
        INNER JOIN (
            SELECT order_id, active_id, MAX(id) AS max_id
            FROM active_user_record
            GROUP BY order_id, active_id
        ) latest ON latest.order_id = r.order_id AND latest.active_id = r.active_id AND latest.max_id = r.id
        LEFT JOIN active a ON a.active_id = r.active_id
        WHERE NOT EXISTS (
            SELECT 1
            FROM promo_campaign_applications pca
            WHERE pca.campaign_application_bid = r.record_id
        )
        """
    )


def downgrade():
    # Data migrations are not safely reversible without risking data loss.
    return
