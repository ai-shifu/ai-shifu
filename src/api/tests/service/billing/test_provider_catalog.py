"""Verify provider catalog behavior."""

from __future__ import annotations

import pytest
from flaskr.service.billing.consts import (
    BILLING_INTERVAL_MONTH,
    BILLING_INTERVAL_NONE,
    BILLING_INTERVAL_YEAR,
    BILLING_MODE_ONE_TIME,
    BILLING_MODE_RECURRING,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_GRANT,
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
from flaskr.service.common.stripe_client import build_stripe_request_options
from flaskr.service.config import config_overrides


class _StripeObject:
    def __init__(self: object, payload: object) -> None:
        self._payload = payload

    def to_dict(self: object):
        return dict(self._payload)


class _FakeStripeResource:
    def __init__(self: object, payload: object) -> None:
        self.payload = payload
        self.calls = []

    def retrieve(self: object, *args: object, **kwargs: object):
        self.calls.append({"args": args, "kwargs": kwargs})
        return _StripeObject(self.payload)


class _FakeStripe:
    def __init__(self: object) -> None:
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
                "metadata": {
                    "market": "global",
                    "plan_tier": "growth",
                    "product_type": "plan",
                },
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
                "recurring": {
                    "interval": "month",
                    "interval_count": 1,
                    "usage_type": "licensed",
                },
                "metadata": {
                    "product_code": "creator-global-growth-monthly",
                    "credit_amount": "1000",
                    "billing_interval": "month",
                },
            }
        )


class _FailingStripeResource:
    def retrieve(self: object, *args: object, **kwargs: object):
        _ = (args, kwargs)
        message = "secret sk_test_should_not_leak"
        raise RuntimeError(message)


class _FailingStripe:
    Account = _FailingStripeResource()
    Product = _FailingStripeResource()
    Price = _FailingStripeResource()


class _FakeStripeAdapter(StripeCatalogReadAdapter):
    def __init__(self: object, stripe: object) -> None:
        self.stripe = stripe

    def _client_options(self: object, app: object):
        _ = app
        return self.stripe, build_stripe_request_options()


def _plan_product(**overrides: object) -> BillingProduct:
    values = {
        "product_bid": "bill-product-growth-month",
        "product_code": "creator-global-growth-monthly",
        "product_type": BILLING_PRODUCT_TYPE_PLAN,
        "billing_mode": BILLING_MODE_RECURRING,
        "billing_interval": BILLING_INTERVAL_MONTH,
        "billing_interval_count": 1,
        "currency": "USD",
        "price_amount": 5900,
        "credit_amount": 1000,
        "status": BILLING_PRODUCT_STATUS_ACTIVE,
    }
    values.update(overrides)
    return BillingProduct(**values)


def _topup_product(**overrides: object) -> BillingProduct:
    values = {
        "product_bid": "bill-product-topup-1000",
        "product_code": "creator-global-topup-1000",
        "product_type": BILLING_PRODUCT_TYPE_TOPUP,
        "billing_mode": BILLING_MODE_ONE_TIME,
        "billing_interval": BILLING_INTERVAL_NONE,
        "billing_interval_count": 0,
        "currency": "USD",
        "price_amount": 1900,
        "credit_amount": 1000,
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
    unit_amount_missing: bool = False,
    product_id: str = "prod_growth",
    price_product_id: str = "prod_growth",
    price_id: str = "price_growth_month",
    account_id: str = "acct_test",
    recurring_usage_type: str = "licensed",
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
        else {
            "market": "global",
            "plan_tier": "growth",
            "product_type": "plan",
        },
    }
    fake.Price.payload = {
        "id": price_id,
        "product": price_product_id,
        "active": price_active,
        "livemode": livemode,
        "currency": currency,
        "unit_amount": None if unit_amount_missing else unit_amount,
        "type": price_type,
        "recurring": {
            "interval": recurring_interval,
            "interval_count": recurring_interval_count,
            "usage_type": recurring_usage_type,
        }
        if price_type == "recurring"
        else None,
        "metadata": price_metadata
        if price_metadata is not None
        else {
            "product_code": "creator-global-growth-monthly",
            "credit_amount": "1000",
            "billing_interval": "month",
        },
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


def test_stripe_catalog_adapter_retrieves_and_normalizes_sdk_objects(
    app: object,
) -> None:
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
    assert fake.Account.calls[0]["kwargs"]["stripe_version"] == "2024-06-20"
    assert fake.Product.calls[0]["kwargs"]["stripe_version"] == "2024-06-20"
    assert fake.Price.calls[0]["kwargs"]["stripe_version"] == "2024-06-20"
    assert fake.Product.calls[0]["args"] == ("prod_growth",)
    assert fake.Price.calls[0]["args"] == ("price_growth_month",)


def test_stripe_catalog_adapter_wraps_retrieve_errors_without_secret(
    app: object,
) -> None:
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
    assert exc_info.value.__cause__ is None
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
        product_metadata={"market": "global", "product_type": "topup"},
        price_metadata={
            "product_code": "creator-global-topup-1000",
            "credit_amount": "1000",
            "billing_interval": "one_time",
        },
    )

    result = _validate(product, snapshot)

    assert result.valid is True
    assert result.errors == []


