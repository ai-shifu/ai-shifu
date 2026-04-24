from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, jsonify, request
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    ALLOCATION_INTERVAL_PER_CYCLE,
    BILLING_INTERVAL_DAY,
    BILLING_METRIC_LLM_INPUT_TOKENS,
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    BILLING_MODE_RECURRING,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
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
    BillingDailyLedgerSummary,
    BillingDailyUsageMetric,
    BillingOrder,
    BillingEntitlement,
    BillingProduct,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.dtos import (
    BillingCatalogDTO,
    BillingLedgerPageDTO,
    BillingOverviewDTO,
    BillingRouteBootstrapDTO,
    BillingWalletBucketListDTO,
)
from flaskr.service.billing.capabilities import build_billing_route_bootstrap
from flaskr.service.billing.read_models import (
    build_billing_catalog,
    build_billing_ledger_page,
    build_billing_overview,
    build_billing_wallet_buckets,
)
from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
)
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.models import UserInfo as UserEntity
from tests.common.fixtures.bill_products import build_bill_products
from tests.service.billing.route_loader import (
    load_billing_routes_module,
    load_register_billing_routes,
)

register_billing_routes = load_register_billing_routes()
billing_routes_module = load_billing_routes_module()


def _seed_products_with_yearly_entitlements():
    return build_bill_products(
        overrides_by_bid={
            "bill-product-plan-yearly": {
                "entitlement_payload": {
                    "branding_enabled": True,
                    "custom_domain_enabled": True,
                    "priority_class": "vip",
                    "analytics_tier": "enterprise",
                    "support_tier": "priority",
                    "feature_payload": {"beta_reports": True},
                }
            }
        }
    )


