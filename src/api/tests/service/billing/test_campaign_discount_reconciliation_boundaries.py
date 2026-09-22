"""Keep persisted campaign coupons safe across invalid provider responses."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.service.billing import campaign_provider_discounts as discounts
from flaskr.service.billing.consts import (
    BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_FAILED,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_PROVIDER_INVALID,
)
from flaskr.service.billing.models import (
    BillingCampaignProduct,
    BillingCampaignProviderDiscount,
    BillingProduct,
    BillingProductProviderPrice,
)
from flaskr.service.billing.provider_price_mappings import ProviderPriceMappingError
from flaskr.service.common.models import AppError

from tests.service.billing.test_billing_tasks import (
    billing_task_integration_app as discount_app,
)
from tests.service.billing.test_campaign_provider_discounts import (
    _FakeCampaignDiscountProvider,
    _patch_scope,
    _seed_discount_campaign,
)

if TYPE_CHECKING:
    from flask import Flask

__all__ = ["discount_app"]


@pytest.fixture
def published(
    discount_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> tuple[_FakeCampaignDiscountProvider, str]:
    _patch_scope(monkeypatch)
    _seed_discount_campaign()
    provider = _FakeCampaignDiscountProvider()
    result = discounts.publish_admin_campaign_provider_discounts(
        discount_app,
        campaign_bid="campaign-growth-fixed",
        operator_user_bid="publisher",
        provider=provider,
    )
    return provider, result["items"][0]["campaign_provider_discount_bid"]


@pytest.mark.parametrize(
    ("change", "failure"),
    [
        ({"provider_coupon_id": ""}, "provider_coupon_missing"),
        ({"valid": False}, "provider_coupon_invalid"),
        ({"livemode": True}, "livemode_mismatch"),
        ({"duration": "forever"}, "duration_mismatch"),
        ({"applies_to_product_ids": ["prod_someone_else"]}, "product_scope_mismatch"),
        ({"amount_off": 900}, "amount_off_mismatch"),
        ({"currency": "CNY"}, "currency_mismatch"),
    ],
)
def test_validation_persists_remote_drift_and_removes_checkout_eligibility(
    discount_app: Flask,
    published: tuple[_FakeCampaignDiscountProvider, str],
    change: dict[str, object],
    failure: str,
) -> None:
    provider, row_bid = published
    row = BillingCampaignProviderDiscount.query.one()
    coupon_id = row.provider_coupon_id
    provider.snapshots[coupon_id] = replace(provider.snapshots[coupon_id], **change)
    result = discounts.validate_admin_campaign_provider_discount(
        discount_app,
        campaign_provider_discount_bid=row_bid,
        operator_user_bid="validator",
        provider=provider,
    )
    db.session.expire_all()
    assert result["failure_code"] == failure
    assert row.status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_PROVIDER_INVALID
    assert row.updated_user_bid == "validator"
    assert row.validated_at is not None
    assert (
        discounts.load_current_stripe_campaign_provider_discount(
            campaign_bid=row.campaign_bid,
            product_bid=row.product_bid,
            provider_price_mapping=BillingProductProviderPrice.query.one(),
        )
        is None
    )


def test_percent_validation_rejects_changed_remote_discount(
    discount_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_scope(monkeypatch)
    _seed_discount_campaign(
        discount_type=BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
        discount_percent=Decimal(10),
    )
    provider = _FakeCampaignDiscountProvider()
    discounts.publish_admin_campaign_provider_discounts(
        discount_app,
        campaign_bid="campaign-growth-fixed",
        operator_user_bid="operator",
        provider=provider,
    )
    row = BillingCampaignProviderDiscount.query.one()
    provider.snapshots[row.provider_coupon_id] = replace(
        provider.snapshots[row.provider_coupon_id], percent_off=Decimal(20)
    )
    result = discounts.validate_admin_campaign_provider_discount(
        discount_app,
        campaign_provider_discount_bid=row.campaign_provider_discount_bid,
        operator_user_bid="validator",
        provider=provider,
    )
    assert result["failure_code"] == "percent_off_mismatch"
    db.session.expire_all()
    assert row.status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_PROVIDER_INVALID


def test_retry_of_unhealthy_coupon_persists_sanitized_provider_failure(
    discount_app: Flask, published: tuple[_FakeCampaignDiscountProvider, str]
) -> None:
    provider, row_bid = published
    row = BillingCampaignProviderDiscount.query.one()
    row.status = BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_FAILED
    db.session.commit()
    provider.retrieve_error = RuntimeError("unavailable sk_test_secret-do-not-store")
    discounts.publish_admin_campaign_provider_discounts(
        discount_app,
        campaign_bid=row.campaign_bid,
        operator_user_bid="retry-operator",
        provider=provider,
    )
    db.session.expire_all()
    assert BillingCampaignProviderDiscount.query.count() == 1
    assert row.campaign_provider_discount_bid == row_bid
    assert row.status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_FAILED
    assert row.failure_code == "provider_retrieve_failed"
    assert row.failure_message == "unavailable sk_****"
    assert row.updated_user_bid == "retry-operator"
    assert len(provider.created) == 1


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"campaign_price_amount": 0}, "invalid_fixed_discount"),
        ({"campaign_price_amount": 5900}, "invalid_fixed_discount"),
        (
            {
                "discount_type": BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
                "discount_percent": Decimal(0),
            },
            "invalid_percent_discount",
        ),
        (
            {
                "discount_type": BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
                "discount_percent": Decimal(101),
            },
            "invalid_percent_discount",
        ),
        ({"discount_type": 999}, "invalid_discount_type"),
    ],
)
def test_invalid_persisted_campaign_rule_never_creates_remote_coupon(
    discount_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    change: dict[str, object],
    code: str,
) -> None:
    _patch_scope(monkeypatch)
    _seed_discount_campaign()
    binding = BillingCampaignProduct.query.one()
    for name, value in change.items():
        setattr(binding, name, value)
    db.session.commit()
    provider = _FakeCampaignDiscountProvider()
    with pytest.raises(discounts.CampaignProviderDiscountError) as exc:
        discounts.publish_admin_campaign_provider_discounts(
            discount_app,
            campaign_bid=binding.campaign_bid,
            operator_user_bid="operator",
            provider=provider,
        )
    assert exc.value.code == code
    assert str(exc.value) == exc.value.message
    assert exc.value.details["product_bid"] == binding.product_bid
    assert provider.created == []
    assert BillingCampaignProviderDiscount.query.count() == 0


@pytest.mark.parametrize("missing", ["bindings", "product", "mapping"])
def test_publish_requires_live_catalog_relationships(
    discount_app: Flask, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    _patch_scope(monkeypatch)
    _seed_discount_campaign()
    model = {
        "bindings": BillingCampaignProduct,
        "product": BillingProduct,
        "mapping": BillingProductProviderPrice,
    }[missing]
    model.query.one().deleted = 1
    db.session.commit()
    provider = _FakeCampaignDiscountProvider()
    expected = ProviderPriceMappingError if missing == "mapping" else AppError
    with pytest.raises(expected):
        discounts.publish_admin_campaign_provider_discounts(
            discount_app,
            campaign_bid="campaign-growth-fixed",
            operator_user_bid="operator",
            provider=provider,
        )
    assert provider.created == []
    assert BillingCampaignProviderDiscount.query.count() == 0


@pytest.mark.parametrize("row_kind", ["absent", "coupon_missing"])
def test_manual_validation_has_specific_missing_reference_error(
    discount_app: Flask,
    published: tuple[_FakeCampaignDiscountProvider, str],
    row_kind: str,
) -> None:
    provider, row_bid = published
    if row_kind == "absent":
        row_bid = "missing-discount"
        expected = "campaign_provider_discount_not_found"
    else:
        row = BillingCampaignProviderDiscount.query.one()
        row.provider_coupon_id = ""
        db.session.commit()
        expected = "provider_coupon_missing"
    with pytest.raises(discounts.CampaignProviderDiscountError) as exc:
        discounts.validate_admin_campaign_provider_discount(
            discount_app,
            campaign_provider_discount_bid=row_bid,
            operator_user_bid="operator",
            provider=provider,
        )
    assert exc.value.code == expected
    assert exc.value.details["campaign_provider_discount_bid"] == row_bid


@pytest.mark.parametrize("action", ["publish", "list", "retire", "validate"])
def test_admin_coupon_actions_reject_empty_identifier(
    discount_app: Flask, action: str
) -> None:
    function = getattr(
        discounts,
        f"{action}_admin_campaign_provider_discount"
        + ("" if action == "validate" else "s"),
    )
    kwargs = {
        "campaign_provider_discount_bid"
        if action == "validate"
        else "campaign_bid": " "
    }
    if action != "list":
        kwargs["operator_user_bid"] = "operator"
    with pytest.raises(AppError):
        function(discount_app, **kwargs)


def test_activation_requires_mapping_in_current_account(
    discount_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_scope(monkeypatch)
    _seed_discount_campaign()
    BillingProductProviderPrice.query.one().deleted = 1
    db.session.commit()
    with pytest.raises(AppError):
        discounts.assert_current_stripe_campaign_provider_discounts_ready(
            discount_app,
            campaign_bid="campaign-growth-fixed",
            product_bids=["product-growth-month"],
        )


def test_unknown_campaign_cannot_be_listed(discount_app: Flask) -> None:
    with pytest.raises(AppError):
        discounts.list_admin_campaign_provider_discounts(
            discount_app, campaign_bid="missing"
        )
