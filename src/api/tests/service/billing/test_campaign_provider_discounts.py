"""Verify billing campaign provider discount publishing."""

from __future__ import annotations

from decimal import Decimal

import pytest
from flaskr.dao import db
from flaskr.service.billing.campaign_discount_providers import (
    ProviderDiscountCreateRequest,
    ProviderDiscountSnapshot,
)
from flaskr.service.billing.campaign_provider_discounts import (
    list_admin_campaign_provider_discounts,
    publish_admin_campaign_provider_discounts,
    retire_admin_campaign_provider_discounts,
    validate_admin_campaign_provider_discount,
)
from flaskr.service.billing.campaigns import update_admin_billing_campaign
from flaskr.service.billing.consts import (
    BILLING_CAMPAIGN_BENEFIT_TYPE_BONUS,
    BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_REQUIRES_REPUBLISH,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_RETIRED,
    BILLING_INTERVAL_MONTH,
    BILLING_MODE_RECURRING,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import (
    BillingCampaign,
    BillingCampaignProduct,
    BillingCampaignProviderDiscount,
    BillingProduct,
    BillingProductProviderPrice,
)
from flaskr.service.billing.provider_price_mappings import (
    ProviderPriceRuntimeScope,
    retire_provider_price_mapping,
)
from flaskr.service.common.models import AppError
from flaskr.util.datetime import now_utc


class _FakeCampaignDiscountProvider:
    def __init__(self) -> None:
        self.created: list[ProviderDiscountCreateRequest] = []
        self.retired: list[str] = []
        self.snapshots: dict[str, ProviderDiscountSnapshot] = {}

    def create_campaign_discount(
        self, *, request: ProviderDiscountCreateRequest, app: object
    ) -> ProviderDiscountSnapshot:
        _ = app
        self.created.append(request)
        coupon_id = f"coupon_{request.campaign_provider_discount_bid}"
        snapshot = ProviderDiscountSnapshot(
            provider_coupon_id=coupon_id,
            provider_account_id="acct_test",
            livemode=False,
            valid=True,
            currency=request.currency,
            amount_off=request.amount_off,
            percent_off=request.percent_off,
            duration=request.duration,
            metadata=request.metadata,
        )
        self.snapshots[coupon_id] = snapshot
        return snapshot

    def retrieve_campaign_discount(
        self, *, provider_coupon_id: str, app: object
    ) -> ProviderDiscountSnapshot:
        _ = app
        return self.snapshots[provider_coupon_id]

    def retire_campaign_discount(
        self, *, provider_coupon_id: str, app: object
    ) -> ProviderDiscountSnapshot:
        _ = app
        self.retired.append(provider_coupon_id)
        return self.snapshots[provider_coupon_id]


def _product(product_bid: str = "product-growth-month") -> BillingProduct:
    return BillingProduct(
        product_bid=product_bid,
        product_code=f"creator-global-growth-{product_bid}",
        product_type=BILLING_PRODUCT_TYPE_PLAN,
        billing_mode=BILLING_MODE_RECURRING,
        billing_interval=BILLING_INTERVAL_MONTH,
        billing_interval_count=1,
        display_name_i18n_key="module.billing.catalog.growth.title",
        description_i18n_key="module.billing.catalog.growth.description",
        currency="USD",
        price_amount=5900,
        credit_amount=Decimal(1000),
        status=BILLING_PRODUCT_STATUS_ACTIVE,
        sort_order=10,
        metadata_json={"plan_tier": "growth"},
    )


def _mapping(product_bid: str = "product-growth-month") -> BillingProductProviderPrice:
    return BillingProductProviderPrice(
        provider_price_bid=f"provider-price-{product_bid}",
        product_bid=product_bid,
        provider="stripe",
        provider_account_id="acct_test",
        provider_product_id="prod_growth",
        provider_price_id=f"price_{product_bid}",
        livemode=0,
        currency="USD",
        unit_amount=5900,
        billing_mode=BILLING_MODE_RECURRING,
        billing_interval=BILLING_INTERVAL_MONTH,
        billing_interval_count=1,
        status=BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
        activated_at=now_utc(),
    )


def _campaign(
    *,
    campaign_bid: str = "campaign-growth-fixed",
    benefit_type: int = BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    discount_type: int = BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
    discount_percent: Decimal = Decimal(0),
    bonus_credit_amount: Decimal = Decimal(0),
) -> BillingCampaign:
    now = now_utc()
    return BillingCampaign(
        campaign_bid=campaign_bid,
        name="Growth launch",
        note="",
        benefit_type=benefit_type,
        discount_type=discount_type,
        discount_amount=1000
        if discount_type == BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED
        else 0,
        discount_percent=discount_percent,
        bonus_credit_amount=bonus_credit_amount,
        enabled=1,
        start_at=now,
        end_at=now.replace(year=now.year + 1),
        created_user_bid="operator",
        updated_user_bid="operator",
    )


def _binding(
    *,
    campaign_bid: str = "campaign-growth-fixed",
    product_bid: str = "product-growth-month",
    benefit_type: int = BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    discount_type: int = BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
    campaign_price_amount: int = 4900,
    discount_percent: Decimal = Decimal(0),
    bonus_credit_amount: Decimal = Decimal(0),
) -> BillingCampaignProduct:
    return BillingCampaignProduct(
        campaign_bid=campaign_bid,
        product_bid=product_bid,
        product_type=BILLING_PRODUCT_TYPE_PLAN,
        discount_type=discount_type
        if benefit_type == BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT
        else 0,
        discount_amount=1000
        if discount_type == BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED
        else 0,
        discount_percent=discount_percent,
        campaign_price_amount=campaign_price_amount,
        bonus_credit_amount=bonus_credit_amount,
    )


def _seed_discount_campaign(
    *,
    campaign_bid: str = "campaign-growth-fixed",
    product_bid: str = "product-growth-month",
    discount_type: int = BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
    campaign_price_amount: int = 4900,
    discount_percent: Decimal = Decimal(0),
) -> None:
    product = _product(product_bid)
    db.session.add(product)
    db.session.add(_mapping(product.product_bid))
    db.session.add(
        _campaign(
            campaign_bid=campaign_bid,
            discount_type=discount_type,
            discount_percent=discount_percent,
        )
    )
    db.session.add(
        _binding(
            campaign_bid=campaign_bid,
            product_bid=product.product_bid,
            discount_type=discount_type,
            campaign_price_amount=campaign_price_amount,
            discount_percent=discount_percent,
        )
    )
    db.session.commit()


def _patch_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    import flaskr.service.billing.campaign_provider_discounts as module

    monkeypatch.setattr(
        module,
        "resolve_current_stripe_provider_price_scope",
        lambda _app: ProviderPriceRuntimeScope(
            provider_account_id="acct_test", livemode=False
        ),
    )


def test_publish_fixed_campaign_creates_amount_off_coupon(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(product_bid="product-growth-fixed-1")
    _patch_scope(monkeypatch)

    payload = publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-fixed",
        operator_user_bid="operator",
        provider=provider,
    )

    assert len(provider.created) == 1
    assert provider.created[0].amount_off == 1000
    assert provider.created[0].percent_off is None
    assert provider.created[0].duration == "once"
    assert payload["items"][0]["status"] == "active"
    with app.app_context():
        row = BillingCampaignProviderDiscount.query.first()
        assert row.status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE
        assert row.provider_coupon_id == f"coupon_{row.campaign_provider_discount_bid}"


def test_publish_percent_campaign_creates_percent_off_coupon(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-percent",
            product_bid="product-growth-percent-1",
            discount_type=BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
            campaign_price_amount=4720,
            discount_percent=Decimal("20.00"),
        )
    _patch_scope(monkeypatch)

    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-percent",
        operator_user_bid="operator",
        provider=provider,
    )

    assert len(provider.created) == 1
    assert provider.created[0].amount_off is None
    assert provider.created[0].percent_off == Decimal("20.00")


