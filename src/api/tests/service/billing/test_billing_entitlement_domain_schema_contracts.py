from __future__ import annotations

from pathlib import Path

from flaskr.service.billing.models import BillingDomainBinding, BillingEntitlement

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_v11_models_define_entitlement_and_domain_tables() -> None:
    entitlement_table = BillingEntitlement.__table__
    domain_table = BillingDomainBinding.__table__

    assert BillingEntitlement.__tablename__ == "bill_entitlements"
    assert "entitlement_bid" in entitlement_table.c
    assert "max_concurrency" not in entitlement_table.c
    assert "effective_to" in entitlement_table.c

    assert BillingDomainBinding.__tablename__ == "bill_domain_bindings"
    assert "domain_binding_bid" in domain_table.c
    assert "host" in domain_table.c
    assert "verification_token" in domain_table.c
    assert "ssl_status" in domain_table.c


def test_billing_single_migration_creates_final_entitlement_schema() -> None:
    source = (
        _API_ROOT / "migrations/versions/b114d7f5e2c1_add_billing_core_phase.py"
    ).read_text(encoding="utf-8")

    assert 'op.create_table(\n        "bill_entitlements",' in source
    assert 'op.create_table(\n        "bill_domain_bindings",' in source
    assert '"max_concurrency"' not in source
    assert "ix_bill_entitlements_source_type_source_bid" in source
    assert not (
        _API_ROOT
        / "migrations/versions/4c2a9d8b7e6f_drop_billing_entitlement_max_concurrency.py"
    ).exists()
