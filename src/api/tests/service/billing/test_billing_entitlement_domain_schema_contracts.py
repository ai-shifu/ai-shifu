"""Protect billing entitlement domain schema compatibility."""

from __future__ import annotations

from flaskr.service.billing.models import BillingDomainBinding, BillingEntitlement


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
