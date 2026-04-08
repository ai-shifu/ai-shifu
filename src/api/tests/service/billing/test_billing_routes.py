from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from flask import Flask, jsonify, request
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_PRODUCT_SEEDS,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_GIFT,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingEntitlement,
    BillingProduct,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.routes import register_billing_routes
from flaskr.service.common.models import AppException
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD


def _seed_products() -> list[BillingProduct]:
    items: list[BillingProduct] = []
    for seed in BILLING_PRODUCT_SEEDS:
        payload = dict(seed)
        payload["metadata_json"] = payload.pop("metadata", None)
        if payload["product_bid"] == "billing-product-plan-yearly":
            payload["entitlement_payload"] = {
                "branding_enabled": True,
                "custom_domain_enabled": True,
                "priority_class": "vip",
                "max_concurrency": "8",
                "analytics_tier": "enterprise",
                "support_tier": "priority",
                "feature_payload": {"beta_reports": True},
            }
        items.append(BillingProduct(**payload))
    return items


@pytest.fixture
def billing_test_client():
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )

    dao.db.init_app(app)

    @app.errorhandler(AppException)
    def _handle_app_exception(error: AppException):
        response = jsonify({"code": error.code, "message": error.message})
        response.status_code = 200
        return response

    @app.before_request
    def _inject_request_user() -> None:
        request.user = SimpleNamespace(
            user_id=request.headers.get("X-User-Id", "creator-1"),
            language="en-US",
            is_creator=request.headers.get("X-Creator", "1") == "1",
        )

    register_billing_routes(app=app)

    with app.app_context():
        dao.db.create_all()

        dao.db.session.add_all(_seed_products())

        wallet = CreditWallet(
            wallet_bid="wallet-1",
            creator_bid="creator-1",
            available_credits=Decimal("120.5000000000"),
            reserved_credits=Decimal("10.0000000000"),
            lifetime_granted_credits=Decimal("500.0000000000"),
            lifetime_consumed_credits=Decimal("379.5000000000"),
            created_at=datetime(2026, 4, 1, 9, 0, 0),
            updated_at=datetime(2026, 4, 6, 10, 0, 0),
        )
        other_wallet = CreditWallet(
            wallet_bid="wallet-2",
            creator_bid="creator-2",
            available_credits=Decimal("999.0000000000"),
            reserved_credits=Decimal("0"),
            lifetime_granted_credits=Decimal("999.0000000000"),
            lifetime_consumed_credits=Decimal("0"),
            created_at=datetime(2026, 4, 1, 9, 0, 0),
            updated_at=datetime(2026, 4, 6, 10, 0, 0),
        )
        dao.db.session.add_all([wallet, other_wallet])

        subscription = BillingSubscription(
            subscription_bid="sub-1",
            creator_bid="creator-1",
            product_bid="billing-product-plan-monthly",
            status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
            billing_provider="stripe",
            provider_subscription_id="sub_stripe_1",
            provider_customer_id="cus_stripe_1",
            current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
            current_period_end_at=datetime(2026, 5, 1, 0, 0, 0),
            grace_period_end_at=None,
            cancel_at_period_end=1,
            next_product_bid="",
            last_renewed_at=datetime(2026, 4, 1, 0, 0, 0),
            last_failed_at=None,
            metadata_json={"source": "seed"},
            created_at=datetime(2026, 4, 1, 0, 0, 0),
            updated_at=datetime(2026, 4, 1, 0, 0, 0),
        )
        dao.db.session.add(subscription)
        dao.db.session.add(
            BillingSubscription(
                subscription_bid="sub-creator-3",
                creator_bid="creator-3",
                product_bid="billing-product-plan-yearly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="sub_stripe_3",
                provider_customer_id="cus_stripe_3",
                current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
                current_period_end_at=datetime(2026, 5, 1, 0, 0, 0),
                cancel_at_period_end=0,
                last_renewed_at=datetime(2026, 4, 1, 0, 0, 0),
                created_at=datetime(2026, 4, 1, 0, 0, 0),
                updated_at=datetime(2026, 4, 1, 0, 0, 0),
            )
        )
        dao.db.session.add(
            BillingEntitlement(
                entitlement_bid="entitlement-1",
                creator_bid="creator-1",
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="sub-1",
                branding_enabled=1,
                custom_domain_enabled=1,
                priority_class=7702,
                max_concurrency=3,
                analytics_tier=7712,
                support_tier=7722,
                feature_payload={"custom_css": True},
                effective_from=datetime(2026, 4, 1, 0, 0, 0),
                effective_to=None,
                created_at=datetime(2026, 4, 1, 0, 0, 0),
                updated_at=datetime(2026, 4, 1, 0, 0, 0),
            )
        )

        dao.db.session.add_all(
            [
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-free",
                    wallet_bid="wallet-1",
                    creator_bid="creator-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
                    source_type=CREDIT_SOURCE_TYPE_GIFT,
                    source_bid="gift-1",
                    priority=1,
                    original_credits=Decimal("20.0000000000"),
                    available_credits=Decimal("20.0000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 1, 0, 0, 0),
                    effective_to=datetime(2026, 4, 10, 0, 0, 0),
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    created_at=datetime(2026, 4, 1, 0, 0, 0),
                    updated_at=datetime(2026, 4, 1, 0, 0, 0),
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-subscription",
                    wallet_bid="wallet-1",
                    creator_bid="creator-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                    source_bid="sub-1",
                    priority=2,
                    original_credits=Decimal("80.5000000000"),
                    available_credits=Decimal("80.5000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 1, 0, 0, 0),
                    effective_to=datetime(2026, 5, 1, 0, 0, 0),
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    created_at=datetime(2026, 4, 2, 0, 0, 0),
                    updated_at=datetime(2026, 4, 2, 0, 0, 0),
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-topup",
                    wallet_bid="wallet-1",
                    creator_bid="creator-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
                    source_type=CREDIT_SOURCE_TYPE_TOPUP,
                    source_bid="topup-1",
                    priority=3,
                    original_credits=Decimal("20.0000000000"),
                    available_credits=Decimal("20.0000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 3, 0, 0, 0),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    created_at=datetime(2026, 4, 3, 0, 0, 0),
                    updated_at=datetime(2026, 4, 3, 0, 0, 0),
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-other",
                    wallet_bid="wallet-2",
                    creator_bid="creator-2",
                    bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
                    source_type=CREDIT_SOURCE_TYPE_GIFT,
                    source_bid="gift-other",
                    priority=1,
                    original_credits=Decimal("999.0000000000"),
                    available_credits=Decimal("999.0000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 1, 0, 0, 0),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    created_at=datetime(2026, 4, 1, 0, 0, 0),
                    updated_at=datetime(2026, 4, 1, 0, 0, 0),
                ),
            ]
        )

        dao.db.session.add_all(
            [
                CreditLedgerEntry(
                    ledger_bid="ledger-grant",
                    creator_bid="creator-1",
                    wallet_bid="wallet-1",
                    wallet_bucket_bid="bucket-subscription",
                    entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                    source_bid="sub-1",
                    idempotency_key="grant-sub-1",
                    amount=Decimal("80.5000000000"),
                    balance_after=Decimal("100.5000000000"),
                    expires_at=datetime(2026, 5, 1, 0, 0, 0),
                    consumable_from=datetime(2026, 4, 1, 0, 0, 0),
                    metadata_json={"provider": "stripe"},
                    created_at=datetime(2026, 4, 5, 10, 0, 0),
                    updated_at=datetime(2026, 4, 5, 10, 0, 0),
                ),
                CreditLedgerEntry(
                    ledger_bid="ledger-consume",
                    creator_bid="creator-1",
                    wallet_bid="wallet-1",
                    wallet_bucket_bid="bucket-subscription",
                    entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
                    source_type=CREDIT_SOURCE_TYPE_USAGE,
                    source_bid="usage-1",
                    idempotency_key="usage-1-bucket-subscription",
                    amount=Decimal("-2.5000000000"),
                    balance_after=Decimal("98.0000000000"),
                    expires_at=None,
                    consumable_from=None,
                    metadata_json={
                        "usage_bid": "usage-1",
                        "usage_scene": BILL_USAGE_SCENE_PROD,
                        "metric_breakdown": [
                            {
                                "billing_metric": "llm_output_tokens",
                                "raw_amount": 1234,
                                "unit_size": 1000,
                                "credits_per_unit": 1.25,
                                "rounding_mode": "ceil",
                                "consumed_credits": 2.5,
                            }
                        ],
                    },
                    created_at=datetime(2026, 4, 6, 10, 0, 0),
                    updated_at=datetime(2026, 4, 6, 10, 0, 0),
                ),
                CreditLedgerEntry(
                    ledger_bid="ledger-other",
                    creator_bid="creator-2",
                    wallet_bid="wallet-2",
                    wallet_bucket_bid="bucket-other",
                    entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                    source_type=CREDIT_SOURCE_TYPE_GIFT,
                    source_bid="gift-other",
                    idempotency_key="gift-other",
                    amount=Decimal("999.0000000000"),
                    balance_after=Decimal("999.0000000000"),
                    expires_at=None,
                    consumable_from=None,
                    metadata_json={},
                    created_at=datetime(2026, 4, 6, 10, 0, 0),
                    updated_at=datetime(2026, 4, 6, 10, 0, 0),
                ),
            ]
        )

        dao.db.session.add_all(
            [
                BillingOrder(
                    billing_order_bid="order-1",
                    creator_bid="creator-1",
                    order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                    product_bid="billing-product-plan-monthly",
                    subscription_bid="sub-1",
                    currency="CNY",
                    payable_amount=9900,
                    paid_amount=0,
                    payment_provider="stripe",
                    channel="card",
                    provider_reference_id="cs_test_1",
                    status=BILLING_ORDER_STATUS_FAILED,
                    paid_at=None,
                    failed_at=datetime(2026, 4, 5, 12, 5, 0),
                    refunded_at=None,
                    failure_code="card_declined",
                    failure_message="declined",
                    metadata_json={"event_type": "checkout.session.completed"},
                    created_at=datetime(2026, 4, 5, 12, 0, 0),
                    updated_at=datetime(2026, 4, 5, 12, 5, 0),
                ),
                BillingOrder(
                    billing_order_bid="order-2",
                    creator_bid="creator-1",
                    order_type=BILLING_ORDER_TYPE_TOPUP,
                    product_bid="billing-product-topup-small",
                    subscription_bid="",
                    currency="CNY",
                    payable_amount=19900,
                    paid_amount=19900,
                    payment_provider="pingxx",
                    channel="alipay_qr",
                    provider_reference_id="ch_test_2",
                    status=BILLING_ORDER_STATUS_PAID,
                    paid_at=datetime(2026, 4, 6, 11, 5, 0),
                    failed_at=None,
                    refunded_at=None,
                    failure_code="",
                    failure_message="",
                    metadata_json={"event_type": "charge.succeeded"},
                    created_at=datetime(2026, 4, 6, 11, 0, 0),
                    updated_at=datetime(2026, 4, 6, 11, 5, 0),
                ),
                BillingOrder(
                    billing_order_bid="order-other",
                    creator_bid="creator-2",
                    order_type=BILLING_ORDER_TYPE_TOPUP,
                    product_bid="billing-product-topup-large",
                    subscription_bid="",
                    currency="CNY",
                    payable_amount=69900,
                    paid_amount=69900,
                    payment_provider="stripe",
                    channel="card",
                    provider_reference_id="cs_test_other",
                    status=BILLING_ORDER_STATUS_PAID,
                    paid_at=datetime(2026, 4, 6, 11, 5, 0),
                    failed_at=None,
                    refunded_at=None,
                    failure_code="",
                    failure_message="",
                    metadata_json={},
                    created_at=datetime(2026, 4, 6, 11, 0, 0),
                    updated_at=datetime(2026, 4, 6, 11, 5, 0),
                ),
            ]
        )

        dao.db.session.commit()

        with app.test_client() as client:
            yield client

        dao.db.session.remove()
        dao.db.drop_all()


class TestBillingRoutes:
    def test_billing_bootstrap_route_returns_design_manifest(
        self, billing_test_client
    ) -> None:
        response = billing_test_client.get("/api/billing")
        payload = response.get_json(force=True)

        assert response.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["service"] == "billing"
        assert payload["data"]["status"] == "bootstrap"
        assert payload["data"]["path_prefix"] == "/api/billing"
        assert {
            "method": "GET",
            "path": "/api/billing/catalog",
        } in payload["data"]["creator_routes"]
        assert {
            "method": "GET",
            "path": "/api/billing/entitlements",
        } in payload["data"]["creator_routes"]
        assert {
            "method": "POST",
            "path": "/api/billing/orders/{billing_order_bid}/sync",
        } in payload["data"]["creator_routes"]

    def test_catalog_overview_and_wallet_buckets_follow_design_projection(
        self, billing_test_client
    ) -> None:
        catalog_response = billing_test_client.get("/api/billing/catalog")
        overview_response = billing_test_client.get("/api/billing/overview")
        bucket_response = billing_test_client.get("/api/billing/wallet-buckets")

        catalog_payload = catalog_response.get_json(force=True)
        overview_payload = overview_response.get_json(force=True)
        bucket_payload = bucket_response.get_json(force=True)

        assert catalog_payload["code"] == 0
        assert len(catalog_payload["data"]["plans"]) == 2
        assert len(catalog_payload["data"]["topups"]) == 2
        assert catalog_payload["data"]["plans"][1]["status_badge_key"] == (
            "module.billing.catalog.badges.recommended"
        )

        assert overview_payload["code"] == 0
        assert overview_payload["data"]["creator_bid"] == "creator-1"
        assert overview_payload["data"]["wallet"]["available_credits"] == 120.5
        assert overview_payload["data"]["subscription"]["subscription_bid"] == "sub-1"
        assert overview_payload["data"]["subscription"]["status"] == "active"
        assert overview_payload["data"]["billing_alerts"][0]["code"] == (
            "subscription_cancel_scheduled"
        )

        assert bucket_payload["code"] == 0
        assert [item["wallet_bucket_bid"] for item in bucket_payload["data"]] == [
            "bucket-free",
            "bucket-subscription",
            "bucket-topup",
        ]
        assert bucket_payload["data"][0]["category"] == "free"
        assert bucket_payload["data"][2]["source_bid"] == "topup-1"

    def test_entitlements_route_returns_snapshot_then_product_fallback(
        self, billing_test_client
    ) -> None:
        snapshot_response = billing_test_client.get("/api/billing/entitlements")
        fallback_response = billing_test_client.get(
            "/api/billing/entitlements",
            headers={"X-User-Id": "creator-3"},
        )
        default_response = billing_test_client.get(
            "/api/billing/entitlements",
            headers={"X-User-Id": "creator-4"},
        )

        snapshot_payload = snapshot_response.get_json(force=True)
        fallback_payload = fallback_response.get_json(force=True)
        default_payload = default_response.get_json(force=True)

        assert snapshot_payload["code"] == 0
        assert snapshot_payload["data"] == {
            "branding_enabled": True,
            "custom_domain_enabled": True,
            "priority_class": "priority",
            "max_concurrency": 3,
            "analytics_tier": "advanced",
            "support_tier": "business_hours",
        }

        assert fallback_payload["code"] == 0
        assert fallback_payload["data"] == {
            "branding_enabled": True,
            "custom_domain_enabled": True,
            "priority_class": "vip",
            "max_concurrency": 8,
            "analytics_tier": "enterprise",
            "support_tier": "priority",
        }

        assert default_payload["code"] == 0
        assert default_payload["data"] == {
            "branding_enabled": False,
            "custom_domain_enabled": False,
            "priority_class": "standard",
            "max_concurrency": 1,
            "analytics_tier": "basic",
            "support_tier": "self_serve",
        }

    def test_ledger_and_orders_support_pagination_and_creator_isolation(
        self, billing_test_client
    ) -> None:
        ledger_response = billing_test_client.get(
            "/api/billing/ledger?page_index=1&page_size=1"
        )
        orders_response = billing_test_client.get(
            "/api/billing/orders?page_index=1&page_size=1"
        )

        ledger_payload = ledger_response.get_json(force=True)
        orders_payload = orders_response.get_json(force=True)

        assert ledger_payload["code"] == 0
        assert ledger_payload["data"]["total"] == 2
        assert ledger_payload["data"]["page_count"] == 2
        assert ledger_payload["data"]["items"][0]["ledger_bid"] == "ledger-consume"
        assert (
            ledger_payload["data"]["items"][0]["metadata"]["usage_scene"]
            == "production"
        )
        assert (
            ledger_payload["data"]["items"][0]["metadata"]["metric_breakdown"][0][
                "consumed_credits"
            ]
            == 2.5
        )

        assert orders_payload["code"] == 0
        assert orders_payload["data"]["total"] == 2
        assert orders_payload["data"]["items"][0]["billing_order_bid"] == "order-2"
        assert orders_payload["data"]["items"][0]["payment_mode"] == "one_time"
        assert orders_payload["data"]["items"][0]["status"] == "paid"

    def test_billing_order_detail_requires_current_creator(
        self, billing_test_client
    ) -> None:
        detail_response = billing_test_client.get("/api/billing/orders/order-1")
        payload = detail_response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["billing_order_bid"] == "order-1"
        assert payload["data"]["payment_mode"] == "subscription"
        assert payload["data"]["failure_code"] == "card_declined"
        assert payload["data"]["metadata"]["event_type"] == (
            "checkout.session.completed"
        )
        assert payload["data"]["failed_at"] is not None

        forbidden = billing_test_client.get(
            "/api/billing/orders/order-1",
            headers={"X-User-Id": "creator-2"},
        )
        forbidden_payload = forbidden.get_json(force=True)
        assert forbidden_payload["code"] != 0

    def test_billing_routes_require_creator(self, billing_test_client) -> None:
        response = billing_test_client.get(
            "/api/billing/catalog",
            headers={"X-Creator": "0"},
        )
        payload = response.get_json(force=True)

        assert response.status_code == 200
        assert payload["code"] != 0
