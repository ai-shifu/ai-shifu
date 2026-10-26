"""Verify operator campaign inputs, legacy rules, and locked pricing snapshots."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.service.billing import campaigns
from flaskr.service.billing.consts import (
    BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    BILLING_ORDER_STATUS_PAID,
)
from flaskr.service.billing.models import (
    BillingCampaign,
    BillingCampaignProduct,
    BillingOrder,
    BillingProduct,
)
from flaskr.service.common.models import AppError
from flaskr.util.datetime import now_utc

from tests.common.fixtures.bill_products import build_billing_product

if TYPE_CHECKING:
    from flask import Flask


def _product() -> BillingProduct:
    product = build_billing_product(
        "bill-product-plan-monthly",
        overrides={
            "product_bid": uuid4().hex,
            "product_code": uuid4().hex,
            "price_amount": 1000,
        },
    )
    db.session.add(product)
    db.session.commit()
    return product


def _payload(product_bid: str) -> dict:
    return {
        "name": uuid4().hex,
        "benefit_type": "discount",
        "enabled": False,
        "start_at": (now_utc() - timedelta(days=1)).isoformat() + "Z",
        "end_at": (now_utc() + timedelta(days=1)).isoformat() + "Z",
        "products": [
            {
                "product_bid": product_bid,
                "discount_type": "fixed",
                "campaign_price_amount": 500,
            }
        ],
    }


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"name": "x" * 256},
        {"note": "x" * 501},
        {"benefit_type": ""},
        {"benefit_type": "unsupported"},
        {"start_at": "bad"},
        {"end_at": "2000-01-01T00:00:00Z"},
        {"products": [None]},
        {"products": [{"product_bid": " "}]},
        {"products": None, "product_bids": None},
        {"products": None, "product_bids": []},
    ],
)
def test_campaign_create_rejects_invalid_input_before_writes(
    change: dict, app: Flask
) -> None:
    with app.app_context():
        product = _product()
        payload = _payload(product.product_bid) | change
        before = BillingCampaign.query.count()
        with pytest.raises(AppError):
            campaigns.create_admin_billing_campaign(
                app, operator_user_bid="operator-test", payload=payload
            )
        assert BillingCampaign.query.count() == before


@pytest.mark.parametrize(
    ("benefit", "draft"),
    [
        ("discount", {"discount_type": ""}),
        ("discount", {"discount_type": "unsupported"}),
        ("discount", {"discount_type": "fixed", "campaign_price_amount": "invalid"}),
        ("discount", {"discount_type": "fixed", "campaign_price_amount": 1000}),
        ("discount", {"discount_type": "percent", "discount_percent": "invalid"}),
        ("discount", {"discount_type": "percent", "discount_percent": 101}),
        ("bonus", {"bonus_credit_amount": "invalid"}),
        ("bonus", {"bonus_credit_amount": 0}),
    ],
)
def test_campaign_rejects_unusable_per_product_benefits(
    benefit: str, draft: dict, app: Flask
) -> None:
    with app.app_context():
        product = _product()
        payload = _payload(product.product_bid) | {
            "benefit_type": benefit,
            "products": [{"product_bid": product.product_bid} | draft],
        }
        with pytest.raises(AppError):
            campaigns.create_admin_billing_campaign(
                app, operator_user_bid="operator-test", payload=payload
            )
        assert BillingCampaign.query.filter_by(name=payload["name"]).count() == 0
        assert (
            BillingCampaignProduct.query.filter_by(
                product_bid=product.product_bid
            ).count()
            == 0
        )


@pytest.mark.parametrize(
    ("benefit", "legacy", "price", "bonus"),
    [
        ("discount", {"discount_type": "fixed", "discount_amount": 100}, 900, "0"),
        (
            "discount",
            {"discount_type": "percent", "discount_percent": "12.5"},
            875,
            "0",
        ),
        ("bonus", {"bonus_credit_amount": "2.5"}, 1000, "2.5"),
    ],
)
def test_legacy_campaign_payload_deduplicates_products_and_stores_resolved_prices(
    benefit: str, legacy: dict, price: int, bonus: str, app: Flask
) -> None:
    with app.app_context():
        product = _product()
        payload = (
            _payload(product.product_bid)
            | {
                "products": None,
                "product_bids": [product.product_bid, " ", product.product_bid],
                "benefit_type": benefit,
            }
            | legacy
        )
        result = campaigns.create_admin_billing_campaign(
            app, operator_user_bid="operator-test", payload=payload
        )
        row = BillingCampaign.query.filter_by(name=payload["name"]).one()
        binding = BillingCampaignProduct.query.filter_by(
            campaign_bid=row.campaign_bid
        ).one()
        assert result.campaign.campaign_bid == row.campaign_bid
        assert binding.campaign_price_amount == price
        assert binding.bonus_credit_amount == Decimal(bonus)
        assert row.created_user_bid == "operator-test"


@pytest.mark.parametrize("amount", ["invalid", 0, 1000])
def test_legacy_fixed_discount_cannot_be_invalid_or_remove_entire_price(
    amount: object, app: Flask
) -> None:
    with app.app_context():
        product = _product()
        payload = _payload(product.product_bid) | {
            "products": None,
            "product_bids": [product.product_bid],
            "discount_type": "fixed",
            "discount_amount": amount,
        }
        with pytest.raises(AppError):
            campaigns.create_admin_billing_campaign(
                app, operator_user_bid="operator-test", payload=payload
            )
        assert BillingCampaign.query.filter_by(name=payload["name"]).count() == 0


@pytest.mark.parametrize("change", ["benefit", "product", "amount"])
def test_campaign_that_has_orders_cannot_change_purchased_pricing_contract(
    change: str, app: Flask
) -> None:
    with app.app_context():
        product = _product()
        payload = _payload(product.product_bid)
        created = campaigns.create_admin_billing_campaign(
            app, operator_user_bid="operator-before", payload=payload
        )
        campaign_bid = created.campaign.campaign_bid
        db.session.add(
            BillingOrder(
                bill_order_bid=uuid4().hex,
                creator_bid=uuid4().hex,
                campaign_bid=campaign_bid,
                product_bid=product.product_bid,
                status=BILLING_ORDER_STATUS_PAID,
            )
        )
        db.session.commit()
        replacement = payload | {"name": "must-roll-back"}
        if change == "benefit":
            replacement.update(
                benefit_type="bonus",
                products=[
                    {"product_bid": product.product_bid, "bonus_credit_amount": "5"}
                ],
            )
        elif change == "product":
            replacement["products"] = [
                {
                    "product_bid": _product().product_bid,
                    "discount_type": "fixed",
                    "campaign_price_amount": 500,
                }
            ]
        else:
            replacement["products"] = [
                {
                    "product_bid": product.product_bid,
                    "discount_type": "fixed",
                    "campaign_price_amount": 400,
                }
            ]
        with pytest.raises(AppError):
            campaigns.update_admin_billing_campaign(
                app,
                operator_user_bid="operator-after",
                campaign_bid=campaign_bid,
                payload=replacement,
            )
        db.session.expire_all()
        row = BillingCampaign.query.filter_by(campaign_bid=campaign_bid).one()
        assert row.name == payload["name"]
        assert row.updated_user_bid == "operator-before"
        binding = BillingCampaignProduct.query.filter_by(
            campaign_bid=campaign_bid
        ).one()
        assert binding.product_bid == product.product_bid
        assert binding.campaign_price_amount == 500


@pytest.mark.parametrize("operation", ["detail", "update", "status"])
@pytest.mark.parametrize("identifier", ["", "missing"])
def test_campaign_admin_operations_reject_missing_identity(
    operation: str, identifier: str, app: Flask
) -> None:
    method = {
        "detail": campaigns.build_admin_billing_campaign_detail,
        "update": campaigns.update_admin_billing_campaign,
        "status": campaigns.update_admin_billing_campaign_status,
    }[operation]
    kwargs = (
        {}
        if operation == "detail"
        else {"operator_user_bid": "operator", "payload": {"enabled": True}}
    )
    with app.app_context(), pytest.raises(AppError):
        method(app, campaign_bid=identifier, **kwargs)


@pytest.mark.parametrize(
    "filters",
    [
        {"status": "unsupported"},
        {"product_type": "custom"},
        {"benefit_type": "unknown"},
    ],
)
def test_campaign_listing_rejects_unknown_operator_filters(
    filters: dict, app: Flask
) -> None:
    with pytest.raises(AppError):
        campaigns.build_admin_billing_campaigns_page(app, **filters)


@pytest.mark.parametrize("status", ["upcoming", "ended", "inactive"])
def test_campaign_listing_filters_status_and_intersecting_date_window(
    status: str, app: Flask
) -> None:
    with app.app_context():
        product = _product()
        marker = uuid4().hex
        current = now_utc()
        rows = [
            BillingCampaign(
                campaign_bid=uuid4().hex,
                name=marker + " upcoming",
                enabled=1,
                benefit_type=BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
                start_at=current + timedelta(days=2),
                end_at=current + timedelta(days=3),
            ),
            BillingCampaign(
                campaign_bid=uuid4().hex,
                name=marker + " ended",
                enabled=1,
                benefit_type=BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
                start_at=current - timedelta(days=3),
                end_at=current - timedelta(days=2),
            ),
            BillingCampaign(
                campaign_bid=uuid4().hex,
                name=marker + " inactive",
                enabled=0,
                benefit_type=BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
                start_at=current - timedelta(hours=1),
                end_at=current + timedelta(hours=1),
            ),
        ]
        db.session.add_all(rows)
        for row in rows:
            db.session.add(
                BillingCampaignProduct(
                    campaign_bid=row.campaign_bid,
                    product_bid=product.product_bid,
                    product_type=product.product_type,
                )
            )
        db.session.commit()
        result = campaigns.build_admin_billing_campaigns_page(
            app,
            keyword=marker,
            status=status,
            start_time=(current - timedelta(days=4)).isoformat(),
            end_time=(current + timedelta(days=4)).isoformat(),
        )
        assert result.total == 1
        assert result.items[0].name == marker + " " + status
