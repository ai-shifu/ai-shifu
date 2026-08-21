"""Verify billing HTTP route behavior."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from typing import TYPE_CHECKING

import flaskr.service.billing.campaigns as billing_campaigns_module
import flaskr.service.billing.entitlements as billing_entitlements_module
import flaskr.service.billing.queries as billing_queries_module
import flaskr.service.billing.read_models as billing_read_models_module
import flaskr.service.billing.serializers as billing_serializers_module
import pytest
from flask import Flask, Response, jsonify, request
from flaskr import dao
from flaskr.service.billing.capabilities import build_billing_route_bootstrap
from flaskr.service.billing.consts import (
    ALLOCATION_INTERVAL_PER_CYCLE,
    BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
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
    BILLING_TRIAL_PRODUCT_BID,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
    CREDIT_SOURCE_TYPE_GIFT,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    CREDIT_SOURCE_TYPE_USAGE,
)
from flaskr.service.billing.dtos import (
    BillingCatalogDTO,
    BillingLedgerPageDTO,
    BillingOverviewDTO,
    BillingRouteBootstrapDTO,
    BillingWalletBucketListDTO,
)
from flaskr.service.billing.models import (
    BillingCampaign,
    BillingCampaignProduct,
    BillingDailyLedgerSummary,
    BillingDailyUsageMetric,
    BillingEntitlement,
    BillingOrder,
    BillingProduct,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.read_models import (
    build_billing_catalog,
    build_billing_ledger_page,
    build_billing_overview,
    build_billing_wallet_buckets,
)
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.models import UserInfo as UserEntity
from sqlalchemy import event

from tests.common.fixtures.bill_products import build_bill_products
from tests.service.billing.route_loader import (
    load_billing_routes_module,
    load_register_billing_routes,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask.testing import FlaskClient

register_billing_routes = load_register_billing_routes()
billing_routes_module = load_billing_routes_module()


def _freeze_billing_wall_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: object | None = None) -> datetime:
            current = cls(2026, 4, 6, 12, 0, 0)
            if tz is not None:
                return current.replace(tzinfo=tz)
            return current

    _frozen_now = _FixedDateTime(2026, 4, 6, 12, 0, 0)

    monkeypatch.setattr(billing_entitlements_module, "datetime", _FixedDateTime)
    monkeypatch.setattr(billing_entitlements_module, "now_utc", lambda: _frozen_now)
    monkeypatch.setattr(billing_queries_module, "datetime", _FixedDateTime)
    monkeypatch.setattr(billing_queries_module, "now_utc", lambda: _frozen_now)
    monkeypatch.setattr(billing_read_models_module, "now_utc", lambda: _frozen_now)
    monkeypatch.setattr(billing_campaigns_module, "now_utc", lambda: _frozen_now)
    monkeypatch.setattr(billing_serializers_module, "now_utc", lambda: _frozen_now)


def _seed_products_with_yearly_entitlements() -> object:
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
def billing_test_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[FlaskClient]:
    _freeze_billing_wall_clock(monkeypatch)

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

    @app.errorhandler(AppError)
    def _handle_app_exception(error: AppError) -> Response:
        response = jsonify({"code": error.code, "message": error.message})
        response.status_code = 200
        return response

    @app.before_request
    def _inject_request_user() -> None:
        request.user = SimpleNamespace(
            user_id=request.headers.get("X-User-Id", "creator-1"),
            language="en-US",
            is_creator=request.headers.get("X-Creator", "1") == "1",
            is_operator=request.headers.get("X-Operator", "0") == "1",
        )

    monkeypatch.setattr(
        billing_routes_module,
        "is_billing_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        billing_routes_module,
        "clear_admin_creator_customization_draft",
        lambda *_args, **_kwargs: {"status": "noop"},
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
            reserved_credits=Decimal(0),
            lifetime_granted_credits=Decimal("999.0000000000"),
            lifetime_consumed_credits=Decimal(0),
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
                    reserved_credits=Decimal(0),
                    consumed_credits=Decimal(0),
                    expired_credits=Decimal(0),
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
                    reserved_credits=Decimal(0),
                    consumed_credits=Decimal(0),
                    expired_credits=Decimal(0),
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
                    reserved_credits=Decimal(0),
                    consumed_credits=Decimal(0),
                    expired_credits=Decimal(0),
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
                    reserved_credits=Decimal(0),
                    consumed_credits=Decimal(0),
                    expired_credits=Decimal(0),
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
    """Verify billing routes behavior."""

    def test_billing_routes_reject_requests_when_feature_disabled(
        self, billing_test_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
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
        self, billing_test_client: FlaskClient
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
            "method": "POST",
            "path": "/api/admin/billing/entitlements/grants",
        } in payload["data"]["admin_routes"]
        assert {
            "method": "GET",
            "path": "/api/admin/billing/reports/focus-teachers",
        } in payload["data"]["admin_routes"]
        assert {
            "method": "GET",
            "path": "/api/admin/billing/reports/usage-daily",
        } in payload["data"]["admin_routes"]
        assert {
            "method": "GET",
            "path": "/api/admin/billing/reports/ledger-daily",
        } in payload["data"]["admin_routes"]
        assert {
            "method": "GET",
            "path": "/api/admin/billing/products/options",
        } in payload["data"]["admin_routes"]
        assert {
            "method": "GET",
            "path": "/api/admin/billing/campaigns",
        } in payload["data"]["admin_routes"]
        assert {
            "method": "POST",
            "path": "/api/admin/billing/campaigns",
        } in payload["data"]["admin_routes"]

    def test_admin_can_grant_creator_customization_entitlements(
        self, billing_test_client: FlaskClient
    ) -> None:
        response = billing_test_client.post(
            "/api/admin/billing/entitlements/grants",
            headers={"X-Operator": "1"},
            json={
                "creator_bid": "creator-1",
                "branding_enabled": True,
                "custom_domain_enabled": True,
                "custom_wechat_enabled": True,
                "custom_payment_enabled": True,
            },
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["branding_enabled"] is True
        assert payload["data"]["custom_domain_enabled"] is True
        assert payload["data"]["custom_wechat_enabled"] is True
        assert payload["data"]["custom_payment_enabled"] is True

    def test_creator_logo_upload_route_uses_branding_uploader(
        self, billing_test_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            billing_routes_module,
            "is_creator_customization_enabled",
            lambda: True,
        )
        monkeypatch.setattr(
            billing_routes_module,
            "upload_creator_brand_logo",
            lambda _app, creator_bid, file, target="wide": (
                f"https://courses-oss.example.com/{creator_bid}/{target}-{file.filename}"
            ),
        )
        response = billing_test_client.post(
            "/api/billing/customization/branding/logo",
            data={"file": (BytesIO(b"png"), "wide.png"), "target": "square"},
            content_type="multipart/form-data",
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"] == (
            "https://courses-oss.example.com/creator-1/square-wide.png"
        )

    def test_catalog_overview_and_wallet_buckets_follow_design_projection(
        self, billing_test_client: FlaskClient
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
        assert bucket_payload["data"]["items"][0]["credit_asset_kind"] == "plan_credits"
        assert bucket_payload["data"]["items"][0]["priority"] == 20
        assert bucket_payload["data"]["items"][1]["credit_asset_kind"] == "plan_credits"
        assert bucket_payload["data"]["items"][2]["credit_asset_kind"] == "pack_credits"
        assert bucket_payload["data"]["items"][2]["source_bid"] == "topup-1"

    def test_overview_recalculates_wallet_snapshot_for_current_balance(
        self, billing_test_client: FlaskClient
    ) -> None:
        app = billing_test_client.application
        with app.app_context():
            wallet = CreditWallet.query.filter(
                CreditWallet.wallet_bid == "wallet-1",
            ).one()
            wallet.available_credits = Decimal(0)
            wallet.reserved_credits = Decimal(0)
            dao.db.session.add(wallet)
            dao.db.session.commit()

            overview = build_billing_overview(app, "creator-1")

            assert overview.wallet.available_credits == 120.5
            assert overview.wallet.reserved_credits == 0
            assert overview.credit_status == "normal"
            assert overview.debug_allowed is True
            assert wallet.available_credits == Decimal(0)

    def test_overview_limit_state_uses_current_consumable_bucket_balance(
        self,
        billing_test_client: FlaskClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        app = billing_test_client.application
        monkeypatch.setattr(
            billing_read_models_module,
            "is_billing_enabled",
            lambda: True,
        )
        with app.app_context():
            wallet = CreditWallet.query.filter(
                CreditWallet.wallet_bid == "wallet-1",
            ).one()
            wallet.available_credits = Decimal("20.0000000000")
            subscription = BillingSubscription.query.filter(
                BillingSubscription.subscription_bid == "sub-1",
            ).one()
            subscription.current_period_end_at = datetime(2026, 4, 5, 0, 0, 0)
            for bucket in CreditWalletBucket.query.filter(
                CreditWalletBucket.wallet_bid == "wallet-1",
            ).all():
                if bucket.wallet_bucket_bid == "bucket-topup":
                    bucket.available_credits = Decimal("20.0000000000")
                else:
                    bucket.available_credits = Decimal(0)
            dao.db.session.commit()

            overview = build_billing_overview(app, "creator-1")

            assert overview.wallet.available_credits == 0
            assert overview.credit_status == "hardlimit"

    def test_overview_limit_state_remains_normal_when_billing_disabled(
        self,
        billing_test_client: FlaskClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        app = billing_test_client.application
        monkeypatch.setattr(
            billing_read_models_module,
            "is_billing_enabled",
            lambda: False,
        )
        with app.app_context():
            wallet = CreditWallet.query.filter(
                CreditWallet.wallet_bid == "wallet-1",
            ).one()
            wallet.available_credits = Decimal(0)
            for bucket in CreditWalletBucket.query.filter(
                CreditWalletBucket.wallet_bid == "wallet-1",
            ).all():
                bucket.available_credits = Decimal(0)
            dao.db.session.commit()

            overview = build_billing_overview(app, "creator-1")

            assert overview.wallet.available_credits == 0
            assert overview.credit_status == "normal"
            assert overview.debug_allowed is True

    def test_overview_marks_stale_active_subscription_expired_without_db_update(
        self, billing_test_client: FlaskClient
    ) -> None:
        app = billing_test_client.application
        with app.app_context():
            dao.db.session.add(
                CreditWallet(
                    wallet_bid="wallet-stale-active",
                    creator_bid="creator-stale-active",
                    available_credits=Decimal(0),
                    reserved_credits=Decimal(0),
                    lifetime_granted_credits=Decimal("100.0000000000"),
                    lifetime_consumed_credits=Decimal("100.0000000000"),
                    created_at=datetime(2026, 3, 1, 0, 0, 0),
                    updated_at=datetime(2026, 4, 5, 0, 0, 0),
                )
            )
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-stale-active",
                    creator_bid="creator-stale-active",
                    product_bid="bill-product-plan-monthly-pro",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="manual",
                    provider_subscription_id="",
                    provider_customer_id="",
                    current_period_start_at=datetime(2026, 3, 1, 0, 0, 0),
                    current_period_end_at=datetime(2026, 4, 5, 0, 0, 0),
                    cancel_at_period_end=0,
                    next_product_bid="",
                    created_at=datetime(2026, 3, 1, 0, 0, 0),
                    updated_at=datetime(2026, 3, 1, 0, 0, 0),
                )
            )
            dao.db.session.commit()

        response = billing_test_client.get(
            "/api/billing/overview",
            headers={"X-User-Id": "creator-stale-active"},
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["subscription"]["subscription_bid"] == (
            "sub-stale-active"
        )
        assert payload["data"]["subscription"]["status"] == "expired"
        assert payload["data"]["billing_alerts"][0]["code"] == "low_balance"
        with app.app_context():
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-stale-active"
            ).one()
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE

    def test_overview_marks_stale_active_trial_subscription_expired(
        self, billing_test_client: FlaskClient
    ) -> None:
        app = billing_test_client.application
        with app.app_context():
            dao.db.session.add(
                CreditWallet(
                    wallet_bid="wallet-stale-trial",
                    creator_bid="creator-stale-trial",
                    available_credits=Decimal(0),
                    reserved_credits=Decimal(0),
                    lifetime_granted_credits=Decimal("100.0000000000"),
                    lifetime_consumed_credits=Decimal("100.0000000000"),
                    created_at=datetime(2026, 3, 1, 0, 0, 0),
                    updated_at=datetime(2026, 4, 5, 0, 0, 0),
                )
            )
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-stale-trial",
                    creator_bid="creator-stale-trial",
                    product_bid=BILLING_TRIAL_PRODUCT_BID,
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="manual",
                    provider_subscription_id="",
                    provider_customer_id="",
                    current_period_start_at=datetime(2026, 3, 1, 0, 0, 0),
                    current_period_end_at=datetime(2026, 3, 16, 0, 0, 0),
                    cancel_at_period_end=0,
                    next_product_bid="",
                    metadata_json={"trial_bootstrap": True},
                    created_at=datetime(2026, 3, 1, 0, 0, 0),
                    updated_at=datetime(2026, 3, 1, 0, 0, 0),
                )
            )
            dao.db.session.commit()

        response = billing_test_client.get(
            "/api/billing/overview",
            headers={"X-User-Id": "creator-stale-trial"},
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["subscription"]["subscription_bid"] == (
            "sub-stale-trial"
        )
        assert payload["data"]["subscription"]["product_bid"] == (
            BILLING_TRIAL_PRODUCT_BID
        )
        assert payload["data"]["subscription"]["status"] == "expired"
        assert payload["data"]["trial_offer"]["status"] == "granted"
        assert payload["data"]["trial_offer"]["expires_at"] is not None
        with app.app_context():
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-stale-trial"
            ).one()
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE

    def test_catalog_returns_active_campaign_payload_for_plan_product(
        self,
        billing_test_client: FlaskClient,
    ) -> None:
        app = billing_test_client.application
        with app.app_context():
            dao.db.session.add(
                BillingCampaign(
                    campaign_bid="campaign-catalog-1",
                    name="April plan discount",
                    note="",
                    benefit_type=BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
                    discount_type=BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
                    discount_amount=0,
                    discount_percent=Decimal("20.00"),
                    bonus_credit_amount=Decimal(0),
                    enabled=1,
                    start_at=datetime(2026, 4, 1, 0, 0, 0),
                    end_at=datetime(2026, 4, 30, 23, 59, 0),
                    created_user_bid="creator-1",
                    updated_user_bid="creator-1",
                )
            )
            dao.db.session.add(
                BillingCampaignProduct(
                    campaign_bid="campaign-catalog-1",
                    product_bid="bill-product-plan-monthly",
                    product_type=BILLING_PRODUCT_TYPE_PLAN,
                )
            )
            dao.db.session.commit()

        payload = billing_test_client.get("/api/billing/catalog").get_json(force=True)
        plan = next(
            item
            for item in payload["data"]["plans"]
            if item["product_bid"] == "bill-product-plan-monthly"
        )

        assert plan["campaign"] == {
            "campaign_bid": "campaign-catalog-1",
            "benefit_type": "discount",
            "discount_type": "percent",
            "discount_amount": 198,
            "discount_percent": 20,
            "campaign_price_amount": 792,
            "bonus_credit_amount": 0,
        }

    def test_catalog_serializes_daily_plan_interval_without_month_fallback(
        self, billing_test_client: FlaskClient
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

    def test_overview_and_wallet_buckets_emit_utc_ignoring_request_timezone(
        self, billing_test_client: FlaskClient
    ) -> None:
        # The backend is a single UTC sink: ?timezone= is ignored and every
        # datetime is emitted as UTC ISO 8601 with a 'Z' suffix. Display-time
        # localization is a pure frontend concern.
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

        assert overview_payload["code"] == 0
        assert (
            overview_payload["data"]["subscription"]["current_period_end_at"]
            == "2026-05-01T00:00:00Z"
        )

        assert timezone_bucket_payload["code"] == 0
        assert (
            timezone_bucket_payload["data"]["items"][0]["effective_from"]
            == "2026-04-01T00:00:00Z"
        )

        assert default_bucket_payload["code"] == 0
        assert (
            default_bucket_payload["data"]["items"][0]["effective_from"]
            == "2026-04-01T00:00:00Z"
        )

    def test_wallet_buckets_return_runtime_expired_status_before_expire_task_runs(
        self,
        billing_test_client: FlaskClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class _FixedDateTime(datetime):
            @classmethod
            def now(cls, tz: object | None = None) -> datetime:
                current = cls(2026, 5, 1, 12, 0, 0)
                if tz is not None:
                    return current.replace(tzinfo=tz)
                return current

        monkeypatch.setattr(
            "flaskr.service.billing.serializers.now_utc",
            lambda: _FixedDateTime(2026, 5, 1, 12, 0, 0),
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

    def test_wallet_buckets_keep_owned_topup_visible_after_old_window_ends(
        self,
        billing_test_client: FlaskClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "flaskr.service.billing.serializers.now_utc",
            lambda: datetime(2026, 5, 1, 12, 0, 0),
        )
        app = billing_test_client.application
        with app.app_context():
            bucket = CreditWalletBucket.query.filter(
                CreditWalletBucket.wallet_bucket_bid == "bucket-topup",
            ).one()
            bucket.effective_to = datetime(2026, 4, 5, 0, 0, 0)
            bucket.available_credits = Decimal("15.3800000000")
            dao.db.session.commit()

        payload = billing_test_client.get("/api/billing/wallet-buckets").get_json(
            force=True
        )
        bucket_map = {
            item["wallet_bucket_bid"]: item for item in payload["data"]["items"]
        }

        assert payload["code"] == 0
        assert bucket_map["bucket-topup"]["category"] == "topup"
        assert bucket_map["bucket-topup"]["status"] == "active"
        assert bucket_map["bucket-topup"]["available_credits"] == 15.38

    def test_wallet_bucket_order_lookup_is_page_scoped(
        self, billing_test_client: FlaskClient
    ) -> None:
        app = billing_test_client.application

        with app.app_context():
            order_select_count = 0

            def _count_order_selects(
                _conn: object, _cursor: object, statement: object, *_args: object
            ) -> None:
                nonlocal order_select_count
                if "bill_orders" in statement.lower():
                    order_select_count += 1

            event.listen(dao.db.engine, "before_cursor_execute", _count_order_selects)
            try:
                bucket_list = build_billing_wallet_buckets(app, "creator-1")
            finally:
                event.remove(
                    dao.db.engine,
                    "before_cursor_execute",
                    _count_order_selects,
                )

            assert order_select_count == 0
            assert len(bucket_list.items) == 3

            dao.db.session.add(
                BillingOrder(
                    bill_order_bid="order-shared-topup",
                    creator_bid="creator-1",
                    order_type=BILLING_ORDER_TYPE_TOPUP,
                    product_bid="bill-product-topup-100",
                    status=BILLING_ORDER_STATUS_PAID,
                    paid_at=datetime(2026, 4, 7, 9, 0, 0),
                )
            )
            dao.db.session.add_all(
                [
                    CreditWalletBucket(
                        wallet_bucket_bid="bucket-shared-order-1",
                        wallet_bid="wallet-1",
                        creator_bid="creator-1",
                        bucket_category=0,
                        source_type=CREDIT_SOURCE_TYPE_GIFT,
                        source_bid="gift-shared-order-1",
                        priority=4,
                        original_credits=Decimal("3.0000000000"),
                        available_credits=Decimal("3.0000000000"),
                        reserved_credits=Decimal(0),
                        consumed_credits=Decimal(0),
                        expired_credits=Decimal(0),
                        effective_from=datetime(2026, 4, 7, 9, 0, 0),
                        effective_to=None,
                        status=CREDIT_BUCKET_STATUS_ACTIVE,
                        metadata_json={"bill_order_bid": "order-shared-topup"},
                        created_at=datetime(2026, 4, 7, 9, 0, 0),
                        updated_at=datetime(2026, 4, 7, 9, 0, 0),
                    ),
                    CreditWalletBucket(
                        wallet_bucket_bid="bucket-shared-order-2",
                        wallet_bid="wallet-1",
                        creator_bid="creator-1",
                        bucket_category=0,
                        source_type=CREDIT_SOURCE_TYPE_GIFT,
                        source_bid="gift-shared-order-2",
                        priority=5,
                        original_credits=Decimal("4.0000000000"),
                        available_credits=Decimal("4.0000000000"),
                        reserved_credits=Decimal(0),
                        consumed_credits=Decimal(0),
                        expired_credits=Decimal(0),
                        effective_from=datetime(2026, 4, 7, 10, 0, 0),
                        effective_to=None,
                        status=CREDIT_BUCKET_STATUS_ACTIVE,
                        metadata_json={"bill_order_bid": "order-shared-topup"},
                        created_at=datetime(2026, 4, 7, 10, 0, 0),
                        updated_at=datetime(2026, 4, 7, 10, 0, 0),
                    ),
                ]
            )
            dao.db.session.commit()

            order_select_count = 0
            event.listen(dao.db.engine, "before_cursor_execute", _count_order_selects)
            try:
                bucket_list = build_billing_wallet_buckets(app, "creator-1")
            finally:
                event.remove(
                    dao.db.engine,
                    "before_cursor_execute",
                    _count_order_selects,
                )

        bucket_map = {item.wallet_bucket_bid: item for item in bucket_list.items}

        assert order_select_count == 1
        assert bucket_map["bucket-shared-order-1"].credit_asset_kind == "pack_credits"
        assert bucket_map["bucket-shared-order-2"].credit_asset_kind == "pack_credits"

    def test_billing_public_builders_return_dto_instances(
        self,
        billing_test_client: FlaskClient,
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
        self, billing_test_client: FlaskClient
    ) -> None:
        entitlements_response = billing_test_client.get(
            "/api/admin/billing/entitlements?page_index=1&page_size=10",
            headers={"X-Operator": "1"},
        )
        focus_response = billing_test_client.get(
            "/api/admin/billing/reports/focus-teachers?page_index=1&page_size=10",
            headers={"X-Operator": "1"},
        )
        usage_response = billing_test_client.get(
            "/api/admin/billing/reports/usage-daily?page_index=1&page_size=10&creator_bid=creator-1&date_from=2026-04-06",
            headers={"X-Operator": "1"},
        )
        ledger_response = billing_test_client.get(
            "/api/admin/billing/reports/ledger-daily?page_index=1&page_size=10&creator_bid=creator-1&date_from=2026-04-06",
            headers={"X-Operator": "1"},
        )

        entitlements_payload = entitlements_response.get_json(force=True)
        focus_payload = focus_response.get_json(force=True)
        usage_payload = usage_response.get_json(force=True)
        ledger_payload = ledger_response.get_json(force=True)

        assert entitlements_payload["code"] == 0
        assert focus_payload["code"] == 0
        assert focus_payload["data"]["total"] == 2
        assert focus_payload["data"]["items"][0]["attention_reasons"] == [
            "rapid_growth",
            "high_consumption",
            "active_production",
        ]
        assert focus_payload["data"]["items"][0]["credits_30d"] == 9
        assert focus_payload["data"]["items"][0]["record_count_7d"] == 1
        assert focus_payload["data"]["items"][0]["latest_usage_at"] == (
            "2026-04-06T00:00:00Z"
        )
        assert entitlements_payload["data"]["total"] == 3
        assert entitlements_payload["data"]["items"][0] == {
            "creator_bid": "creator-1",
            "creator_mobile": "",
            "creator_email": "",
            "creator_nickname": "",
            "creator_identify": "",
            "source_kind": "snapshot",
            "source_type": "subscription",
            "source_bid": "sub-1",
            "product_bid": "",
            "product_name_key": "",
            "branding_enabled": True,
            "custom_domain_enabled": True,
            "custom_wechat_enabled": False,
            "custom_payment_enabled": False,
            "priority_class": "priority",
            "analytics_tier": "advanced",
            "support_tier": "business_hours",
            "effective_from": "2026-04-01T00:00:00Z",
            "effective_to": None,
            "feature_payload": {"custom_css": True},
        }
        assert entitlements_payload["data"]["items"][2] == {
            "creator_bid": "creator-3",
            "creator_mobile": "",
            "creator_email": "",
            "creator_nickname": "",
            "creator_identify": "",
            "source_kind": "product_payload",
            "source_type": "subscription",
            "source_bid": "sub-creator-3",
            "product_bid": "bill-product-plan-yearly",
            "product_name_key": "module.billing.catalog.plans.creatorYearly.title",
            "branding_enabled": True,
            "custom_domain_enabled": True,
            "custom_wechat_enabled": False,
            "custom_payment_enabled": False,
            "priority_class": "vip",
            "analytics_tier": "enterprise",
            "support_tier": "priority",
            "effective_from": "2026-04-01T00:00:00Z",
            "effective_to": "2026-05-01T00:00:00Z",
            "feature_payload": {"beta_reports": True},
        }

        assert usage_payload["code"] == 0
        assert usage_payload["data"]["items"] == [
            {
                "creator_bid": "creator-1",
                "creator_mobile": "",
                "creator_email": "",
                "creator_nickname": "",
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
                "window_started_at": "2026-04-06T00:00:00Z",
                "window_ended_at": "2026-04-07T00:00:00Z",
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
                "window_started_at": "2026-04-06T00:00:00Z",
                "window_ended_at": "2026-04-07T00:00:00Z",
            }
        ]

    def test_ledger_supports_pagination_and_creator_isolation(
        self, billing_test_client: FlaskClient
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
        assert ledger_payload["data"]["items"][0]["credit_asset_kind"] == "plan_credits"

    def test_billing_ledger_page_exposes_canonical_credit_asset_kind(
        self, billing_test_client: FlaskClient
    ) -> None:
        app = billing_test_client.application

        with app.app_context():
            dao.db.session.add_all(
                [
                    BillingOrder(
                        bill_order_bid="order-campaign-topup",
                        creator_bid="creator-1",
                        order_type=BILLING_ORDER_TYPE_TOPUP,
                        product_bid="bill-product-topup-100",
                        status=BILLING_ORDER_STATUS_PAID,
                        paid_at=datetime(2026, 4, 7, 9, 0, 0),
                    ),
                    BillingOrder(
                        bill_order_bid="order-bucket-plan",
                        creator_bid="creator-1",
                        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                        product_bid="bill-product-plan-monthly",
                        status=BILLING_ORDER_STATUS_PAID,
                        paid_at=datetime(2026, 4, 7, 9, 30, 0),
                    ),
                    BillingOrder(
                        bill_order_bid="order-other-creator-topup",
                        creator_bid="creator-2",
                        order_type=BILLING_ORDER_TYPE_TOPUP,
                        product_bid="bill-product-topup-100",
                        status=BILLING_ORDER_STATUS_PAID,
                        paid_at=datetime(2026, 4, 7, 9, 45, 0),
                    ),
                ]
            )
            dao.db.session.add(
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-gift-order-backed",
                    wallet_bid="wallet-1",
                    creator_bid="creator-1",
                    bucket_category=0,
                    source_type=CREDIT_SOURCE_TYPE_GIFT,
                    source_bid="gift-order-backed",
                    priority=4,
                    original_credits=Decimal("6.0000000000"),
                    available_credits=Decimal("6.0000000000"),
                    reserved_credits=Decimal(0),
                    consumed_credits=Decimal(0),
                    expired_credits=Decimal(0),
                    effective_from=datetime(2026, 4, 7, 9, 30, 0),
                    effective_to=datetime(2026, 5, 7, 9, 30, 0),
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={"bill_order_bid": "order-bucket-plan"},
                    created_at=datetime(2026, 4, 7, 9, 30, 0),
                    updated_at=datetime(2026, 4, 7, 9, 30, 0),
                )
            )
            dao.db.session.add_all(
                [
                    CreditLedgerEntry(
                        ledger_bid="ledger-topup-grant",
                        creator_bid="creator-1",
                        wallet_bid="wallet-1",
                        wallet_bucket_bid="bucket-topup",
                        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                        source_type=CREDIT_SOURCE_TYPE_TOPUP,
                        source_bid="topup-1",
                        idempotency_key="grant-topup-1",
                        amount=Decimal("20.0000000000"),
                        balance_after=Decimal("120.5000000000"),
                        expires_at=None,
                        consumable_from=datetime(2026, 4, 3, 0, 0, 0),
                        metadata_json={"bucket_credit_state": "available"},
                        created_at=datetime(2026, 4, 7, 10, 0, 0),
                        updated_at=datetime(2026, 4, 7, 10, 0, 0),
                    ),
                    CreditLedgerEntry(
                        ledger_bid="ledger-bucket-order-backed",
                        creator_bid="creator-1",
                        wallet_bid="wallet-1",
                        wallet_bucket_bid="bucket-gift-order-backed",
                        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                        source_type=CREDIT_SOURCE_TYPE_GIFT,
                        source_bid="gift-order-backed",
                        idempotency_key="grant-gift-order-backed",
                        amount=Decimal("6.0000000000"),
                        balance_after=Decimal("126.5000000000"),
                        expires_at=datetime(2026, 5, 7, 9, 30, 0),
                        consumable_from=datetime(2026, 4, 7, 9, 30, 0),
                        metadata_json={"bucket_credit_state": "available"},
                        created_at=datetime(2026, 4, 7, 9, 30, 0),
                        updated_at=datetime(2026, 4, 7, 9, 30, 0),
                    ),
                    CreditLedgerEntry(
                        ledger_bid="ledger-referral-reward",
                        creator_bid="creator-1",
                        wallet_bid="wallet-1",
                        wallet_bucket_bid="bucket-subscription",
                        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                        source_type=CREDIT_SOURCE_TYPE_MANUAL,
                        source_bid="referral_reward",
                        idempotency_key="operator_referral_reward:1",
                        amount=Decimal("5.0000000000"),
                        balance_after=Decimal("125.5000000000"),
                        expires_at=datetime(2026, 5, 1, 0, 0, 0),
                        consumable_from=datetime(2026, 4, 7, 11, 0, 0),
                        metadata_json={
                            "grant_type": "referral_reward",
                            "reward_scene": "referral",
                            "reward_program": "referral_reward",
                        },
                        created_at=datetime(2026, 4, 7, 11, 0, 0),
                        updated_at=datetime(2026, 4, 7, 11, 0, 0),
                    ),
                    CreditLedgerEntry(
                        ledger_bid="ledger-campaign-bonus-1",
                        creator_bid="creator-1",
                        wallet_bid="wallet-1",
                        wallet_bucket_bid="",
                        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                        source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
                        source_bid="campaign-1",
                        idempotency_key="campaign-bonus-1",
                        amount=Decimal("3.0000000000"),
                        balance_after=Decimal("128.5000000000"),
                        expires_at=None,
                        consumable_from=datetime(2026, 4, 7, 12, 0, 0),
                        metadata_json={"bill_order_bid": "order-campaign-topup"},
                        created_at=datetime(2026, 4, 7, 12, 0, 0),
                        updated_at=datetime(2026, 4, 7, 12, 0, 0),
                    ),
                    CreditLedgerEntry(
                        ledger_bid="ledger-campaign-bonus-2",
                        creator_bid="creator-1",
                        wallet_bid="wallet-1",
                        wallet_bucket_bid="",
                        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                        source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
                        source_bid="campaign-1",
                        idempotency_key="campaign-bonus-2",
                        amount=Decimal("4.0000000000"),
                        balance_after=Decimal("132.5000000000"),
                        expires_at=None,
                        consumable_from=datetime(2026, 4, 7, 13, 0, 0),
                        metadata_json={"bill_order_bid": "order-campaign-topup"},
                        created_at=datetime(2026, 4, 7, 13, 0, 0),
                        updated_at=datetime(2026, 4, 7, 13, 0, 0),
                    ),
                    CreditLedgerEntry(
                        ledger_bid="ledger-internal-legacy",
                        creator_bid="creator-1",
                        wallet_bid="wallet-1",
                        wallet_bucket_bid="",
                        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                        source_type=CREDIT_SOURCE_TYPE_MANUAL,
                        source_bid="manual-adjustment",
                        idempotency_key="manual-adjustment-1",
                        amount=Decimal("1.0000000000"),
                        balance_after=Decimal("133.5000000000"),
                        expires_at=None,
                        consumable_from=datetime(2026, 4, 7, 14, 0, 0),
                        metadata_json={},
                        created_at=datetime(2026, 4, 7, 14, 0, 0),
                        updated_at=datetime(2026, 4, 7, 14, 0, 0),
                    ),
                    CreditLedgerEntry(
                        ledger_bid="ledger-cross-creator-order",
                        creator_bid="creator-1",
                        wallet_bid="wallet-1",
                        wallet_bucket_bid="",
                        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                        source_type=CREDIT_SOURCE_TYPE_CAMPAIGN_BONUS,
                        source_bid="campaign-cross-creator",
                        idempotency_key="campaign-cross-creator-1",
                        amount=Decimal("2.0000000000"),
                        balance_after=Decimal("135.5000000000"),
                        expires_at=None,
                        consumable_from=datetime(2026, 4, 7, 15, 0, 0),
                        metadata_json={"bill_order_bid": "order-other-creator-topup"},
                        created_at=datetime(2026, 4, 7, 15, 0, 0),
                        updated_at=datetime(2026, 4, 7, 15, 0, 0),
                    ),
                ]
            )
            dao.db.session.commit()

        order_select_count = 0

        def _count_order_selects(
            _conn: object, _cursor: object, statement: object, *_args: object
        ) -> None:
            nonlocal order_select_count
            if "bill_orders" in statement.lower():
                order_select_count += 1

        with app.app_context():
            event.listen(dao.db.engine, "before_cursor_execute", _count_order_selects)
            try:
                ledger_page = build_billing_ledger_page(app, "creator-1", page_size=10)
            finally:
                event.remove(
                    dao.db.engine,
                    "before_cursor_execute",
                    _count_order_selects,
                )
        asset_kind_by_bid = {
            item.ledger_bid: item.credit_asset_kind for item in ledger_page.items
        }

        assert order_select_count == 1
        assert asset_kind_by_bid["ledger-bucket-order-backed"] == "plan_credits"
        assert asset_kind_by_bid["ledger-campaign-bonus-1"] == "pack_credits"
        assert asset_kind_by_bid["ledger-campaign-bonus-2"] == "pack_credits"
        assert asset_kind_by_bid["ledger-referral-reward"] == "plan_credits"
        assert asset_kind_by_bid["ledger-topup-grant"] == "pack_credits"
        assert asset_kind_by_bid["ledger-grant"] == "plan_credits"
        assert asset_kind_by_bid["ledger-consume"] == "plan_credits"
        assert asset_kind_by_bid["ledger-internal-legacy"] == "internal_legacy"
        assert asset_kind_by_bid["ledger-cross-creator-order"] == "unknown"

    def test_ledger_emits_utc_ignoring_request_timezone(
        self, billing_test_client: FlaskClient
    ) -> None:
        ledger_response = billing_test_client.get(
            "/api/billing/ledger?page_index=1&page_size=1&timezone=Asia/Shanghai"
        )

        ledger_payload = ledger_response.get_json(force=True)

        assert ledger_payload["code"] == 0
        assert (
            ledger_payload["data"]["items"][0]["created_at"] == "2026-04-06T10:00:00Z"
        )

    def test_build_billing_ledger_page_returns_raw_created_at(
        self, billing_test_client: FlaskClient
    ) -> None:
        # DTO datetime fields now hold the raw stored datetime; the browser
        # timezone thread is gone and the fmt sink emits UTC at serialization time.
        app = billing_test_client.application

        ledger_page = build_billing_ledger_page(app, "creator-1", page_size=1)

        assert ledger_page.items[0].created_at == datetime(2026, 4, 6, 10, 0)

    def test_build_billing_ledger_page_hides_reserved_grants_until_available(
        self, billing_test_client: FlaskClient
    ) -> None:
        app = billing_test_client.application

        with app.app_context():
            dao.db.session.add_all(
                [
                    CreditLedgerEntry(
                        ledger_bid="ledger-reserved-renewal",
                        creator_bid="creator-1",
                        wallet_bid="wallet-1",
                        wallet_bucket_bid="bucket-subscription",
                        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                        source_bid="order-reserved-renewal",
                        idempotency_key="grant:order-reserved-renewal",
                        amount=Decimal("1000.0000000000"),
                        balance_after=Decimal("1098.0000000000"),
                        expires_at=datetime(2026, 6, 1, 0, 0, 0),
                        consumable_from=datetime(2026, 5, 1, 0, 0, 0),
                        metadata_json={"bucket_credit_state": "reserved"},
                        created_at=datetime(2026, 4, 7, 10, 0, 0),
                        updated_at=datetime(2026, 4, 7, 10, 0, 0),
                    ),
                    CreditLedgerEntry(
                        ledger_bid="ledger-absorbed-renewal",
                        creator_bid="creator-1",
                        wallet_bid="wallet-1",
                        wallet_bucket_bid="bucket-subscription",
                        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                        source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                        source_bid="order-absorbed-renewal",
                        idempotency_key="grant:order-absorbed-renewal",
                        amount=Decimal("2000.0000000000"),
                        balance_after=Decimal("98.0000000000"),
                        expires_at=datetime(2026, 6, 1, 0, 0, 0),
                        consumable_from=datetime(2026, 5, 1, 0, 0, 0),
                        metadata_json={"bucket_credit_state": " AbSoRbEd "},
                        created_at=datetime(2026, 4, 7, 11, 0, 0),
                        updated_at=datetime(2026, 4, 7, 11, 0, 0),
                    ),
                ]
            )
            dao.db.session.commit()

        ledger_page = build_billing_ledger_page(app, "creator-1", page_size=10)

        assert ledger_page.total == 2
        assert {item.ledger_bid for item in ledger_page.items} == {
            "ledger-consume",
            "ledger-grant",
        }

        with app.app_context():
            reserved_ledger = CreditLedgerEntry.query.filter_by(
                ledger_bid="ledger-reserved-renewal"
            ).one()
            reserved_ledger.metadata_json = {"bucket_credit_state": "available"}
            dao.db.session.commit()

        activated_page = build_billing_ledger_page(app, "creator-1", page_size=10)

        assert activated_page.total == 3
        assert activated_page.items[0].ledger_bid == "ledger-reserved-renewal"

    def test_build_billing_ledger_page_uses_draft_course_name_for_non_prod_usage(
        self, billing_test_client: FlaskClient
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

    def test_billing_routes_require_creator(
        self, billing_test_client: FlaskClient
    ) -> None:
        response = billing_test_client.get(
            "/api/billing/catalog",
            headers={"X-Creator": "0"},
        )
        payload = response.get_json(force=True)

        assert response.status_code == 200
        assert payload["code"] != 0