@pytest.fixture
def billing_test_client(monkeypatch):
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        REDIS_KEY_PREFIX="billing-routes-test:",
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

    monkeypatch.setattr(
        billing_routes_module,
        "is_billing_enabled",
        lambda: True,
    )

    register_billing_routes(app=app)

    with app.app_context():
        dao.db.create_all()

        dao.db.session.add_all(_seed_products_with_yearly_entitlements())
        dao.db.session.add_all(
            [
                DraftShifu(
                    shifu_bid="shifu-1",
                    title="Draft Course 1",
                    created_user_bid="creator-1",
                    updated_user_bid="creator-1",
                ),
                PublishedShifu(
                    shifu_bid="shifu-1",
                    title="Published Course 1",
                    created_user_bid="creator-1",
                    updated_user_bid="creator-1",
                ),
                UserEntity(
                    user_bid="learner-1",
                    user_identify="learner@example.com",
                    nickname="Learner 1",
                    is_creator=0,
                    is_operator=0,
                ),
            ]
        )

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
            product_bid="bill-product-plan-monthly",
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
                product_bid="bill-product-plan-yearly",
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
                BillUsageRecord(
                    usage_bid="usage-1",
                    user_bid="learner-1",
                    shifu_bid="shifu-1",
                    usage_type=BILL_USAGE_TYPE_LLM,
                    usage_scene=BILL_USAGE_SCENE_PROD,
                    provider="openai",
                    model="gpt-4o-mini",
                    input=0,
                    input_cache=0,
                    output=1234,
                    total=1234,
                    created_at=datetime(2026, 4, 6, 10, 0, 0),
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
                    bill_order_bid="order-1",
                    creator_bid="creator-1",
                    order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                    product_bid="bill-product-plan-monthly",
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
                    bill_order_bid="order-2",
                    creator_bid="creator-1",
                    order_type=BILLING_ORDER_TYPE_TOPUP,
                    product_bid="bill-product-topup-small",
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
                    bill_order_bid="order-other",
                    creator_bid="creator-2",
                    order_type=BILLING_ORDER_TYPE_TOPUP,
                    product_bid="bill-product-topup-large",
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

        dao.db.session.add_all(
            [
                BillingDailyUsageMetric(
                    daily_usage_metric_bid="daily-usage-1",
                    stat_date="2026-04-06",
                    creator_bid="creator-1",
                    shifu_bid="shifu-1",
                    usage_scene=BILL_USAGE_SCENE_PROD,
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-4o-mini",
                    billing_metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    raw_amount=1234,
                    record_count=3,
                    consumed_credits=Decimal("4.5000000000"),
                    window_started_at=datetime(2026, 4, 6, 0, 0, 0),
                    window_ended_at=datetime(2026, 4, 7, 0, 0, 0),
                    created_at=datetime(2026, 4, 7, 0, 0, 0),
                    updated_at=datetime(2026, 4, 7, 0, 0, 0),
                ),
                BillingDailyUsageMetric(
                    daily_usage_metric_bid="daily-usage-2",
                    stat_date="2026-04-05",
                    creator_bid="creator-1",
                    shifu_bid="shifu-1",
                    usage_scene=BILL_USAGE_SCENE_PROD,
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-4o-mini",
                    billing_metric=BILLING_METRIC_LLM_INPUT_TOKENS,
                    raw_amount=2048,
                    record_count=5,
                    consumed_credits=Decimal("3.2500000000"),
                    window_started_at=datetime(2026, 4, 5, 0, 0, 0),
                    window_ended_at=datetime(2026, 4, 6, 0, 0, 0),
                    created_at=datetime(2026, 4, 6, 0, 0, 0),
                    updated_at=datetime(2026, 4, 6, 0, 0, 0),
                ),
                BillingDailyUsageMetric(
                    daily_usage_metric_bid="daily-usage-other",
                    stat_date="2026-04-06",
                    creator_bid="creator-2",
                    shifu_bid="shifu-2",
                    usage_scene=BILL_USAGE_SCENE_PROD,
                    usage_type=BILL_USAGE_TYPE_LLM,
                    provider="openai",
                    model="gpt-4o-mini",
                    billing_metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
                    raw_amount=999,
                    record_count=1,
                    consumed_credits=Decimal("9.0000000000"),
                    window_started_at=datetime(2026, 4, 6, 0, 0, 0),
                    window_ended_at=datetime(2026, 4, 7, 0, 0, 0),
                    created_at=datetime(2026, 4, 7, 0, 0, 0),
                    updated_at=datetime(2026, 4, 7, 0, 0, 0),
                ),
                BillingDailyLedgerSummary(
                    daily_ledger_summary_bid="daily-ledger-1",
                    stat_date="2026-04-06",
                    creator_bid="creator-1",
                    entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
                    source_type=CREDIT_SOURCE_TYPE_USAGE,
                    amount=Decimal("-4.5000000000"),
                    entry_count=3,
                    window_started_at=datetime(2026, 4, 6, 0, 0, 0),
                    window_ended_at=datetime(2026, 4, 7, 0, 0, 0),
                    created_at=datetime(2026, 4, 7, 0, 0, 0),
                    updated_at=datetime(2026, 4, 7, 0, 0, 0),
                ),
                BillingDailyLedgerSummary(
                    daily_ledger_summary_bid="daily-ledger-2",
                    stat_date="2026-04-05",
                    creator_bid="creator-1",
                    entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                    source_type=CREDIT_SOURCE_TYPE_TOPUP,
                    amount=Decimal("20.0000000000"),
                    entry_count=1,
                    window_started_at=datetime(2026, 4, 5, 0, 0, 0),
                    window_ended_at=datetime(2026, 4, 6, 0, 0, 0),
                    created_at=datetime(2026, 4, 6, 0, 0, 0),
                    updated_at=datetime(2026, 4, 6, 0, 0, 0),
                ),
                BillingDailyLedgerSummary(
                    daily_ledger_summary_bid="daily-ledger-other",
                    stat_date="2026-04-06",
                    creator_bid="creator-2",
                    entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                    source_type=CREDIT_SOURCE_TYPE_GIFT,
                    amount=Decimal("99.0000000000"),
                    entry_count=1,
                    window_started_at=datetime(2026, 4, 6, 0, 0, 0),
                    window_ended_at=datetime(2026, 4, 7, 0, 0, 0),
                    created_at=datetime(2026, 4, 7, 0, 0, 0),
                    updated_at=datetime(2026, 4, 7, 0, 0, 0),
                ),
            ]
        )

        dao.db.session.commit()

        with app.test_client() as client:
            yield client

        dao.db.session.remove()
        dao.db.drop_all()


class TestBillingRoutes:
    def test_billing_routes_reject_requests_when_feature_disabled(
        self, billing_test_client, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            billing_routes_module,
            "is_billing_enabled",
            lambda: False,
        )

        response = billing_test_client.get("/api/billing")
        payload = response.get_json(force=True)

        assert response.status_code == 200
        assert payload["code"] == ERROR_CODE["server.billing.disabled"]

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
            "method": "POST",
            "path": "/api/billing/orders/{bill_order_bid}/sync",
        } in payload["data"]["creator_routes"]
        assert {
            "method": "POST",
            "path": "/api/billing/orders/{bill_order_bid}/checkout",
        } in payload["data"]["creator_routes"]
        assert {
            "method": "GET",
            "path": "/api/admin/billing/entitlements",
        } in payload["data"]["admin_routes"]
        assert {
            "method": "GET",
            "path": "/api/admin/billing/domain-audits",
        } in payload["data"]["admin_routes"]
        assert {
            "method": "GET",
            "path": "/api/admin/billing/reports/usage-daily",
        } in payload["data"]["admin_routes"]
        assert {
            "method": "GET",
            "path": "/api/admin/billing/reports/ledger-daily",
        } in payload["data"]["admin_routes"]

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
        assert len(catalog_payload["data"]["plans"]) == 5
        assert len(catalog_payload["data"]["topups"]) == 4
        plan_map = {
            item["product_bid"]: item for item in catalog_payload["data"]["plans"]
        }
        topup_map = {
            item["product_bid"]: item for item in catalog_payload["data"]["topups"]
        }
        assert plan_map["bill-product-plan-monthly-pro"]["status_badge_key"] == (
            "module.billing.catalog.badges.recommended"
        )
        assert (
            plan_map["bill-product-plan-yearly-premium"]["status_badge_key"]
            == "module.billing.catalog.badges.bestValue"
        )
        assert topup_map["bill-product-topup-xlarge"]["status_badge_key"] == (
            "module.billing.catalog.badges.bestValue"
        )

        assert overview_payload["code"] == 0
        assert overview_payload["data"]["creator_bid"] == "creator-1"
        assert overview_payload["data"]["wallet"]["available_credits"] == 120.5
        assert overview_payload["data"]["subscription"]["subscription_bid"] == "sub-1"
        assert overview_payload["data"]["subscription"]["status"] == "active"
        assert overview_payload["data"]["billing_alerts"][0]["code"] == (
            "subscription_cancel_scheduled"
        )
        assert overview_payload["data"]["trial_offer"] == {
            "enabled": True,
            "status": "ineligible",
            "product_bid": "bill-product-plan-trial",
            "product_code": "creator-plan-trial",
            "display_name": "module.billing.package.free.title",
            "description": "module.billing.package.free.description",
            "currency": "CNY",
            "price_amount": 0,
            "credit_amount": 100,
            "highlights": [
                "module.billing.package.features.free.publish",
                "module.billing.package.features.free.preview",
            ],
            "valid_days": 15,
            "starts_on_first_grant": True,
            "granted_at": None,
            "expires_at": None,
            "welcome_dialog_acknowledged_at": None,
        }

        assert bucket_payload["code"] == 0
        assert [
            item["wallet_bucket_bid"] for item in bucket_payload["data"]["items"]
        ] == [
            "bucket-free",
            "bucket-subscription",
            "bucket-topup",
        ]
        assert bucket_payload["data"]["items"][0]["category"] == "subscription"
        assert bucket_payload["data"]["items"][0]["priority"] == 20
        assert bucket_payload["data"]["items"][2]["source_bid"] == "topup-1"

    def test_catalog_serializes_daily_plan_interval_without_month_fallback(
        self, billing_test_client
    ) -> None:
        app = billing_test_client.application
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
                    metadata_json={
                        "highlights": [
                            "module.billing.package.features.daily.publish",
                            "module.billing.package.features.daily.preview",
                        ]
                    },
                    status=BILLING_PRODUCT_STATUS_ACTIVE,
                    sort_order=15,
                )
            )
            dao.db.session.commit()

        payload = billing_test_client.get("/api/billing/catalog").get_json(force=True)
        daily_plan = next(
            item
            for item in payload["data"]["plans"]
            if item["product_bid"] == "bill-product-plan-daily"
        )

        assert daily_plan["billing_interval"] == "day"
        assert daily_plan["billing_interval_count"] == 7

    def test_overview_and_wallet_buckets_respect_request_timezone_and_fallback(
        self, billing_test_client
    ) -> None:
        try:
            target_tz = ZoneInfo("Asia/Shanghai")
        except ZoneInfoNotFoundError:
            pytest.skip("Asia/Shanghai timezone is unavailable in test environment")

        app_tz = ZoneInfo(billing_test_client.application.config.get("TZ", "UTC"))

        overview_response = billing_test_client.get(
            "/api/billing/overview?timezone=Asia/Shanghai"
        )
        timezone_bucket_response = billing_test_client.get(
            "/api/billing/wallet-buckets?timezone=Asia/Shanghai"
        )
        default_bucket_response = billing_test_client.get("/api/billing/wallet-buckets")

        overview_payload = overview_response.get_json(force=True)
        timezone_bucket_payload = timezone_bucket_response.get_json(force=True)
        default_bucket_payload = default_bucket_response.get_json(force=True)

        expected_period_end = datetime(2026, 5, 1, 0, 0, 0, tzinfo=app_tz).astimezone(
            target_tz
        )
        expected_bucket_start = datetime(2026, 4, 1, 0, 0, 0, tzinfo=app_tz).astimezone(
            target_tz
        )

        assert overview_payload["code"] == 0
        assert (
            overview_payload["data"]["subscription"]["current_period_end_at"]
            == expected_period_end.isoformat()
        )

        assert timezone_bucket_payload["code"] == 0
        assert (
            timezone_bucket_payload["data"]["items"][0]["effective_from"]
            == expected_bucket_start.isoformat()
        )

        assert default_bucket_payload["code"] == 0
        assert (
            default_bucket_payload["data"]["items"][0]["effective_from"]
            == "2026-04-01T00:00:00+00:00"
        )

    def test_wallet_buckets_return_runtime_expired_status_before_expire_task_runs(
        self,
        billing_test_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class _FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                current = cls(2026, 5, 1, 12, 0, 0)
                if tz is not None:
                    return current.replace(tzinfo=tz)
                return current

        monkeypatch.setattr(
            "flaskr.service.billing.serializers.datetime",
            _FixedDateTime,
        )

        payload = billing_test_client.get("/api/billing/wallet-buckets").get_json(
            force=True
        )

        bucket_map = {
            item["wallet_bucket_bid"]: item for item in payload["data"]["items"]
        }

        assert payload["code"] == 0
        assert bucket_map["bucket-free"]["status"] == "expired"
        assert bucket_map["bucket-subscription"]["status"] == "expired"
        assert bucket_map["bucket-topup"]["status"] == "active"

    def test_billing_public_builders_return_dto_instances(
        self,
        billing_test_client,
    ) -> None:
        app = billing_test_client.application

        results = {
            "bootstrap": build_billing_route_bootstrap("/api/billing"),
            "catalog": build_billing_catalog(app),
            "overview": build_billing_overview(app, "creator-1"),
            "wallet_buckets": build_billing_wallet_buckets(app, "creator-1"),
            "ledger": build_billing_ledger_page(app, "creator-1"),
        }

        assert isinstance(results["bootstrap"], BillingRouteBootstrapDTO)
        assert isinstance(results["catalog"], BillingCatalogDTO)
        assert isinstance(results["overview"], BillingOverviewDTO)
        assert isinstance(results["wallet_buckets"], BillingWalletBucketListDTO)
        assert isinstance(results["ledger"], BillingLedgerPageDTO)

        for value in results.values():
            assert not isinstance(value, dict)
            assert not isinstance(value, list)
            assert isinstance(value.__json__(), dict)

    def test_billing_routes_module_uses_shared_common_response(self) -> None:
        from flaskr.route.common import make_common_response

        assert getattr(billing_routes_module, "_make_common_response", None) is None
        assert billing_routes_module.make_common_response.__name__ == (
            make_common_response.__name__
        )
        assert billing_routes_module.make_common_response.__module__ == (
            make_common_response.__module__
        )

    def test_admin_entitlements_and_reports_routes_return_cross_creator_rows(
        self, billing_test_client
    ) -> None:
        entitlements_response = billing_test_client.get(
            "/api/admin/billing/entitlements?page_index=1&page_size=10"
        )
        usage_response = billing_test_client.get(
            "/api/admin/billing/reports/usage-daily?page_index=1&page_size=10&creator_bid=creator-1&date_from=2026-04-06"
        )
        ledger_response = billing_test_client.get(
            "/api/admin/billing/reports/ledger-daily?page_index=1&page_size=10&creator_bid=creator-1&date_from=2026-04-06"
        )

        entitlements_payload = entitlements_response.get_json(force=True)
        usage_payload = usage_response.get_json(force=True)
        ledger_payload = ledger_response.get_json(force=True)

        assert entitlements_payload["code"] == 0
        assert entitlements_payload["data"]["total"] == 3
        assert entitlements_payload["data"]["items"][0] == {
            "creator_bid": "creator-1",
            "source_kind": "snapshot",
            "source_type": "subscription",
            "source_bid": "sub-1",
            "product_bid": "",
            "branding_enabled": True,
            "custom_domain_enabled": True,
            "priority_class": "priority",
            "analytics_tier": "advanced",
            "support_tier": "business_hours",
            "effective_from": "2026-04-01T00:00:00+00:00",
            "effective_to": None,
            "feature_payload": {"custom_css": True},
        }
        assert entitlements_payload["data"]["items"][2] == {
            "creator_bid": "creator-3",
            "source_kind": "product_payload",
            "source_type": "subscription",
            "source_bid": "sub-creator-3",
            "product_bid": "bill-product-plan-yearly",
            "branding_enabled": True,
            "custom_domain_enabled": True,
            "priority_class": "vip",
            "analytics_tier": "enterprise",
            "support_tier": "priority",
            "effective_from": "2026-04-01T00:00:00+00:00",
            "effective_to": "2026-05-01T00:00:00+00:00",
            "feature_payload": {"beta_reports": True},
        }

        assert usage_payload["code"] == 0
        assert usage_payload["data"]["items"] == [
            {
                "creator_bid": "creator-1",
                "daily_usage_metric_bid": "daily-usage-1",
                "stat_date": "2026-04-06",
                "shifu_bid": "shifu-1",
                "usage_scene": "production",
                "usage_type": "llm",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "billing_metric": "llm_output_tokens",
                "raw_amount": 1234,
                "record_count": 3,
                "consumed_credits": 4.5,
                "window_started_at": "2026-04-06T00:00:00+00:00",
                "window_ended_at": "2026-04-07T00:00:00+00:00",
            }
        ]

        assert ledger_payload["code"] == 0
        assert ledger_payload["data"]["items"] == [
            {
                "creator_bid": "creator-1",
                "daily_ledger_summary_bid": "daily-ledger-1",
                "stat_date": "2026-04-06",
                "entry_type": "consume",
                "source_type": "usage",
                "amount": -4.5,
                "entry_count": 3,
                "window_started_at": "2026-04-06T00:00:00+00:00",
                "window_ended_at": "2026-04-07T00:00:00+00:00",
            }
        ]

    def test_ledger_supports_pagination_and_creator_isolation(
        self, billing_test_client
    ) -> None:
        ledger_response = billing_test_client.get(
            "/api/billing/ledger?page_index=1&page_size=1"
        )

        ledger_payload = ledger_response.get_json(force=True)

        assert ledger_payload["code"] == 0
        assert ledger_payload["data"]["total"] == 2
        assert ledger_payload["data"]["page_count"] == 2
        assert ledger_payload["data"]["items"][0]["ledger_bid"] == "ledger-consume"
        assert (
            ledger_payload["data"]["items"][0]["metadata"]["usage_scene"]
            == "production"
        )
        assert (
            ledger_payload["data"]["items"][0]["metadata"]["course_name"]
            == "Published Course 1"
        )
        assert (
            ledger_payload["data"]["items"][0]["metadata"]["user_identify"]
            == "learner@example.com"
        )
        assert (
            ledger_payload["data"]["items"][0]["metadata"]["metric_breakdown"][0][
                "consumed_credits"
            ]
            == 2.5
        )

    def test_ledger_uses_requested_timezone(self, billing_test_client) -> None:
        try:
            target_tz = ZoneInfo("Asia/Shanghai")
            ledger_source_tz = ZoneInfo("Asia/Shanghai")
        except ZoneInfoNotFoundError:
            pytest.skip("Asia/Shanghai timezone is unavailable in test environment")

        ledger_response = billing_test_client.get(
            "/api/billing/ledger?page_index=1&page_size=1&timezone=Asia/Shanghai"
        )

        ledger_payload = ledger_response.get_json(force=True)

        expected_ledger_created_at = datetime(
            2026, 4, 6, 10, 0, 0, tzinfo=ledger_source_tz
        ).astimezone(target_tz)

        assert ledger_payload["code"] == 0
        assert (
            ledger_payload["data"]["items"][0]["created_at"]
            == expected_ledger_created_at.isoformat()
        )

    def test_build_billing_ledger_page_uses_requested_timezone_for_created_at(
        self, billing_test_client
    ) -> None:
        try:
            target_tz = ZoneInfo("Asia/Shanghai")
            ledger_source_tz = ZoneInfo("Asia/Shanghai")
        except ZoneInfoNotFoundError:
            pytest.skip("Asia/Shanghai timezone is unavailable in test environment")

        app = billing_test_client.application

        ledger_page = build_billing_ledger_page(
            app,
            "creator-1",
            page_size=1,
            timezone_name="Asia/Shanghai",
        )
        default_ledger_page = build_billing_ledger_page(app, "creator-1", page_size=1)

        expected_created_at = datetime(
            2026, 4, 6, 10, 0, 0, tzinfo=ledger_source_tz
        ).astimezone(target_tz)

        assert ledger_page.items[0].created_at == expected_created_at.isoformat()
        assert default_ledger_page.items[0].created_at == "2026-04-06T02:00:00+00:00"

    def test_build_billing_ledger_page_uses_draft_course_name_for_non_prod_usage(
        self, billing_test_client
    ) -> None:
        app = billing_test_client.application

        with app.app_context():
            dao.db.session.add_all(
                [
                    CreditLedgerEntry(
                        ledger_bid="ledger-preview",
                        creator_bid="creator-1",
                        wallet_bid="wallet-1",
                        wallet_bucket_bid="bucket-subscription",
                        entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
                        source_type=CREDIT_SOURCE_TYPE_USAGE,
                        source_bid="usage-preview",
                        idempotency_key="usage-preview-bucket-subscription",
                        amount=Decimal("-1.0000000000"),
                        balance_after=Decimal("97.0000000000"),
                        expires_at=None,
                        consumable_from=None,
                        metadata_json={
                            "usage_bid": "usage-preview",
                            "usage_scene": BILL_USAGE_SCENE_PREVIEW,
                        },
                        created_at=datetime(2026, 4, 6, 9, 0, 0),
                        updated_at=datetime(2026, 4, 6, 9, 0, 0),
                    ),
                    CreditLedgerEntry(
                        ledger_bid="ledger-debug",
                        creator_bid="creator-1",
                        wallet_bid="wallet-1",
                        wallet_bucket_bid="bucket-subscription",
                        entry_type=CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
                        source_type=CREDIT_SOURCE_TYPE_USAGE,
                        source_bid="usage-debug",
                        idempotency_key="usage-debug-bucket-subscription",
                        amount=Decimal("-0.5000000000"),
                        balance_after=Decimal("96.5000000000"),
                        expires_at=None,
                        consumable_from=None,
                        metadata_json={
                            "usage_bid": "usage-debug",
                            "usage_scene": BILL_USAGE_SCENE_DEBUG,
                        },
                        created_at=datetime(2026, 4, 6, 8, 0, 0),
                        updated_at=datetime(2026, 4, 6, 8, 0, 0),
                    ),
                    BillUsageRecord(
                        usage_bid="usage-preview",
                        user_bid="learner-1",
                        shifu_bid="shifu-1",
                        usage_type=BILL_USAGE_TYPE_LLM,
                        usage_scene=BILL_USAGE_SCENE_PREVIEW,
                        provider="openai",
                        model="gpt-4o-mini",
                        input=0,
                        input_cache=0,
                        output=456,
                        total=456,
                        created_at=datetime(2026, 4, 6, 9, 0, 0),
                    ),
                    BillUsageRecord(
                        usage_bid="usage-debug",
                        user_bid="learner-1",
                        shifu_bid="shifu-1",
                        usage_type=BILL_USAGE_TYPE_LLM,
                        usage_scene=BILL_USAGE_SCENE_DEBUG,
                        provider="openai",
                        model="gpt-4o-mini",
                        input=0,
                        input_cache=0,
                        output=123,
                        total=123,
                        created_at=datetime(2026, 4, 6, 8, 0, 0),
                    ),
                ]
            )
            dao.db.session.commit()

        ledger_page = build_billing_ledger_page(app, "creator-1", page_size=10)
        items_by_bid = {item.ledger_bid: item for item in ledger_page.items}

        assert items_by_bid["ledger-preview"].metadata["usage_scene"] == "preview"
        assert items_by_bid["ledger-preview"].metadata["course_name"] == (
            "Draft Course 1"
        )
        assert items_by_bid["ledger-debug"].metadata["usage_scene"] == "debug"
        assert items_by_bid["ledger-debug"].metadata["course_name"] == (
            "Draft Course 1"
        )

    def test_billing_routes_require_creator(self, billing_test_client) -> None:
        response = billing_test_client.get(
            "/api/billing/catalog",
            headers={"X-Creator": "0"},
        )
        payload = response.get_json(force=True)

        assert response.status_code == 200
        assert payload["code"] != 0
