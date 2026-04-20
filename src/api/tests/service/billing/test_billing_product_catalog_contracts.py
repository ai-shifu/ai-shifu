from __future__ import annotations

from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_product_catalog_uses_cli_upsert_instead_of_seed_migrations() -> None:
    migration_source = (
        _API_ROOT / "migrations/versions/b114d7f5e2c1_add_billing_core_phase.py"
    ).read_text(encoding="utf-8")
    cli_source = (_API_ROOT / "flaskr/service/billing/cli.py").read_text(
        encoding="utf-8"
    )

    assert "upsert-product" in cli_source
    assert "--product-bid" in cli_source
    assert "--credit-amount" in cli_source
    assert "--metadata-json" in cli_source
    assert "--entitlement-json" in cli_source
    assert "bill-product-plan-monthly" not in migration_source
    assert "bill-product-topup-xlarge" not in migration_source
    assert "op.bulk_insert(" not in migration_source
    assert not (
        _API_ROOT
        / "migrations/versions/9a6b3c2d1e4f_canonicalize_billing_product_catalog.py"
    ).exists()
