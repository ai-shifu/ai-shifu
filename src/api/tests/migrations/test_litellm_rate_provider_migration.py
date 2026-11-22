"""Verify LLM rate providers are renamed to LiteLLM provider names."""

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa

API_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    API_ROOT
    / "migrations"
    / "versions"
    / "a3c5e7f9b1d2_rename_llm_rate_providers_to_litellm.py"
)
LLM = 1101
TTS = 1102
EFFECTIVE = datetime(2026, 1, 1)


def _load_migration_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "test_litellm_rate_provider_migration_module", MIGRATION_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rates_table(metadata: sa.MetaData) -> sa.Table:
    return sa.Table(
        "credit_usage_rates",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("usage_type", sa.Integer),
        sa.Column("provider", sa.String(32)),
        sa.Column("model", sa.String(64)),
        sa.Column("usage_scene", sa.Integer),
        sa.Column("billing_metric", sa.Integer),
        sa.Column("effective_from", sa.DateTime),
        sa.UniqueConstraint(
            "usage_type",
            "provider",
            "model",
            "usage_scene",
            "billing_metric",
            "effective_from",
        ),
    )


def _row(row_id: int, usage_type: int, provider: str, model: str) -> dict:
    return {
        "id": row_id,
        "usage_type": usage_type,
        "provider": provider,
        "model": model,
        "usage_scene": 1,
        "billing_metric": 1,
        "effective_from": EFFECTIVE,
    }


def test_upgrade_renames_llm_rows_and_downgrade_restores_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration_module()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    rates = _rates_table(metadata)
    rows = [
        _row(1, LLM, "qwen", "qwen-max"),
        _row(2, LLM, "glm", "glm-4.6"),
        _row(3, LLM, "ark", "doubao"),
        _row(4, LLM, "ernie_v2", "ernie-4.5"),
        _row(5, LLM, "silicon", "Qwen/Qwen3-8B"),
        _row(6, LLM, "openai", "gpt-4o"),
        _row(7, LLM, "*", "*"),
        # TTS provider names are a separate namespace.
        _row(8, TTS, "ark", "voice"),
        # A LiteLLM-named row for the same identity already wins.
        _row(9, LLM, "qwen", "qwen-plus"),
        _row(10, LLM, "dashscope", "qwen-plus"),
    ]

    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(rates.insert(), rows)
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)

        migration.upgrade()
        migration.upgrade()  # A rerun finds nothing left to rename.
        upgraded = dict(
            connection.execute(sa.select(rates.c.id, rates.c.provider)).all()
        )

        migration.downgrade()
        downgraded = dict(
            connection.execute(sa.select(rates.c.id, rates.c.provider)).all()
        )

    engine.dispose()
    assert upgraded == {
        1: "dashscope",
        2: "bigmodel",
        3: "volcengine",
        4: "qianfan",
        5: "siliconflow",
        6: "openai",
        7: "*",
        8: "ark",
        9: "qwen",
        10: "dashscope",
    }
    # Row 9 kept its name; row 10 was LiteLLM-named before the upgrade and
    # also blocks the downgrade of its identity.
    assert downgraded == {
        1: "qwen",
        2: "glm",
        3: "ark",
        4: "ernie_v2",
        5: "silicon",
        6: "openai",
        7: "*",
        8: "ark",
        9: "qwen",
        10: "dashscope",
    }
