"""copy LLM credit rates to LiteLLM provider names.

Revision ID: a3c5e7f9b1d2
Revises: d96fca5d4222
Create Date: 2026-11-20 12:00:00.000000

Model routing now uses LiteLLM's provider names, which are also the billing
identity. Each active LLM rate row keyed by an earlier AI-Shifu provider name
or model id prefix (``qwen/qwen-max``) is copied to its LiteLLM identity. The
earlier rows stay, because processes still running the previous release only
look up the earlier names and would settle their usage at zero credits
otherwise; this keeps the migration additive, safe during rolling upgrades
and on databases shared with environments that have not upgraded. A later
migration can drop the earlier rows once no environment runs that release.

A row is not copied when its LiteLLM identity already exists (same usage
type, model, scene, metric and effective time), because the lookup unique
constraint would reject it; the existing LiteLLM-named row already wins for
that identity. Rerunning finds nothing left to copy.

Copies get a ``rate_bid`` starting with ``COPY_RATE_BID_PREFIX`` (36
characters in all, the column width). Other rate bids are 32-character hex
ids or ``credit-rate-`` seed names, neither of which can start with it, so
downgrade deletes exactly the copies and keeps every other row.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a3c5e7f9b1d2"
down_revision = "d96fca5d4222"
branch_labels = None
depends_on = None

COPY_RATE_BID_PREFIX = "litellm-copy-"
RATE_BID_LENGTH = 36


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


def _renamed(row, providers: dict[str, str], prefixes: dict[str, str]):
    provider = providers.get(row["provider"], row["provider"])
    model = _renamed_model(row["model"], prefixes)
    if (provider, model) == (row["provider"], row["model"]):
        return None
    return provider, model


def _llm_rows(bind, columns: str):
    return (
        bind.execute(
            sa.text(
                f"SELECT {columns} FROM credit_usage_rates "
                "WHERE usage_type = :usage_type AND deleted = 0"
            ),
            {"usage_type": BILL_USAGE_TYPE_LLM},
        )
        .mappings()
        .all()
    )


def _identity_exists(bind, row, provider: str, model: str) -> bool:
    return (
        bind.execute(
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
        is not None
    )


_COPIED_COLUMNS = (
    "usage_type",
    "usage_scene",
    "billing_metric",
    "unit_size",
    "credits_per_unit",
    "rounding_mode",
    "effective_from",
    "effective_to",
    "status",
)


def upgrade():
    bind = op.get_bind()
    now = datetime.utcnow().replace(microsecond=0)
    rows = _llm_rows(bind, ", ".join(("provider", "model", *_COPIED_COLUMNS)))
    for row in rows:
        renamed = _renamed(row, PROVIDER_RENAMES, MODEL_PREFIX_RENAMES)
        if renamed is None or _identity_exists(bind, row, *renamed):
            continue
        provider, model = renamed
        values = {column: row[column] for column in _COPIED_COLUMNS}
        values.update(
            rate_bid=(COPY_RATE_BID_PREFIX + uuid.uuid4().hex)[:RATE_BID_LENGTH],
            provider=provider,
            model=model,
            deleted=0,
            created_at=now,
            updated_at=now,
        )
        columns = ", ".join(values)
        placeholders = ", ".join(f":{column}" for column in values)
        bind.execute(
            sa.text(
                f"INSERT INTO credit_usage_rates ({columns}) VALUES ({placeholders})"
            ),
            values,
        )


def downgrade():
    op.get_bind().execute(
        sa.text(
            "DELETE FROM credit_usage_rates "
            "WHERE usage_type = :usage_type AND rate_bid LIKE :prefix"
        ),
        {"usage_type": BILL_USAGE_TYPE_LLM, "prefix": COPY_RATE_BID_PREFIX + "%"},
    )
