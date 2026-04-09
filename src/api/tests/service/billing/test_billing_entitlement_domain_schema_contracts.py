from __future__ import annotations

from pathlib import Path

from flaskr.service.billing.models import BillingDomainBinding, BillingEntitlement

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_v11_models_define_entitlement_and_domain_tables() -> None:
    entitlement_table = BillingEntitlement.__table__
    domain_table = BillingDomainBinding.__table__

    assert BillingEntitlement.__tablename__ == "billing_entitlements"
    assert "entitlement_bid" in entitlement_table.c
    assert "max_concurrency" in entitlement_table.c
    assert "effective_to" in entitlement_table.c

    assert BillingDomainBinding.__tablename__ == "billing_domain_bindings"
    assert "domain_binding_bid" in domain_table.c
    assert "host" in domain_table.c
    assert "verification_token" in domain_table.c
    assert "ssl_status" in domain_table.c


def test_billing_v11_migration_creates_entitlement_and_domain_tables() -> None:
    source = (
        _API_ROOT / "migrations/versions/c225e8a6f3d2_add_billing_extension_phase.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "b114d7f5e2c1"' in source
    assert 'op.create_table(\n        "billing_entitlements",' in source
    assert 'op.create_table(\n        "billing_domain_bindings",' in source
    assert "ix_billing_entitlements_creator_effective_to" in source
    assert "ix_billing_entitlements_source_type_source_bid" in source
    assert "ix_billing_domain_bindings_creator_status" in source
    assert "uq_billing_domain_bindings_host" in source
