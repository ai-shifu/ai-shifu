from __future__ import annotations

from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_product_catalog_canonicalization_migration_upserts_db_rows() -> None:
    source = (
        _API_ROOT
        / "migrations/versions/9a6b3c2d1e4f_canonicalize_billing_product_catalog.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "e5c6f7a8b9d0"' in source
    assert '"product_bid": "billing-product-plan-trial"' in source
    assert '"product_bid": "billing-product-plan-monthly"' in source
    assert '"product_bid": "billing-product-topup-xlarge"' in source
    assert '.where(_PRODUCT_TABLE.c.product_bid == payload["product_bid"])' in source
    assert "_upsert_products(_PRODUCT_ROWS)" in source
    assert "def downgrade():" in source
    assert "\n    pass\n" in source
