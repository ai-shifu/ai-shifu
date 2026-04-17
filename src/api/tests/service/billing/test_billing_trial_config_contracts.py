from __future__ import annotations

from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_trial_product_catalog_is_authoritative() -> None:
    source = (
        _API_ROOT / "migrations/versions/d2b9a5c4f8e1_productize_creator_trial_plan.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "c225e8a6f3d2"' in source
    assert '"product_code": "creator-plan-trial"' in source
    assert '"trial_valid_days": 15' in source
    assert '"public_trial_offer": True' in source
    assert "op.bulk_insert(product_table, [_TRIAL_PRODUCT])" in source
    assert "_LEGACY_TRIAL_CONFIG" not in source
    assert 'sa.table("sys_configs"' not in source
