"""rename LLM credit rate providers to LiteLLM provider names.

Revision ID: a3c5e7f9b1d2
Revises: d96fca5d4222
Create Date: 2026-11-20 12:00:00.000000

Model routing now uses LiteLLM's provider names, which are also the billing
identity. LLM rate rows keyed by the earlier AI-Shifu provider names or
model id prefixes (``qwen/qwen-max``) are renamed so they keep matching.
Historical usage records keep the names they were written with.

A row is left unchanged when the renamed identity already exists
(same usage type, model, scene, metric and effective time), because the
lookup unique constraint would reject it; the existing LiteLLM-named row
already wins for that identity. Rerunning finds nothing left to rename.

Downgrade is best effort: it renames every LiteLLM-named LLM row back, since
the earlier code only billed under the earlier names.
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
# Full model ids may carry the earlier AI-Shifu prefix; LiteLLM ids use the
# provider name instead.
MODEL_PREFIX_RENAMES = {
    "qwen/": "dashscope/",
    "glm/": "bigmodel/",
    "ark/": "volcengine/",
    "ernie/": "qianfan/",
    "silicon/": "siliconflow/",
}


def _renamed_model(model: str, prefixes: dict[str, str]) -> str:
    for old, new in prefixes.items():
        if model.startswith(old) and len(model) > len(old):
            return new + model[len(old) :]
    return model


def _rename(providers: dict[str, str], prefixes: dict[str, str]) -> None:
    bind = op.get_bind()
    rows = (
        bind.execute(
            sa.text(
                """
                SELECT id, provider, model, usage_scene, billing_metric,
                       effective_from
                FROM credit_usage_rates
                WHERE usage_type = :usage_type
                """
            ),
            {"usage_type": BILL_USAGE_TYPE_LLM},
        )
        .mappings()
        .all()
    )
    for row in rows:
        provider = providers.get(row["provider"], row["provider"])
        model = _renamed_model(row["model"], prefixes)
        if (provider, model) == (row["provider"], row["model"]):
            continue
        conflict = bind.execute(
            sa.text(
                """
                SELECT 1 FROM credit_usage_rates
                WHERE usage_type = :usage_type
                  AND provider = :provider
                  AND model = :model
                  AND usage_scene = :usage_scene
                  AND billing_metric = :billing_metric
                  AND effective_from = :effective_from
                LIMIT 1
                """
            ),
            {
                "usage_type": BILL_USAGE_TYPE_LLM,
                "provider": provider,
                "model": model,
                "usage_scene": row["usage_scene"],
                "billing_metric": row["billing_metric"],
                "effective_from": row["effective_from"],
            },
        ).first()
        if conflict is not None:
            continue
        bind.execute(
            sa.text(
                "UPDATE credit_usage_rates SET provider = :provider, model = :model "
                "WHERE id = :id"
            ),
            {"provider": provider, "model": model, "id": row["id"]},
        )


def _inverted(mapping: dict[str, str]) -> dict[str, str]:
    return {new: old for old, new in mapping.items()}


def upgrade():
    _rename(PROVIDER_RENAMES, MODEL_PREFIX_RENAMES)


def downgrade():
    _rename(_inverted(PROVIDER_RENAMES), _inverted(MODEL_PREFIX_RENAMES))
