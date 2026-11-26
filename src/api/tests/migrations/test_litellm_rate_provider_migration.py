"""Verify LLM rates are copied to LiteLLM provider names."""

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
    / "a3c5e7f9b1d2_copy_llm_rates_to_litellm_names.py"
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
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("rate_bid", sa.String(36), nullable=False, unique=True),
        sa.Column("deleted", sa.Integer, nullable=False, default=0),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("usage_type", sa.Integer),
        sa.Column("provider", sa.String(32)),
        sa.Column("model", sa.String(100)),
        sa.Column("usage_scene", sa.Integer),
        sa.Column("billing_metric", sa.Integer),
        sa.Column("unit_size", sa.Integer),
        sa.Column("credits_per_unit", sa.Numeric(20, 10)),
        sa.Column("rounding_mode", sa.Integer),
        sa.Column("effective_from", sa.DateTime),
        sa.Column("effective_to", sa.DateTime, nullable=True),
        sa.Column("status", sa.Integer),
        sa.UniqueConstraint(
            "usage_type",
            "provider",
            "model",
            "usage_scene",
            "billing_metric",
            "effective_from",
        ),
    )


def _row(
    row_id: int, usage_type: int, provider: str, model: str, *, deleted: int = 0
) -> dict:
    return {
        "id": row_id,
        "rate_bid": f"rate-{row_id}",
        "deleted": deleted,
        "created_at": EFFECTIVE,
        "updated_at": EFFECTIVE,
        "usage_type": usage_type,
        "provider": provider,
        "model": model,
        "usage_scene": 1,
        "billing_metric": 1,
        "unit_size": 1000,
        "credits_per_unit": row_id,
        "rounding_mode": 1,
        "effective_from": EFFECTIVE,
        "effective_to": None,
        "status": 1,
    }


def test_upgrade_copies_llm_rows_and_downgrade_removes_the_copies(
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
        # Full legacy model ids move to the LiteLLM prefix too.
        _row(11, LLM, "qwen", "qwen/qwen-turbo"),
        _row(12, LLM, "*", "silicon/deepseek-ai/DeepSeek-V3"),
        # Deleted rows are not copied.
        _row(13, LLM, "qwen", "qwen-long", deleted=1),
        # An operator-created rate with an ordinary hex id survives downgrade.
        {**_row(14, LLM, "openai", "gpt-5"), "rate_bid": "a3c5" + "0" * 28},
    ]
    rate_columns = [
        column.name for column in rates.c if column.name not in {"id", "rate_bid"}
    ]

    def snapshot() -> dict[str, dict]:
        return {
            row["rate_bid"]: {column: row[column] for column in rate_columns}
            for row in connection.execute(sa.select(rates)).mappings()
        }

    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(rates.insert(), rows)
        original = snapshot()
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)

        migration.upgrade()
        migration.upgrade()  # A rerun finds nothing left to copy.
        upgraded = snapshot()

        migration.downgrade()
        downgraded = snapshot()

    engine.dispose()
    copies = {
        bid: values
        for bid, values in upgraded.items()
        if bid.startswith(migration.COPY_RATE_BID_PREFIX)
    }
    assert all(len(bid) == 36 for bid in copies)
    # Every earlier row stays as it was.
    assert {bid: upgraded[bid] for bid in original} == original

    by_id = {int(values["credits_per_unit"]): values for values in original.values()}

    def source(source_id: int) -> dict:
        return by_id[source_id]

    copied = {}
    for values in copies.values():
        source_id = int(values["credits_per_unit"])
        expected = {
            **source(source_id),
            "provider": values["provider"],
            "model": values["model"],
            "created_at": values["created_at"],
            "updated_at": values["updated_at"],
        }
        assert values == expected
        copied[source_id] = (values["provider"], values["model"])
    assert copied == {
        1: ("dashscope", "qwen-max"),
        2: ("bigmodel", "glm-4.6"),
        3: ("volcengine", "doubao"),
        4: ("qianfan", "ernie-4.5"),
        5: ("siliconflow", "Qwen/Qwen3-8B"),
        11: ("dashscope", "dashscope/qwen-turbo"),
        12: ("*", "siliconflow/deepseek-ai/DeepSeek-V3"),
    }
    # Downgrade removes only the copies, keeping row 10 that predates them.
    assert downgraded == original
