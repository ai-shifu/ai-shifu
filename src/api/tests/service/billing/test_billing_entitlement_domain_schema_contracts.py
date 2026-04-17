from __future__ import annotations

from pathlib import Path

from flaskr.service.billing.models import BillingDomainBinding, BillingEntitlement

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_v11_models_define_entitlement_and_domain_tables() -> None:
    entitlement_table = BillingEntitlement.__table__
    domain_table = BillingDomainBinding.__table__

    assert BillingEntitlement.__tablename__ == "billing_entitlements"
    assert "entitlement_bid" in entitlement_table.c
    assert "max_concurrency" not in entitlement_table.c
    assert "effective_to" in entitlement_table.c

    assert BillingDomainBinding.__tablename__ == "billing_domain_bindings"
    assert "domain_binding_bid" in domain_table.c
    assert "host" in domain_table.c
    assert "verification_token" in domain_table.c
    assert "ssl_status" in domain_table.c


def test_billing_v11_migrations_create_then_drop_entitlement_concurrency() -> None:
    extension_source = (
        _API_ROOT / "migrations/versions/c225e8a6f3d2_add_billing_extension_phase.py"
    ).read_text(encoding="utf-8")
    cleanup_source = (
        _API_ROOT
        / "migrations/versions/4c2a9d8b7e6f_drop_billing_entitlement_max_concurrency.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "b114d7f5e2c1"' in extension_source
    assert 'op.create_table(\n        "billing_entitlements",' in extension_source
    assert '"max_concurrency",' in extension_source
    assert 'down_revision = "9a6b3c2d1e4f"' in cleanup_source
    assert 'batch_op.drop_column("max_concurrency")' in cleanup_source