def test_bonus_campaign_does_not_create_provider_coupon(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        product = _product("product-growth-bonus-1")
        db.session.add(product)
        db.session.add(_mapping(product.product_bid))
        db.session.add(
            _campaign(
                campaign_bid="campaign-growth-bonus",
                benefit_type=BILLING_CAMPAIGN_BENEFIT_TYPE_BONUS,
                bonus_credit_amount=Decimal(500),
            )
        )
        db.session.add(
            _binding(
                campaign_bid="campaign-growth-bonus",
                product_bid=product.product_bid,
                benefit_type=BILLING_CAMPAIGN_BENEFIT_TYPE_BONUS,
                campaign_price_amount=5900,
                bonus_credit_amount=Decimal(500),
            )
        )
        db.session.commit()
    _patch_scope(monkeypatch)

    payload = publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-bonus",
        operator_user_bid="operator",
        provider=provider,
    )

    assert provider.created == []
    assert payload["summary"] == {"total": 0, "active": 0, "failed": 0}


def test_validate_and_retire_campaign_provider_discount(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-retire", product_bid="product-growth-retire-1"
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-retire",
        operator_user_bid="operator",
        provider=provider,
    )
    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-retire"
        ).first()
        row_bid = row.campaign_provider_discount_bid

    validation = validate_admin_campaign_provider_discount(
        app,
        campaign_provider_discount_bid=row_bid,
        operator_user_bid="operator",
        provider=provider,
    )
    assert validation["status"] == "active"

    payload = retire_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-retire",
        operator_user_bid="operator",
        provider=provider,
    )

    assert provider.retired == [payload["items"][0]["provider_coupon_id"]]
    assert payload["items"][0]["status"] == "retired"
    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-retire"
        ).first()
        assert row.status == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_RETIRED


