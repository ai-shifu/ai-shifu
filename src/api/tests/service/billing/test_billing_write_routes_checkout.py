"""Verify billing write routes checkout behavior."""

from __future__ import annotations

import pytest

from tests.service.billing import (
    billing_write_routes_test_helpers as write_route_helpers,
)
from tests.service.billing.billing_write_routes_test_helpers import (
    ALLOCATION_INTERVAL_PER_CYCLE,
    BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
    BILLING_INTERVAL_DAY,
    BILLING_MODE_RECURRING,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILLING_TRIAL_PRODUCT_BID,
    ERROR_CODE,
    BillingCampaign,
    BillingCampaignProduct,
    BillingOrder,
    BillingProduct,
    BillingSubscription,
    Decimal,
    billing_write_routes_module,
    dao,
    now_utc,
    timedelta,
)


@pytest.fixture
def billing_write_client(monkeypatch: object):
    yield from write_route_helpers.billing_write_client(monkeypatch)


class TestBillingWriteRoutesCheckout:
    """Verify billing write routes checkout behavior."""

    def test_subscription_checkout_rejects_when_billing_feature_disabled(
        self: object, billing_write_client: object, monkeypatch: object
    ) -> None:
        client = billing_write_client["client"]

        monkeypatch.setattr(
            billing_write_routes_module,
            "is_billing_enabled",
            lambda: False,
        )

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        )
        payload = response.get_json(force=True)

        assert payload["code"] == ERROR_CODE["server.billing.disabled"]
        assert billing_write_client["stripe_requests"] == []

    def test_subscription_checkout_uses_configured_provider_when_omitted(
        self: object, billing_write_client: object, monkeypatch: object
    ) -> None:
        client = billing_write_client["client"]

        def fake_get_config(key: object, default: object = None):
            if key == "PAYMENT_CHANNELS_ENABLED":
                return "stripe"
            return default

        monkeypatch.setattr(
            "flaskr.service.order.payment_channel_resolution.get_config",
            fake_get_config,
        )

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
            },
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["provider"] == "stripe"
        assert payload["data"]["status"] == "pending"

    def test_subscription_checkout_creates_draft_subscription_and_pending_order(
        self: object, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
            headers={"X-Language": "zh-CN"},
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["provider"] == "stripe"
        assert payload["data"]["payment_mode"] == "subscription"
        assert payload["data"]["status"] == "pending"
        assert payload["data"]["redirect_url"] == "https://stripe.test/checkout"
        bill_order_bid = payload["data"]["bill_order_bid"]
        stripe_request = billing_write_client["stripe_requests"][0]
        assert stripe_request["extra"]["success_url"] == (
            "https://billing.example.com/payment/stripe/billing-result"
            f"?bill_order_bid={bill_order_bid}"
        )
        assert stripe_request["extra"]["cancel_url"] == (
            "https://billing.example.com/payment/stripe/billing-result"
            f"?canceled=1&bill_order_bid={bill_order_bid}"
        )

        with app.app_context():
            order = BillingOrder.query.filter_by(creator_bid="creator-1").one()
            subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1"
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PENDING
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_DRAFT
            assert order.subscription_bid == subscription.subscription_bid

        stripe_request = billing_write_client["stripe_requests"][0]
        assert stripe_request["subject"] == "月套餐·轻量版"
        assert stripe_request["body"] == "月套餐·轻量版"
        assert (
            stripe_request["extra"]["line_items"][0]["price_data"]["product_data"][
                "name"
            ]
            == "月套餐·轻量版"
        )
        assert stripe_request["extra"]["session_params"]["mode"] == "subscription"
        assert (
            stripe_request["extra"]["line_items"][0]["price_data"]["recurring"][
                "interval"
            ]
            == "month"
        )

    def test_subscription_checkout_starts_new_order_when_active_status_is_stale(
        self: object, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()

        with app.app_context():
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-stale-active-checkout",
                    creator_bid="creator-stale-checkout",
                    product_bid="bill-product-plan-monthly-pro",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="manual",
                    provider_subscription_id="",
                    provider_customer_id="",
                    current_period_start_at=now - timedelta(days=60),
                    current_period_end_at=now - timedelta(days=30),
                    cancel_at_period_end=0,
                    next_product_bid="",
                    metadata_json={},
                    created_at=now - timedelta(days=60),
                    updated_at=now - timedelta(days=60),
                )
            )
            dao.db.session.commit()

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly-pro",
                "payment_provider": "stripe",
            },
            headers={"X-User-Id": "creator-stale-checkout"},
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["checkout_type"] == "subscription"
        with app.app_context():
            stale_subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-stale-active-checkout"
            ).one()
            new_subscription = (
                BillingSubscription.query.filter(
                    BillingSubscription.creator_bid == "creator-stale-checkout",
                    BillingSubscription.subscription_bid != "sub-stale-active-checkout",
                )
                .order_by(BillingSubscription.id.desc())
                .one()
            )
            order = BillingOrder.query.filter_by(
                creator_bid="creator-stale-checkout",
                subscription_bid=new_subscription.subscription_bid,
            ).one()

            assert stale_subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert new_subscription.status == BILLING_SUBSCRIPTION_STATUS_DRAFT
            assert order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_START

    def test_subscription_checkout_allows_paid_plan_after_stale_active_trial(
        self: object, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()

        with app.app_context():
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-stale-trial-checkout",
                    creator_bid="creator-stale-trial-checkout",
                    product_bid=BILLING_TRIAL_PRODUCT_BID,
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="manual",
                    provider_subscription_id="",
                    provider_customer_id="",
                    current_period_start_at=now - timedelta(days=45),
                    current_period_end_at=now - timedelta(days=30),
                    cancel_at_period_end=0,
                    next_product_bid="",
                    metadata_json={"trial_bootstrap": True},
                    created_at=now - timedelta(days=45),
                    updated_at=now - timedelta(days=45),
                )
            )
            dao.db.session.commit()

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly-pro",
                "payment_provider": "stripe",
            },
            headers={"X-User-Id": "creator-stale-trial-checkout"},
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["checkout_type"] == "subscription"
        with app.app_context():
            stale_trial = BillingSubscription.query.filter_by(
                subscription_bid="sub-stale-trial-checkout"
            ).one()
            new_subscription = (
                BillingSubscription.query.filter(
                    BillingSubscription.creator_bid == "creator-stale-trial-checkout",
                    BillingSubscription.subscription_bid != "sub-stale-trial-checkout",
                )
                .order_by(BillingSubscription.id.desc())
                .one()
            )
            order = BillingOrder.query.filter_by(
                creator_bid="creator-stale-trial-checkout",
                subscription_bid=new_subscription.subscription_bid,
            ).one()

            assert stale_trial.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert new_subscription.product_bid == "bill-product-plan-monthly-pro"
            assert new_subscription.status == BILLING_SUBSCRIPTION_STATUS_DRAFT
            assert order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_START

    def test_subscription_checkout_supports_daily_stripe_recurring_interval(
        self: object, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        with app.app_context():
            dao.db.session.add(
                BillingProduct(
                    product_bid="bill-product-plan-daily",
                    product_code="creator-plan-daily",
                    product_type=BILLING_PRODUCT_TYPE_PLAN,
                    billing_mode=BILLING_MODE_RECURRING,
                    billing_interval=BILLING_INTERVAL_DAY,
                    billing_interval_count=7,
                    display_name_i18n_key=(
                        "module.billing.catalog.plans.creatorMonthly.title"
                    ),
                    description_i18n_key=(
                        "module.billing.catalog.plans.creatorMonthly.description"
                    ),
                    currency="CNY",
                    price_amount=390,
                    credit_amount=Decimal("3.0000000000"),
                    allocation_interval=ALLOCATION_INTERVAL_PER_CYCLE,
                    auto_renew_enabled=1,
                    entitlement_payload=None,
                    metadata_json=None,
                    status=BILLING_PRODUCT_STATUS_ACTIVE,
                    sort_order=15,
                )
            )
            dao.db.session.commit()

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-daily",
                "payment_provider": "stripe",
            },
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        stripe_request = billing_write_client["stripe_requests"][-1]
        recurring = stripe_request["extra"]["line_items"][0]["price_data"]["recurring"]
        assert recurring["interval"] == "day"
        assert recurring["interval_count"] == 7

    def test_stripe_subscription_campaign_uses_first_invoice_discount_not_recurring_price(
        self: object,
        billing_write_client: object,
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()

        with app.app_context():
            dao.db.session.add(
                BillingCampaign(
                    campaign_bid="campaign-stripe-first-invoice",
                    name="Stripe first invoice campaign",
                    note="",
                    benefit_type=BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
                    discount_type=BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
                    discount_amount=200,
                    discount_percent=Decimal("0"),
                    bonus_credit_amount=Decimal("0"),
                    enabled=1,
                    start_at=now - timedelta(days=1),
                    end_at=now + timedelta(days=1),
                    created_user_bid="operator-1",
                    updated_user_bid="operator-1",
                )
            )
            dao.db.session.add(
                BillingCampaignProduct(
                    campaign_bid="campaign-stripe-first-invoice",
                    product_bid="bill-product-plan-monthly",
                    product_type=BILLING_PRODUCT_TYPE_PLAN,
                    discount_type=BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
                    discount_amount=200,
                    discount_percent=Decimal("0"),
                    campaign_price_amount=790,
                    bonus_credit_amount=Decimal("0"),
                )
            )
            dao.db.session.commit()

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["payable_amount"] == 790
        stripe_request = billing_write_client["stripe_requests"][-1]
        price_data = stripe_request["extra"]["line_items"][0]["price_data"]
        assert price_data["unit_amount"] == 990
        assert stripe_request["extra"]["subscription_one_time_discount_amount"] == 200

        with app.app_context():
            order = BillingOrder.query.filter_by(
                bill_order_bid=payload["data"]["bill_order_bid"]
            ).one()
            assert order.campaign_bid == "campaign-stripe-first-invoice"
            assert order.payable_amount == 790

    def test_subscription_checkout_rejects_lower_tier_plan_while_active(
        self: object, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()

        with app.app_context():
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-monthly-pro",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-monthly-pro",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="stripe",
                    provider_subscription_id="sub_provider_monthly_pro",
                    provider_customer_id="cus_provider_monthly_pro",
                    current_period_start_at=now - timedelta(days=5),
                    current_period_end_at=now + timedelta(days=25),
                    cancel_at_period_end=0,
                    next_product_bid="",
                    metadata_json={},
                    created_at=now - timedelta(days=5),
                    updated_at=now - timedelta(days=5),
                )
            )
            dao.db.session.commit()

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 7107
        assert (
            payload["message"]
            == "The current subscription is still active. Only upgrades to a higher-tier plan are allowed."
        )

        with app.app_context():
            assert (
                BillingSubscription.query.filter_by(creator_bid="creator-1").count()
                == 1
            )
            assert BillingOrder.query.filter_by(creator_bid="creator-1").count() == 0

    def test_subscription_checkout_allows_higher_tier_plan_while_active(
        self: object, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()

        with app.app_context():
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-monthly",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-monthly",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="stripe",
                    provider_subscription_id="sub_provider_monthly",
                    provider_customer_id="cus_provider_monthly",
                    current_period_start_at=now - timedelta(days=5),
                    current_period_end_at=now + timedelta(days=25),
                    cancel_at_period_end=0,
                    next_product_bid="",
                    metadata_json={},
                    created_at=now - timedelta(days=5),
                    updated_at=now - timedelta(days=5),
                )
            )
            dao.db.session.commit()

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly-pro",
                "payment_provider": "stripe",
            },
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["provider"] == "stripe"
        assert payload["data"]["status"] == "pending"

        with app.app_context():
            subscriptions = BillingSubscription.query.filter_by(
                creator_bid="creator-1"
            ).all()
            order = BillingOrder.query.filter_by(creator_bid="creator-1").one()

            assert len(subscriptions) == 1
            assert subscriptions[0].subscription_bid == "sub-monthly"
            assert order.subscription_bid == "sub-monthly"
            assert order.order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE

    def test_subscription_checkout_rejects_lower_tier_even_with_newer_draft(
        self: object, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()

        with app.app_context():
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-active-monthly-pro",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-monthly-pro",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="stripe",
                    provider_subscription_id="sub_provider_active_monthly_pro",
                    provider_customer_id="cus_provider_active_monthly_pro",
                    current_period_start_at=now - timedelta(days=5),
                    current_period_end_at=now + timedelta(days=25),
                    cancel_at_period_end=0,
                    next_product_bid="",
                    metadata_json={},
                    created_at=now - timedelta(days=5),
                    updated_at=now - timedelta(days=5),
                )
            )
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-draft-newer",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-monthly",
                    status=BILLING_SUBSCRIPTION_STATUS_DRAFT,
                    billing_provider="stripe",
                    provider_subscription_id="",
                    provider_customer_id="",
                    current_period_start_at=None,
                    current_period_end_at=None,
                    cancel_at_period_end=0,
                    next_product_bid="",
                    metadata_json={"checkout_started": True},
                    created_at=now - timedelta(hours=1),
                    updated_at=now - timedelta(hours=1),
                )
            )
            dao.db.session.commit()

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 7107
        assert (
            payload["message"]
            == "The current subscription is still active. Only upgrades to a higher-tier plan are allowed."
        )

    def test_subscription_checkout_rejects_lower_tier_against_paid_plan_when_trial_overlaps(
        self: object, billing_write_client: object
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = now_utc()

        with app.app_context():
            dao.db.session.add_all(
                [
                    BillingSubscription(
                        subscription_bid="sub-trial-overlap",
                        creator_bid="creator-1",
                        product_bid=BILLING_TRIAL_PRODUCT_BID,
                        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                        billing_provider="manual",
                        provider_subscription_id="",
                        provider_customer_id="",
                        current_period_start_at=now - timedelta(days=1),
                        current_period_end_at=now + timedelta(days=14),
                        cancel_at_period_end=0,
                        next_product_bid="",
                        metadata_json={"trial": True},
                        created_at=now - timedelta(days=1),
                        updated_at=now - timedelta(days=1),
                    ),
                    BillingSubscription(
                        subscription_bid="sub-paid-overlap-pro",
                        creator_bid="creator-1",
                        product_bid="bill-product-plan-monthly-pro",
                        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                        billing_provider="stripe",
                        provider_subscription_id="sub_provider_paid_overlap_pro",
                        provider_customer_id="cus_provider_paid_overlap_pro",
                        current_period_start_at=now - timedelta(hours=6),
                        current_period_end_at=now + timedelta(days=1),
                        cancel_at_period_end=0,
                        next_product_bid="",
                        metadata_json={},
                        created_at=now - timedelta(hours=6),
                        updated_at=now - timedelta(hours=6),
                    ),
                ]
            )
            dao.db.session.commit()

        response = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 7107
        assert (
            payload["message"]
            == "The current subscription is still active. Only upgrades to a higher-tier plan are allowed."
        )
