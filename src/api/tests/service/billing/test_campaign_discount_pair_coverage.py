"""Cover interrupted publication across each required provider/product pair."""

from datetime import timedelta

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing import campaigns
from flaskr.service.billing.campaign_provider_discounts import (
    summarize_campaign_provider_discounts,
)
from flaskr.service.billing.consts import (
    BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_CREATING,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_RETIRED,
    BILLING_PRODUCT_TYPE_PLAN,
)
from flaskr.service.billing.models import (
    BillingCampaign,
    BillingCampaignProduct,
    BillingCampaignProviderDiscount,
    BillingProductProviderPrice,
)
from flaskr.service.billing.provider_price_mappings import ProviderPriceRuntimeScope
from flaskr.service.config import config_overrides
from flaskr.service.order import payment_providers
from flaskr.util.datetime import now_utc

from tests.service.order.test_payment_catalog_extension import (
    CatalogHostedProvider,
    integration_app,
)

__all__ = ["integration_app"]


@pytest.fixture(autouse=True)
def current_price_scopes(
    integration_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.billing import campaign_provider_discounts
    from flaskr.service.billing.consts import BILLING_PROVIDER_PRICE_STATUS_ACTIVE

    assert integration_app.testing
    monkeypatch.setattr(
        campaign_provider_discounts,
        "_DISCOUNT_SCOPE_RESOLVERS",
        {
            provider: lambda _app: ProviderPriceRuntimeScope(
                provider_account_id="acct_test", livemode=False
            )
            for provider in ("stripe", "fixture-catalog")
        },
    )
    with unit_of_work():
        db.session.add_all(
            BillingProductProviderPrice(
                provider_price_bid=f"price-{provider}-{product}",
                product_bid=product,
                provider=provider,
                provider_account_id="acct_test",
                provider_product_id=f"product-{provider}-{product}",
                provider_price_id=f"remote-price-{provider}-{product}",
                status=BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
            )
            for provider in ("stripe", "fixture-catalog")
            for product in (
                "a",
                "b",
                "other",
                "removed",
                "bill-product-plan-monthly",
                "bill-product-plan-monthly-pro",
            )
        )


def _bind(
    campaign_bid: str, product_bid: str, *, deleted: int = 0
) -> BillingCampaignProduct:
    return BillingCampaignProduct(
        campaign_bid=campaign_bid,
        product_bid=product_bid,
        product_type=BILLING_PRODUCT_TYPE_PLAN,
        discount_type=BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
        campaign_price_amount=490,
        deleted=deleted,
    )


def _coupon(
    index: int,
    provider: str,
    product: str,
    *,
    campaign: str = "pair-campaign",
    status: int = BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE,
    deleted: int = 0,
    coupon: str | None = None,
) -> BillingCampaignProviderDiscount:
    return BillingCampaignProviderDiscount(
        campaign_provider_discount_bid=f"pair-{index}",
        campaign_bid=campaign,
        product_bid=product,
        product_provider_price_bid=f"price-{provider}-{product}",
        provider=provider,
        provider_account_id="acct_test",
        provider_coupon_id=f"coupon-{index}" if coupon is None else coupon,
        status=status,
        deleted=deleted,
    )


@pytest.mark.parametrize(
    ("providers", "pairs", "expected"),
    [
        (["stripe"], [("stripe", "a"), ("stripe", "b")], 0),
        (["stripe"], [("stripe", "a")], 1),
        (
            ["stripe", "fixture-catalog"],
            [("stripe", "a"), ("stripe", "b"), ("fixture-catalog", "a")],
            1,
        ),
        (
            ["stripe", "fixture-catalog"],
            [
                ("stripe", "a"),
                ("stripe", "b"),
                ("fixture-catalog", "a"),
                ("fixture-catalog", "b"),
            ],
            0,
        ),
        (
            ["stripe", "fixture-catalog"],
            [("stripe", "a"), ("stripe", "a"), ("fixture-catalog", "a")],
            2,
        ),
        (
            ["stripe", "fixture-catalog"],
            [("stripe", "a"), ("stripe", "b"), ("fixture-catalog", "other")],
            1,
        ),
        (["stripe", "fixture-catalog"], [], 2),
    ],
)
def test_coverage_requires_each_campaign_product(
    integration_app: Flask,
    providers: list[str],
    pairs: list[tuple[str, str]],
    expected: int,
) -> None:
    assert integration_app.testing
    with unit_of_work():
        db.session.add_all([_bind("pair-campaign", "a"), _bind("pair-campaign", "b")])
        seen = set()
        for index, (provider, product) in enumerate(pairs):
            row = _coupon(index, provider, product)
            if (provider, product) in seen:
                row.product_provider_price_bid = f"historical-price-{index}"
            seen.add((provider, product))
            db.session.add(row)
    summary = summarize_campaign_provider_discounts(
        ["pair-campaign"], required_providers=providers
    )
    assert summary["pair-campaign"]["missing_provider_count"] == expected


@pytest.mark.parametrize(
    ("status", "deleted", "coupon"),
    [
        (BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_RETIRED, 0, "retired"),
        (BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_CREATING, 0, ""),
        (BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE, 1, "deleted"),
        (BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE, 0, ""),
    ],
)
def test_invalid_coupon_does_not_fill_missing_pair(
    integration_app: Flask, status: int, deleted: int, coupon: str
) -> None:
    assert integration_app.testing
    with unit_of_work():
        db.session.add_all([_bind("pair-campaign", "a"), _bind("pair-campaign", "b")])
        db.session.add_all(
            [
                _coupon(1, "stripe", "a"),
                _coupon(2, "stripe", "b"),
                _coupon(3, "fixture-catalog", "a"),
                _coupon(
                    4,
                    "fixture-catalog",
                    "b",
                    status=status,
                    deleted=deleted,
                    coupon=coupon,
                ),
            ]
        )
    summary = summarize_campaign_provider_discounts(
        ["pair-campaign"], required_providers=["stripe", "fixture-catalog"]
    )
    assert summary["pair-campaign"]["missing_provider_count"] == 1


def test_campaign_and_deleted_binding_isolation(integration_app: Flask) -> None:
    assert integration_app.testing
    with unit_of_work():
        db.session.add_all(
            [
                _bind("pair-campaign", "a"),
                _bind("pair-campaign", "b"),
                _bind("other-campaign", "a"),
                _bind("other-campaign", "removed", deleted=1),
            ]
        )
        db.session.add_all(
            [
                _coupon(1, "stripe", "a"),
                _coupon(2, "stripe", "a", campaign="other-campaign"),
                _coupon(3, "stripe", "b", campaign="other-campaign"),
            ]
        )
    summaries = summarize_campaign_provider_discounts(
        ["pair-campaign", "other-campaign"], required_providers=["stripe"]
    )
    assert summaries["pair-campaign"]["missing_provider_count"] == 1
    assert summaries["other-campaign"]["missing_provider_count"] == 0


def test_list_and_detail_recover_only_after_missing_pair_is_published(
    integration_app: Flask,
) -> None:
    app = integration_app
    payment_providers.register_payment_provider(CatalogHostedProvider)
    products = ["bill-product-plan-monthly", "bill-product-plan-monthly-pro"]
    now = now_utc()
    with unit_of_work():
        db.session.add(
            BillingCampaign(
                campaign_bid="pair-campaign",
                name="Pair coverage",
                benefit_type=BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
                discount_type=BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
                enabled=0,
                start_at=now - timedelta(days=1),
                end_at=now + timedelta(days=1),
            )
        )
        db.session.add_all(_bind("pair-campaign", product) for product in products)
        db.session.add_all(
            [
                _coupon(1, "stripe", products[0]),
                _coupon(2, "stripe", products[1]),
                _coupon(3, "fixture-catalog", products[0]),
            ]
        )
    with config_overrides(
        {"PAYMENT_CHANNELS_ENABLED": "stripe,fixture-catalog", "STRIPE_ENABLED": True}
    ):
        for expected in (1, 0):
            detail = campaigns.build_admin_billing_campaign_detail(app, "pair-campaign")
            page = campaigns.build_admin_billing_campaigns_page(app)
            assert (
                detail.campaign.provider_discount_summary["missing_provider_count"]
                == expected
            )
            row = next(row for row in page.items if row.campaign_bid == "pair-campaign")
            assert (
                row.provider_discount_summary
                == detail.campaign.provider_discount_summary
            )
            if expected:
                with unit_of_work():
                    db.session.add(_coupon(4, "fixture-catalog", products[1]))
