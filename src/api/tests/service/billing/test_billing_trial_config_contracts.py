from __future__ import annotations

from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_trial_config_migration_seeds_required_defaults() -> None:
    source = (
        _API_ROOT / "migrations/versions/c225e8a6f3d2_add_billing_extension_phase.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "b114d7f5e2c1"' in source
    assert '"key": "BILLING_NEW_CREATOR_TRIAL_CONFIG"' in source
    assert '"program_code": "new_creator_v1"' in source
    assert '"grant_trigger": "billing_overview"' in source
    assert "op.bulk_insert(config_table, [_NEW_CREATOR_TRIAL_CONFIG])" in source
