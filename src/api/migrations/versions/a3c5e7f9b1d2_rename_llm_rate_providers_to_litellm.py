"""rename LLM credit rate providers to LiteLLM provider names.

Revision ID: a3c5e7f9b1d2
Revises: d96fca5d4222
Create Date: 2026-11-20 12:00:00.000000

Model routing now uses LiteLLM's provider names, which are also the billing
identity. LLM rate rows keyed by the earlier AI-Shifu names are renamed so
they keep matching. Historical usage records keep the name they were written
with.

A row is left unchanged when the renamed identity already exists
(same usage type, model, scene, metric and effective time), because the
lookup unique constraint would reject it; the existing LiteLLM-named row
already wins for that identity. Rerunning finds nothing left to rename.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a3c5e7f9b1d2"
down_revision = "d96fca5d4222"
branch_labels = None
depends_on = None


BILL_USAGE_TYPE_LLM = 1101
PROVIDER_RENAMES = {
    "qwen": "dashscope",
    "glm": "bigmodel",
    "ark": "volcengine",
    "ernie_v2": "qianfan",
    "silicon": "siliconflow",
}


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _rename(renames: dict[str, str]) -> None:
    if not _table_exists("credit_usage_rates"):
        return
    bind = op.get_bind()
    for old, new in renames.items():
        rows = (
            bind.execute(
                sa.text(
                    """
                    SELECT id, model, usage_scene, billing_metric, effective_from
                    FROM credit_usage_rates
                    WHERE usage_type = :usage_type AND provider = :old
                    """
                ),
                {"usage_type": BILL_USAGE_TYPE_LLM, "old": old},
            )
            .mappings()
            .all()
        )
        for row in rows:
            conflict = bind.execute(
                sa.text(
                    """
                    SELECT 1 FROM credit_usage_rates
                    WHERE usage_type = :usage_type
                      AND provider = :new
                      AND model = :model
                      AND usage_scene = :usage_scene
                      AND billing_metric = :billing_metric
                      AND effective_from = :effective_from
                    LIMIT 1
                    """
                ),
                {
                    "usage_type": BILL_USAGE_TYPE_LLM,
                    "new": new,
                    "model": row["model"],
                    "usage_scene": row["usage_scene"],
                    "billing_metric": row["billing_metric"],
                    "effective_from": row["effective_from"],
                },
            ).first()
            if conflict is not None:
                continue
            bind.execute(
                sa.text("UPDATE credit_usage_rates SET provider = :new WHERE id = :id"),
                {"new": new, "id": row["id"]},
            )


def upgrade():
    _rename(PROVIDER_RENAMES)


def downgrade():
    _rename({new: old for old, new in PROVIDER_RENAMES.items()})