def test_publish_after_retire_creates_replacement_coupon(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-republish",
            product_bid="product-growth-republish-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-republish",
        operator_user_bid="operator",
        provider=provider,
    )
    retire_payload = retire_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-republish",
        operator_user_bid="operator",
        provider=provider,
    )
    retired_row_bid = retire_payload["items"][0]["campaign_provider_discount_bid"]

    publish_payload = publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-republish",
        operator_user_bid="operator",
        provider=provider,
    )

    active_items = [
        item for item in publish_payload["items"] if item["status"] == "active"
    ]
    assert len(provider.created) == 2
    assert len(active_items) == 1
    assert active_items[0]["campaign_provider_discount_bid"] != retired_row_bid
    with app.app_context():
        replacement = BillingCampaignProviderDiscount.query.filter_by(
            campaign_provider_discount_bid=active_items[0][
                "campaign_provider_discount_bid"
            ]
        ).one()
        assert replacement.replaces_discount_bid == retired_row_bid


def test_list_campaign_provider_discounts_is_read_only(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-list", product_bid="product-growth-list-1"
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-list",
        operator_user_bid="operator",
        provider=provider,
    )

    payload = list_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-list",
    )

    assert payload["items"][0]["provider_coupon_id"].startswith("coupon_")
    assert payload["items"][0]["provider_price_id"] == "price_product-growth-list-1"


def test_retiring_provider_price_requires_campaign_coupon_republish(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-price-retired",
            product_bid="product-growth-price-retired-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-price-retired",
        operator_user_bid="operator",
        provider=provider,
    )

    with app.app_context():
        row = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-price-retired"
        ).one()
        retire_provider_price_mapping(row.product_provider_price_bid)
        db.session.commit()

        refreshed = BillingCampaignProviderDiscount.query.filter_by(
            campaign_bid="campaign-growth-price-retired"
        ).one()
        assert (
            refreshed.status
            == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_REQUIRES_REPUBLISH
        )
        assert refreshed.failure_code == "provider_price_retired"


def test_update_campaign_blocks_rule_changes_after_coupon_publish(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _FakeCampaignDiscountProvider()
    with app.app_context():
        _seed_discount_campaign(
            campaign_bid="campaign-growth-rule-lock",
            product_bid="product-growth-rule-lock-1",
        )
    _patch_scope(monkeypatch)
    publish_admin_campaign_provider_discounts(
        app,
        campaign_bid="campaign-growth-rule-lock",
        operator_user_bid="operator",
        provider=provider,
    )
    with app.app_context():
        campaign = BillingCampaign.query.filter_by(
            campaign_bid="campaign-growth-rule-lock"
        ).one()
        start_at = campaign.start_at
        end_at = campaign.end_at

    with pytest.raises(AppError) as exc_info:
        update_admin_billing_campaign(
            app,
            operator_user_bid="operator",
            campaign_bid="campaign-growth-rule-lock",
            payload={
                "name": "Growth launch updated",
                "note": "",
                "benefit_type": "discount",
                "products": [
                    {
                        "product_bid": "product-growth-rule-lock-1",
                        "discount_type": "fixed",
                        "campaign_price_amount": "4800",
                    }
                ],
                "start_at": start_at,
                "end_at": end_at,
            },
        )

    assert "Stripe Coupon" in str(exc_info.value)
