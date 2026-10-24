"""Verify provider catalog health against real mappings and SDK response shapes."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import provider_catalog as catalog
from flaskr.service.billing import provider_catalog_health as health
from flaskr.service.billing.consts import (
    BILLING_INTERVAL_MONTH,
    BILLING_MODE_RECURRING,
    BILLING_PROVIDER_CATALOG_HEALTH_ACCOUNT_MISMATCH,
    BILLING_PROVIDER_CATALOG_HEALTH_MODE_MISMATCH,
    BILLING_PROVIDER_CATALOG_HEALTH_OK,
    BILLING_PROVIDER_CATALOG_HEALTH_UNLINKED,
    BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
    BILLING_PROVIDER_PRICE_STATUS_INVALID,
)
from flaskr.service.billing.models import (
    BillingProductProviderPrice,
    BillingProviderCatalogSnapshot,
)

from tests.service.billing.test_billing_tasks import (
    billing_task_integration_app as catalog_app,
)
from tests.service.billing.test_provider_catalog import _plan_product

if TYPE_CHECKING:
    from flask import Flask

__all__ = ["catalog_app"]


def _mapping(**changes: object) -> BillingProductProviderPrice:
    row = BillingProductProviderPrice(
        **{
            "provider_price_bid": uuid4().hex,
            "product_bid": "local-plan",
            "provider": "stripe",
            "provider_account_id": "acct_owner",
            "livemode": 0,
            "provider_product_id": "prod_plan",
            "provider_price_id": "price_plan",
            "currency": "USD",
            "unit_amount": 5900,
            "billing_mode": BILLING_MODE_RECURRING,
            "billing_interval": BILLING_INTERVAL_MONTH,
            "billing_interval_count": 1,
            "status": BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
            **changes,
        }
    )
    db.session.add(row)
    return row


def _snapshot(kind: str, **changes: object) -> BillingProviderCatalogSnapshot:
    row = BillingProviderCatalogSnapshot(
        **{
            "catalog_snapshot_bid": uuid4().hex,
            "provider": "stripe",
            "provider_account_id": "acct_owner",
            "object_type": kind,
            "object_id": "price_plan" if kind == "price" else "prod_plan",
            "livemode": 0,
            "active": 1,
            "metadata_json": {},
            **changes,
        }
    )
    db.session.add(row)
    return row


def _price(**changes: object) -> catalog.ProviderPriceSnapshot:
    return catalog.ProviderPriceSnapshot(
        **{
            "provider": "stripe",
            "price_id": "price_plan",
            "product_id": "prod_plan",
            "active": True,
            "livemode": False,
            "currency": "usd",
            "unit_amount": 5900,
            "price_type": "recurring",
            "recurring_interval": "month",
            "recurring_interval_count": 1,
            "recurring_usage_type": "licensed",
            **changes,
        }
    )


@pytest.mark.parametrize(
    ("changes", "issue"),
    [
        ({"active": False}, "provider_price_inactive"),
        ({"product_id": "other"}, "price_product_mismatch"),
        ({"unit_amount": 5901}, "unit_amount_mismatch"),
        ({"currency": "cny"}, "currency_mismatch"),
        ({"price_type": "one_time"}, "billing_mode_mismatch"),
        ({"recurring_interval": "year"}, "billing_interval_mismatch"),
        ({"recurring_interval_count": 2}, "billing_interval_count_mismatch"),
    ],
)
def test_price_drift_invalidates_only_active_mappings_in_its_scope(
    catalog_app: Flask,
    changes: dict,
    issue: str,
) -> None:
    del catalog_app
    mapping = _mapping()
    other = _mapping(provider_account_id="acct_other")
    row = _snapshot("price")
    db.session.commit()
    with unit_of_work():
        health.apply_price_health(row, _price(**changes))
    db.session.expire_all()
    assert row.pending_issue_code == issue
    assert row.linked_product_bid == mapping.product_bid
    assert mapping.status == BILLING_PROVIDER_PRICE_STATUS_INVALID
    assert json.loads(mapping.validation_error) == [{"code": issue}]
    assert other.status == BILLING_PROVIDER_PRICE_STATUS_ACTIVE


@pytest.mark.parametrize("kind", ["product", "price"])
@pytest.mark.parametrize("mismatch", ["account", "mode"])
def test_cross_scope_objects_are_flagged_without_invalidating_foreign_mapping(
    catalog_app: Flask,
    kind: str,
    mismatch: str,
) -> None:
    del catalog_app
    mapping = _mapping()
    row = _snapshot(
        kind,
        **(
            {"provider_account_id": "acct_other"}
            if mismatch == "account"
            else {"livemode": 1}
        ),
    )
    db.session.commit()
    with unit_of_work():
        if kind == "product":
            health.apply_product_health(row)
        else:
            health.apply_price_health(row, _price())
    db.session.expire_all()
    assert row.health_status == (
        BILLING_PROVIDER_CATALOG_HEALTH_ACCOUNT_MISMATCH
        if mismatch == "account"
        else BILLING_PROVIDER_CATALOG_HEALTH_MODE_MISMATCH
    )
    assert row.linked_product_bid == mapping.product_bid
    assert mapping.status == BILLING_PROVIDER_PRICE_STATUS_ACTIVE


@pytest.mark.parametrize("kind", ["product", "price"])
@pytest.mark.parametrize("suggestion", ["matching", "missing", "none"])
def test_unlinked_catalog_suggests_only_existing_local_product(
    catalog_app: Flask,
    kind: str,
    suggestion: str,
) -> None:
    del catalog_app
    product = _plan_product(product_bid="local-plan", product_code="local-plan-code")
    db.session.add(product)
    row = _snapshot(
        kind,
        metadata_json={}
        if suggestion == "none"
        else {
            "product_code": product.product_code
            if suggestion == "matching"
            else "absent"
        },
    )
    db.session.commit()
    with unit_of_work():
        if kind == "product":
            health.apply_product_health(row)
        else:
            health.apply_price_health(row, _price())
    db.session.expire_all()
    assert row.health_status == BILLING_PROVIDER_CATALOG_HEALTH_UNLINKED
    assert row.linked_product_bid == (
        product.product_bid if suggestion == "matching" else ""
    )


@pytest.mark.parametrize("active", [False, True])
def test_product_health_controls_mapped_product_availability(
    catalog_app: Flask, active: bool
) -> None:
    del catalog_app
    mapping = _mapping()
    row = _snapshot("product", active=int(active))
    db.session.commit()
    with unit_of_work():
        health.apply_product_health(row)
    db.session.expire_all()
    assert mapping.status == (
        BILLING_PROVIDER_PRICE_STATUS_ACTIVE
        if active
        else BILLING_PROVIDER_PRICE_STATUS_INVALID
    )
    assert row.pending_issue_code == ("" if active else "provider_product_inactive")


def test_healthy_price_clears_previous_issue_without_changing_mapping(
    catalog_app: Flask,
) -> None:
    del catalog_app
    mapping = _mapping()
    row = _snapshot("price", pending_issue_code="old-error")
    db.session.commit()
    with unit_of_work():
        health.apply_price_health(row, _price())
    db.session.expire_all()
    assert row.health_status == BILLING_PROVIDER_CATALOG_HEALTH_OK
    assert row.pending_issue_code == ""
    assert mapping.status == BILLING_PROVIDER_PRICE_STATUS_ACTIVE


@pytest.fixture
def stripe_reader(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    stripe = SimpleNamespace(Account=Mock(), Product=Mock(), Price=Mock())
    options = {"api_key": "test-only-key", "stripe_account": "acct_owner"}
    monkeypatch.setattr(
        catalog, "get_stripe_client_options", lambda _: (stripe, options)
    )
    return SimpleNamespace(
        adapter=catalog.StripeCatalogReadAdapter(), stripe=stripe, options=options
    )


def test_account_read_preserves_optional_mode_and_uses_scoped_credentials(
    stripe_reader: SimpleNamespace,
) -> None:
    state = stripe_reader
    state.stripe.Account.retrieve.return_value = SimpleNamespace(
        to_dict_recursive=lambda: {"id": " acct_owner ", "livemode": True}
    )
    snapshot = state.adapter.retrieve_account_snapshot(object())
    assert snapshot.account_id == "acct_owner"
    assert snapshot.livemode is True
    state.stripe.Account.retrieve.assert_called_once_with(**state.options)


@pytest.mark.parametrize(
    ("method", "resource"),
    [
        ("retrieve_account_snapshot", "Account"),
        ("list_product_snapshots", "Product"),
        ("list_price_snapshots", "Price"),
    ],
)
@pytest.mark.parametrize("structured", [False, True])
def test_catalog_reads_redact_provider_errors(
    stripe_reader: SimpleNamespace,
    method: str,
    resource: str,
    structured: bool,
) -> None:
    state = stripe_reader
    error = RuntimeError("secret private-request body")
    if structured:
        error.http_status = 403
        error.code = "permission_denied"
    api_method = "retrieve" if resource == "Account" else "list"
    getattr(getattr(state.stripe, resource), api_method).side_effect = error
    with pytest.raises(catalog.ProviderCatalogReadError) as caught:
        getattr(state.adapter, method)(object())
    assert caught.value.code == "stripe_catalog_retrieve_failed"
    assert "private-request" not in str(caught.value)
    assert "secret" not in str(caught.value)
    assert (
        "403 permission_denied" in str(caught.value)
        if structured
        else "RuntimeError" in str(caught.value)
    )


@pytest.mark.parametrize("kind", ["Product", "Price"])
@pytest.mark.parametrize("shape", ["paging", "dict", "malformed"])
def test_catalog_lists_normalize_sdk_and_dictionary_pages(
    stripe_reader: SimpleNamespace,
    kind: str,
    shape: str,
) -> None:
    state = stripe_reader
    payload = {
        "id": "object-1",
        "active": True,
        "livemode": False,
        "metadata": {" plan_tier ": "growth", "": "ignore"},
    }
    if kind == "Price":
        payload.update(
            product=SimpleNamespace(to_dict=lambda: {"id": "prod_plan"}),
            currency="USD",
            type="one_time",
            unit_amount=100,
        )
    wrapped = SimpleNamespace(to_dict=lambda: payload)
    response = (
        SimpleNamespace(auto_paging_iter=lambda: iter([wrapped]))
        if shape == "paging"
        else {"data": [payload]}
        if shape == "dict"
        else {"data": "invalid"}
    )
    getattr(state.stripe, kind).list.return_value = response
    method = (
        state.adapter.list_product_snapshots
        if kind == "Product"
        else state.adapter.list_price_snapshots
    )
    rows = method(object())
    assert len(rows) == (0 if shape == "malformed" else 1)
    if rows:
        assert rows[0].metadata == {"plan_tier": "growth"}
        assert rows[0].active is True
        if kind == "Price":
            assert rows[0].product_id == "prod_plan"
            assert rows[0].unit_amount == 100
    getattr(state.stripe, kind).list.assert_called_once_with(limit=100, **state.options)


@pytest.mark.parametrize(("product", "price"), [("", "price"), ("prod", " ")])
def test_missing_catalog_reference_never_contacts_stripe(
    stripe_reader: SimpleNamespace, product: str, price: str
) -> None:
    state = stripe_reader
    with pytest.raises(
        catalog.ProviderCatalogReadError, match="identifiers are required"
    ):
        state.adapter.retrieve_mapping_snapshot(
            object(), provider_product_id=product, provider_price_id=price
        )
    state.stripe.Account.retrieve.assert_not_called()
    state.stripe.Product.retrieve.assert_not_called()
    state.stripe.Price.retrieve.assert_not_called()
