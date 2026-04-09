from __future__ import annotations

from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_sys_config_migration_seeds_required_keys() -> None:
    source = (
        _API_ROOT / "migrations/versions/b114d7f5e2c1_add_billing_core_phase.py"
    ).read_text(encoding="utf-8")

    assert '"key": "BILLING_ENABLED"' in source
    assert '"key": "BILLING_LOW_BALANCE_THRESHOLD"' in source
    assert '"key": "BILLING_RENEWAL_TASK_CONFIG"' in source
    assert '"key": "BILLING_RATE_VERSION"' in source
    assert "op.bulk_insert(config_table, list(_BILLING_SYS_CONFIG_SEEDS))" in source
