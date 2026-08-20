from __future__ import annotations

import pytest
from flaskr.service.billing.consts import (
    BILLING_INTERVAL_MONTH,
    BILLING_INTERVAL_NONE,
    BILLING_MODE_ONE_TIME,
    BILLING_MODE_RECURRING,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
)
from flaskr.service.billing.models import BillingProduct
from flaskr.service.billing.provider_catalog import (
    ProviderCatalogReadError,
    ProviderCatalogSnapshot,
    StripeCatalogReadAdapter,
    validate_provider_price_mapping,
)
from flaskr.service.config import config_overrides


class _StripeObject:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


class _FakeStripeResource:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def retrieve(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        return _StripeObject(self.payload)


class _FakeStripe:
    def __init__(self):
        self.Account = _FakeStripeResource(
            {
                "id": "acct_test",
            }
        )
        self.Product = _FakeStripeResource(
            {
                "id": "prod_growth",
                "active": True,
                "livemode": False,
                "metadata": {"product_code": "creator-global-growth-monthly"},
            }
        )
        self.Price = _FakeStripeResource(
            {
                "id": "price_growth_month",
                "product": "prod_growth",
                "active": True,
                "livemode": False,
                "currency": "usd",
                "unit_amount": 5900,
                "type": "recurring",
                "recurring": {"interval": "month", "interval_count": 1},
                "metadata": {"product_bid": "bill-product-growth-month"},
            }
        )


class _FailingStripeResource:
    def retrieve(self, *args, **kwargs):
        raise RuntimeError("secret sk_test_should_not_leak")


class _FailingStripe:
    Account = _FailingStripeResource()
    Product = _FailingStripeResource()
    Price = _FailingStripeResource()


class _FakeStripeAdapter(StripeCatalogReadAdapter):
    def __init__(self, stripe):
        self.stripe = stripe

    def _ensure_client(self, app):
        return self.stripe


def _plan_product(**overrides) -> BillingProduct:
    values = {
        "product_bid": "bill-product-growth-month",
        "product_code": "creator-global-growth-monthly",
        "product_type": BILLING_PRODUCT_TYPE_PLAN,
        "billing_mode": BILLING_MODE_RECURRING,
        "billing_interval": BILLING_INTERVAL_MONTH,
        "billing_interval_count": 1,
        "currency": "USD",
        "price_amount": 5900,
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
    }
    values.update(overrides)
    return BillingProduct(**values)


def _topup_product(**overrides) -> BillingProduct:
    values = {
        "product_bid": "bill-product-topup-1000",
        "product_code": "creator-global-topup-1000",
        "product_type": BILLING_PRODUCT_TYPE_TOPUP,
        "billing_mode": BILLING_MODE_ONE_TIME,
        "billing_interval": BILLING_INTERVAL_NONE,
        "billing_interval_count": 0,
        "currency": "USD",
        "price_amount": 1900,
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
    }
    values.update(overrides)
    return BillingProduct(**values)


def _snapshot(
    *,
    price_type: str = "recurring",
    recurring_interval: str = "month",
    recurring_interval_count: int = 1,
    unit_amount: int = 5900,
    currency: str = "usd",
    product_active: bool = True,
    price_active: bool = True,
    livemode: bool = False,
    product_id: str = "prod_growth",
    price_product_id: str = "prod_growth",
    price_id: str = "price_growth_month",
    account_id: str = "acct_test",
    product_metadata: dict | None = None,
    price_metadata: dict | None = None,
) -> ProviderCatalogSnapshot:
    fake = _FakeStripe()
    fake.Account.payload = {"id": account_id}
    fake.Product.payload = {
        "id": product_id,
        "active": product_active,
        "livemode": livemode,
        "metadata": product_metadata
        if product_metadata is not None
        else {"product_code": "creator-global-growth-monthly"},
    }
    fake.Price.payload = {
        "id": price_id,
        "product": price_product_id,
        "active": price_active,
        "livemode": livemode,
        "currency": currency,
        "unit_amount": unit_amount,
        "type": price_type,
        "recurring": {
            "interval": recurring_interval,
            "interval_count": recurring_interval_count,
        }
        if price_type == "recurring"
        else None,
        "metadata": price_metadata
        if price_metadata is not None
        else {"product_bid": "bill-product-growth-month"},
    }
    with config_overrides({"STRIPE_SECRET_KEY": "sk_test_secret"}):
        return _FakeStripeAdapter(fake).retrieve_mapping_snapshot(
            None,
            provider_product_id=product_id,
            provider_price_id=price_id,
        )


def _validate(product: BillingProduct, snapshot: ProviderCatalogSnapshot):
    return validate_provider_price_mapping(
        product,
        snapshot,
        expected_provider_account_id="acct_test",
        expected_livemode=False,
        expected_provider_product_id="prod_growth",
        expected_provider_price_id="price_growth_month",
    )


def test_stripe_catalog_adapter_retrieves_and_normalizes_sdk_objects(app) -> None:
    fake = _FakeStripe()
    with config_overrides(
        {
            "STRIPE_SECRET_KEY": "sk_test_secret",
            "STRIPE_API_VERSION": "2024-06-20",
        }
    ):
        snapshot = _FakeStripeAdapter(fake).retrieve_mapping_snapshot(
            app,
            provider_product_id="prod_growth",
            provider_price_id="price_growth_month",
        )

    assert snapshot.account.account_id == "acct_test"
    assert snapshot.product.product_id == "prod_growth"
    assert snapshot.product.active is True
    assert snapshot.price.price_id == "price_growth_month"
    assert snapshot.price.product_id == "prod_growth"
    assert snapshot.price.price_type == "recurring"
    assert snapshot.price.recurring_interval == "month"
    assert fake.Account.calls[0]["kwargs"]["api_key"] == "sk_test_secret"
    assert fake.Product.calls[0]["args"] == ("prod_growth",)
    assert fake.Price.calls[0]["args"] == ("price_growth_month",)


def test_stripe_catalog_adapter_wraps_retrieve_errors_without_secret(app) -> None:
    with (
        config_overrides({"STRIPE_SECRET_KEY": "sk_test_secret"}),
        pytest.raises(ProviderCatalogReadError) as exc_info,
    ):
        _FakeStripeAdapter(_FailingStripe()).retrieve_mapping_snapshot(
            app,
            provider_product_id="prod_growth",
            provider_price_id="price_growth_month",
        )

    assert exc_info.value.code == "stripe_catalog_retrieve_failed"
    assert "sk_test_should_not_leak" not in str(exc_info.value)


def test_plan_provider_price_mapping_accepts_matching_recurring_price() -> None:
    result = _validate(_plan_product(), _snapshot())

    assert result.valid is True
    assert result.errors == []


def test_topup_provider_price_mapping_accepts_matching_one_time_price() -> None:
    product = _topup_product()
    snapshot = _snapshot(
        price_type="one_time",
        recurring_interval="",
        recurring_interval_count=0,
        unit_amount=1900,
        product_id="prod_growth",
        price_product_id="prod_growth",
        price_id="price_growth_month",
        product_metadata={"product_code": "creator-global-topup-1000"},
        price_metadata={"product_bid": "bill-product-topup-1000"},
    )

    result = _validate(product, snapshot)

    assert result.valid is True
    assert result.errors == []


@pytest.mark.parametrize(
    ("snapshot_kwargs", "expected_error"),
    [
        ({"account_id": "acct_live"}, "provider_account_mismatch"),
        ({"livemode": True}, "product_livemode_mismatch"),
        ({"product_id": "prod_other"}, "provider_product_mismatch"),
        ({"price_product_id": "prod_other"}, "price_product_mismatch"),
        ({"price_id": "price_other"}, "provider_price_mismatch"),
        ({"product_active": False}, "provider_product_inactive"),
        ({"price_active": False}, "provider_price_inactive"),
        ({"currency": "eur"}, "currency_mismatch"),
        ({"unit_amount": 6900}, "unit_amount_mismatch"),
        ({"price_type": "one_time"}, "plan_requires_recurring_price"),
        ({"recurring_interval": "year"}, "billing_interval_mismatch"),
        ({"recurring_interval_count": 12}, "billing_interval_count_mismatch"),
    ],
)
def test_plan_provider_price_mapping_rejects_strong_mismatches(
    snapshot_kwargs,
    expected_error,
) -> None:
    result = _validate(_plan_product(), _snapshot(**snapshot_kwargs))

    assert result.valid is False
    assert expected_error in {issue.code for issue in result.errors}


def test_topup_provider_price_mapping_rejects_recurring_price() -> None:
    result = _validate(
        _topup_product(price_amount=5900),
        _snapshot(price_type="recurring"),
    )

    assert result.valid is False
    assert "topup_requires_one_time_price" in {issue.code for issue in result.errors}


def test_provider_price_mapping_reports_metadata_drift_as_warning_only() -> None:
    result = _validate(
        _plan_product(),
        _snapshot(
            product_metadata={"product_code": "wrong-product-code"},
            price_metadata={"product_bid": "wrong-product-bid"},
        ),
    )

    assert result.valid is True
    assert result.errors == []
    assert {
        "product_metadata_product_code_mismatch",
        "price_metadata_product_bid_mismatch",
    } == {issue.code for issue in result.warnings}