@pytest.mark.parametrize(
    ("product_code", "credit_amount"),
    [
        ("creator-global-credits-250", 250),
        ("creator-global-credits-3000", 3000),
    ],
)
def test_topup_provider_price_mapping_accepts_credit_pack_metadata_contract(
    product_code: object,
    credit_amount: object,
) -> None:
    product = _topup_product(product_code=product_code, credit_amount=credit_amount)
    snapshot = _snapshot(
        price_type="one_time",
        recurring_interval="",
        recurring_interval_count=0,
        unit_amount=1900,
        product_metadata={"market": "global", "product_type": "topup"},
        price_metadata={
            "product_code": product_code,
            "credit_amount": str(credit_amount),
            "billing_interval": "one_time",
        },
    )

    result = _validate(product, snapshot)

    assert result.valid is True
    assert result.errors == []
    assert result.warnings == []


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
        ({"unit_amount_missing": True}, "provider_price_unit_amount_missing"),
        ({"price_type": "one_time"}, "plan_requires_recurring_price"),
        (
            {"recurring_usage_type": "metered"},
            "plan_requires_licensed_recurring_price",
        ),
        ({"recurring_interval": "year"}, "billing_interval_mismatch"),
        ({"recurring_interval_count": 12}, "billing_interval_count_mismatch"),
    ],
)
def test_plan_provider_price_mapping_rejects_strong_mismatches(
    snapshot_kwargs: object,
    expected_error: object,
) -> None:
    result = _validate(_plan_product(), _snapshot(**snapshot_kwargs))

    assert result.valid is False
    assert expected_error in {issue.code for issue in result.errors}


def test_provider_price_mapping_rejects_missing_unit_amount_even_for_zero_price() -> (
    None
):
    result = _validate(
        _plan_product(price_amount=0),
        _snapshot(unit_amount_missing=True),
    )

    assert result.valid is False
    assert "provider_price_unit_amount_missing" in {
        issue.code for issue in result.errors
    }


def test_provider_price_mapping_preserves_actual_zero_unit_amount() -> None:
    result = _validate(
        _plan_product(price_amount=0),
        _snapshot(unit_amount=0),
    )

    assert result.valid is True
    assert result.errors == []


def test_provider_price_mapping_rejects_unsupported_product_type() -> None:
    result = _validate(
        _plan_product(product_type=BILLING_PRODUCT_TYPE_GRANT),
        _snapshot(),
    )

    assert result.valid is False
    assert "unsupported_product_type" in {issue.code for issue in result.errors}


def test_topup_provider_price_mapping_rejects_recurring_price() -> None:
    result = _validate(
        _topup_product(price_amount=5900),
        _snapshot(price_type="recurring"),
    )

    assert result.valid is False
    assert "topup_requires_one_time_price" in {issue.code for issue in result.errors}


def test_topup_provider_price_mapping_rejects_local_recurring_interval() -> None:
    result = _validate(
        _topup_product(billing_interval=BILLING_INTERVAL_MONTH),
        _snapshot(price_type="one_time", unit_amount=1900),
    )

    assert result.valid is False
    assert "local_topup_billing_interval_invalid" in {
        issue.code for issue in result.errors
    }


def test_topup_provider_price_mapping_rejects_local_interval_count() -> None:
    result = _validate(
        _topup_product(billing_interval_count=1),
        _snapshot(price_type="one_time", unit_amount=1900),
    )

    assert result.valid is False
    assert "local_topup_billing_interval_count_invalid" in {
        issue.code for issue in result.errors
    }


def test_plan_provider_price_mapping_allows_shared_product_with_price_sku_metadata() -> (
    None
):
    product = _plan_product(
        product_bid="bill-product-growth-year",
        product_code="creator-global-growth-yearly",
        billing_interval=BILLING_INTERVAL_YEAR,
        price_amount=59000,
        credit_amount=12000,
    )
    snapshot = _snapshot(
        recurring_interval="year",
        unit_amount=59000,
        product_metadata={
            "market": "global",
            "plan_tier": "growth",
            "product_type": "plan",
        },
        price_metadata={
            "product_code": "creator-global-growth-yearly",
            "credit_amount": "12000",
            "billing_interval": "year",
        },
    )

    result = _validate(product, snapshot)

    assert result.valid is True
    assert result.errors == []
    assert result.warnings == []


def test_plan_metadata_tier_prefers_explicit_local_metadata() -> None:
    product = _plan_product(
        product_code="creator-global-growth-monthly",
        metadata_json={"plan_tier": "enterprise"},
    )
    snapshot = _snapshot(
        product_metadata={
            "market": "global",
            "plan_tier": "enterprise",
            "product_type": "plan",
        },
    )

    result = _validate(product, snapshot)

    assert result.valid is True
    assert result.errors == []
    assert result.warnings == []


def test_provider_price_mapping_reports_metadata_drift_as_warning_only() -> None:
    result = _validate(
        _plan_product(),
        _snapshot(
            product_metadata={
                "market": "cn",
                "plan_tier": "studio",
                "product_type": "topup",
            },
            price_metadata={
                "product_code": "wrong-product-code",
                "credit_amount": "999",
                "billing_interval": "year",
            },
        ),
    )

    assert result.valid is True
    assert result.errors == []
    assert {
        "product_metadata_market_mismatch",
        "product_metadata_plan_tier_mismatch",
        "product_metadata_product_type_mismatch",
        "price_metadata_product_code_mismatch",
        "price_metadata_credit_amount_mismatch",
        "price_metadata_billing_interval_mismatch",
    } == {issue.code for issue in result.warnings}


def test_provider_price_mapping_reports_missing_metadata_as_warning_only() -> None:
    result = _validate(
        _plan_product(),
        _snapshot(product_metadata={}, price_metadata={}),
    )

    assert result.valid is True
    assert result.errors == []
    assert {
        "product_metadata_market_missing",
        "product_metadata_plan_tier_missing",
        "product_metadata_product_type_missing",
        "price_metadata_product_code_missing",
        "price_metadata_credit_amount_missing",
        "price_metadata_billing_interval_missing",
    } == {issue.code for issue in result.warnings}
