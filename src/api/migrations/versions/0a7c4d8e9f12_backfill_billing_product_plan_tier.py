"""backfill billing product plan tier metadata

Revision ID: 0a7c4d8e9f12
Revises: f4a6b8c2d9e1
Create Date: 2026-05-28 00:00:00.000000

"""

from __future__ import annotations

import json
from typing import Any

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0a7c4d8e9f12"
down_revision = "f4a6b8c2d9e1"
branch_labels = None
depends_on = None


BILLING_PRODUCT_TYPE_PLAN = 7111


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _normalize_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if value is None:
        return {}
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    raw_value = str(value or "").strip()
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def upgrade():
    if not _table_exists("bill_products"):
        return

    bind = op.get_bind()
    rows = (
        bind.execute(
            sa.text(
                """
                SELECT id, metadata, sort_order
                FROM bill_products
                WHERE deleted = 0
                  AND product_type = :product_type
                  AND COALESCE(sort_order, 0) > 0
                """
            ),
            {"product_type": BILLING_PRODUCT_TYPE_PLAN},
        )
        .mappings()
        .all()
    )
    for row in rows:
        metadata = _normalize_metadata(row.get("metadata"))
        if metadata.get("plan_tier") is not None:
            continue
        try:
            plan_tier = int(row.get("sort_order") or 0)
        except (TypeError, ValueError):
            continue
        if plan_tier <= 0:
            continue
        metadata["plan_tier"] = plan_tier
        bind.execute(
            sa.text(
                """
                UPDATE bill_products
                SET metadata = :metadata
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "metadata": json.dumps(metadata, ensure_ascii=False),
            },
        )


def downgrade():
    pass
