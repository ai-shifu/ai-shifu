from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from flask import Flask, jsonify, request
import pytest

import flaskr.dao as dao
from flaskr.i18n import _translations, load_translations, set_language
import flaskr.service.billing.campaigns as billing_campaigns_module
from flaskr.service.common.models import ERROR_CODE
from flaskr.service.billing.consts import (
    BILLING_CAMPAIGN_BENEFIT_TYPE_BONUS,
    BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT,
    CREDIT_SOURCE_TYPE_GIFT,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
)
from flaskr.service.billing.campaigns import (
    build_admin_billing_campaign_detail,
    build_admin_billing_campaign_product_options,
    build_admin_billing_campaigns_page,
)
from flaskr.service.billing.dtos import (
    AdminBillingCampaignDetailDTO,
    AdminBillingCampaignProductOptionsDTO,
    AdminBillingCampaignsPageDTO,
    BillingDomainAuditsPageDTO,
    BillingEntitlementsPageDTO,
    BillingLedgerAdjustResultDTO,
    BillingSubscriptionsPageDTO,
    AdminBillingDailyLedgerSummaryPageDTO,
    AdminBillingDailyUsageMetricsPageDTO,
    AdminBillingOrdersPageDTO,
)
from flaskr.service.billing.read_models import (
    adjust_admin_billing_ledger,
    build_admin_bill_daily_ledger_summary_page,
    build_admin_bill_daily_usage_metrics_page,
    build_admin_billing_domain_audits_page,
    build_admin_bill_entitlements_page,
    build_admin_bill_orders_page,
    build_admin_bill_subscriptions_page,
)
import flaskr.service.billing.queries as billing_queries_module
import flaskr.service.billing.serializers as billing_serializers_module
import flaskr.service.billing.wallets as billing_wallets_module
from flaskr.service.billing.models import (
    BillingCampaign,
    BillingCampaignProduct,
    BillingOrder,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.common.models import AppException
from tests.common.fixtures.bill_products import build_bill_products
from tests.service.billing.route_loader import (
    load_billing_routes_module,
    load_register_billing_routes,
)

billing_routes_module = load_billing_routes_module()
register_billing_routes = load_register_billing_routes()


def _freeze_billing_wall_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = cls(2026, 4, 6, 12, 0, 0)
            if tz is not None:
                return current.replace(tzinfo=tz)
            return current

    _frozen_now = _FixedDateTime(2026, 4, 6, 12, 0, 0)

    monkeypatch.setattr(billing_queries_module, "datetime", _FixedDateTime)
    monkeypatch.setattr(billing_wallets_module, "datetime", _FixedDateTime)
    monkeypatch.setattr(billing_campaigns_module, "datetime", _FixedDateTime)
    monkeypatch.setattr(billing_campaigns_module, "now_utc", lambda: _frozen_now)
    monkeypatch.setattr(billing_serializers_module, "now_utc", lambda: _frozen_now)


@pytest.fixture
def admin_billing_client(monkeypatch):
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
        TZ="UTC",
    )

    dao.db.init_app(app)
    load_translations(app)

    @app.errorhandler(AppException)
    def _handle_app_exception(error: AppException):
        response = jsonify({"code": error.code, "message": error.message})
        response.status_code = 200
        return response

    @app.before_request
    def _inject_request_user() -> None:
        request.user = SimpleNamespace(
            user_id=request.headers.get("X-User-Id", "admin-creator"),
            language="en-US",
            is_creator=request.headers.get("X-Creator", "1") == "1",
            is_operator=request.headers.get("X-Operator", "1") == "1",
        )
        set_language(request.user.language)

    monkeypatch.setattr(
        billing_routes_module,
        "is_billing_enabled",
        lambda: True,
    )

    register_billing_routes(app=app)

    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(build_bill_products())
        dao.db.session.add_all(
            [
                CreditWallet(
                    wallet_bid="wallet-1",
                    creator_bid="creator-1",
                    available_credits=Decimal("110.0000000000"),
                    reserved_credits=Decimal("0"),
                    lifetime_granted_credits=Decimal("110.0000000000"),
                    lifetime_consumed_credits=Decimal("0"),
                ),
                CreditWallet(
                    wallet_bid="wallet-2",
                    creator_bid="creator-2",
                    available_credits=Decimal("5.0000000000"),
                    reserved_credits=Decimal("0"),
                    lifetime_granted_credits=Decimal("5.0000000000"),
                    lifetime_consumed_credits=Decimal("0"),
                ),
            ]
        )
        dao.db.session.add_all(
            [
                BillingSubscription(
                    subscription_bid="sub-active",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-monthly",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="stripe",
                    provider_subscription_id="sub_provider_active",
                    provider_customer_id="cus_active",
                    current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
                    current_period_end_at=datetime(2026, 5, 1, 0, 0, 0),
                    cancel_at_period_end=0,
                    last_renewed_at=datetime(2026, 4, 1, 0, 0, 0),
                ),
                BillingSubscription(
                    subscription_bid="sub-past-due",
                    creator_bid="creator-2",
                    product_bid="bill-product-plan-yearly",
                    status=BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
                    billing_provider="stripe",
                    provider_subscription_id="sub_provider_past_due",
                    provider_customer_id="cus_past_due",
                    current_period_start_at=datetime(2026, 3, 1, 0, 0, 0),
                    current_period_end_at=datetime(2026, 4, 1, 0, 0, 0),
                    grace_period_end_at=datetime(2026, 4, 8, 0, 0, 0),
                    cancel_at_period_end=0,
                    last_renewed_at=datetime(2026, 3, 1, 0, 0, 0),
                    last_failed_at=datetime(2026, 4, 2, 12, 0, 0),
                ),
            ]
        )
        dao.db.session.add(
            BillingRenewalEvent(
                renewal_event_bid="renewal-failed",
                subscription_bid="sub-past-due",
                creator_bid="creator-2",
                event_type=BILLING_RENEWAL_EVENT_TYPE_RETRY,
                scheduled_at=datetime(2026, 4, 3, 8, 0, 0),
                status=BILLING_RENEWAL_EVENT_STATUS_FAILED,
                attempt_count=2,
                last_error="card_declined",
                payload_json={"bill_order_bid": "order-failed"},
                processed_at=datetime(2026, 4, 3, 8, 5, 0),
            )
        )
        dao.db.session.add_all(
            [
                BillingOrder(
                    bill_order_bid="order-paid",
                    creator_bid="creator-1",
                    order_type=BILLING_ORDER_TYPE_TOPUP,
                    product_bid="bill-product-topup-small",
                    subscription_bid="",
                    currency="CNY",
                    payable_amount=19900,
                    paid_amount=19900,
                    payment_provider="pingxx",
                    channel="alipay_qr",
                    provider_reference_id="charge_paid",
                    status=BILLING_ORDER_STATUS_PAID,
                    paid_at=datetime(2026, 4, 4, 9, 0, 0),
                    created_at=datetime(2026, 4, 4, 8, 0, 0),
                ),
                BillingOrder(
                    bill_order_bid="order-failed",
                    creator_bid="creator-2",
                    order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                    product_bid="bill-product-plan-yearly",
                    subscription_bid="sub-past-due",
                    currency="CNY",
                    payable_amount=99900,
                    paid_amount=0,
                    payment_provider="stripe",
                    channel="checkout_session",
                    provider_reference_id="cs_failed",
                    status=BILLING_ORDER_STATUS_FAILED,
                    failure_code="card_declined",
                    failure_message="Card was declined",
                    failed_at=datetime(2026, 4, 3, 8, 0, 0),
                    created_at=datetime(2026, 4, 3, 7, 55, 0),
                ),
            ]
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
                    priority=10,
                    original_credits=Decimal("10.0000000000"),
                    available_credits=Decimal("10.0000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 1, 0, 0, 0),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                ),
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-subscription",
                    wallet_bid="wallet-1",
                    creator_bid="creator-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                    source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                    source_bid="sub-active",
                    priority=20,
                    original_credits=Decimal("100.0000000000"),
                    available_credits=Decimal("100.0000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 1, 0, 0, 0),
                    effective_to=datetime(2026, 5, 1, 0, 0, 0),
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                ),
            ]
        )
        dao.db.session.commit()

        with app.test_client() as client:
            yield {"app": app, "client": client}

        dao.db.session.remove()
        dao.db.drop_all()


class TestAdminBillingRoutes:
    def test_admin_bill_subscriptions_returns_wallet_and_renewal_context(
        self, admin_billing_client
    ) -> None:
        client = admin_billing_client["client"]

        response = client.get(
            "/api/admin/billing/subscriptions?page_index=1&page_size=10"
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["total"] == 2
        first_item = payload["data"]["items"][0]
        assert first_item["subscription_bid"] == "sub-past-due"
        assert first_item["creator_bid"] == "creator-2"
        assert first_item["status"] == "past_due"
        assert first_item["wallet"]["available_credits"] == 5
        assert first_item["has_attention"] is True
        assert first_item["latest_renewal_event"]["event_type"] == "retry"
        assert first_item["latest_renewal_event"]["status"] == "failed"
        assert first_item["latest_renewal_event"]["last_error"] == "card_declined"

    def test_admin_bill_orders_support_creator_and_status_filters(
        self, admin_billing_client
    ) -> None:
        client = admin_billing_client["client"]

        response = client.get(
            "/api/admin/billing/orders?page_index=1&page_size=10&creator_bid=creator-2&status=failed"
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["total"] == 1
        item = payload["data"]["items"][0]
        assert item["bill_order_bid"] == "order-failed"
        assert item["creator_bid"] == "creator-2"
        assert item["status"] == "failed"
        assert item["failure_code"] == "card_declined"
        assert item["failed_at"] == "2026-04-03T08:00:00Z"
        assert item["has_attention"] is True

    def test_admin_billing_ledger_adjust_positive_creates_manual_subscription_bucket(
        self, admin_billing_client
    ) -> None:
        client = admin_billing_client["client"]
        app = admin_billing_client["app"]

        response = client.post(
            "/api/admin/billing/ledger/adjust",
            json={
                "creator_bid": "creator-1",
                "amount": "12.5000000000",
                "note": "manual bonus",
            },
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["status"] == "adjusted"
        assert payload["data"]["amount"] == 12.5
        assert payload["data"]["wallet"]["available_credits"] == 122.5

        with app.app_context():
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = (
                CreditWalletBucket.query.filter_by(
                    creator_bid="creator-1",
                    source_type=CREDIT_SOURCE_TYPE_MANUAL,
                )
                .order_by(CreditWalletBucket.id.desc())
                .one()
            )
            ledger_entry = (
                CreditLedgerEntry.query.filter_by(
                    creator_bid="creator-1",
                    source_type=CREDIT_SOURCE_TYPE_MANUAL,
                )
                .order_by(CreditLedgerEntry.id.desc())
                .one()
            )

            assert wallet.available_credits == Decimal("122.5000000000")
            assert bucket.bucket_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
            assert bucket.available_credits == Decimal("12.5000000000")
            assert ledger_entry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_ADJUSTMENT
            assert ledger_entry.amount == Decimal("12.5000000000")
            assert ledger_entry.metadata_json["note"] == "manual bonus"

    def test_admin_billing_ledger_adjust_negative_uses_bucket_consumption_order(
        self, admin_billing_client
    ) -> None:
        client = admin_billing_client["client"]
        app = admin_billing_client["app"]

        response = client.post(
            "/api/admin/billing/ledger/adjust",
            json={
                "creator_bid": "creator-1",
                "amount": "-12.5000000000",
                "note": "manual debit",
            },
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["status"] == "adjusted"
        assert payload["data"]["amount"] == -12.5
        assert payload["data"]["wallet"]["available_credits"] == 97.5

        with app.app_context():
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            free_bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-free"
            ).one()
            subscription_bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-subscription"
            ).one()
            entries = (
                CreditLedgerEntry.query.filter_by(
                    creator_bid="creator-1",
                    source_type=CREDIT_SOURCE_TYPE_MANUAL,
                )
                .order_by(CreditLedgerEntry.id.asc())
                .all()
            )

            assert wallet.available_credits == Decimal("97.5000000000")
            assert free_bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
            assert free_bucket.available_credits == Decimal("10.0000000000")
            assert subscription_bucket.available_credits == Decimal("87.5000000000")
            assert [entry.wallet_bucket_bid for entry in entries] == [
                "bucket-subscription",
            ]
            assert [entry.amount for entry in entries] == [
                Decimal("-12.5000000000"),
            ]

    def test_admin_billing_campaign_routes_support_options_crud_and_status(
        self,
        admin_billing_client,
    ) -> None:
        client = admin_billing_client["client"]

        options_response = client.get("/api/admin/billing/products/options")
        options_payload = options_response.get_json(force=True)

        assert options_payload["code"] == 0
        assert options_payload["data"]["plans"]
        assert options_payload["data"]["topups"]

        create_response = client.post(
            "/api/admin/billing/campaigns",
            json={
                "name": "Monthly bonus",
                "note": "ops test",
                "product_type": "plan",
                "benefit_type": "bonus",
                "products": [
                    {
                        "product_bid": "bill-product-plan-monthly",
                        "bonus_credit_amount": "18",
                    }
                ],
                "start_at": "2026-04-10 00:00:00",
                "end_at": "2026-04-20 23:59:00",
            },
        )
        create_payload = create_response.get_json(force=True)

        assert create_payload["code"] == 0
        created_campaign_bid = create_payload["data"]["campaign"]["campaign_bid"]
        assert created_campaign_bid
        assert create_payload["data"]["campaign"]["benefit_type"] == "bonus"
        assert create_payload["data"]["campaign"]["bonus_credit_amount"] == 18
        assert create_payload["data"]["products"][0]["product_bid"] == (
            "bill-product-plan-monthly"
        )
        assert (
            create_payload["data"]["products"][0]["campaign_bonus_credit_amount"] == 18
        )

        list_response = client.get(
            "/api/admin/billing/campaigns?page_index=1&page_size=10"
            "&keyword=Monthly&product_type=plan&benefit_type=bonus&status=upcoming"
        )
        list_payload = list_response.get_json(force=True)

        assert list_payload["code"] == 0
        assert list_payload["data"]["total"] == 1
        assert list_payload["data"]["items"][0]["campaign_bid"] == created_campaign_bid

        detail_response = client.get(
            f"/api/admin/billing/campaigns/{created_campaign_bid}"
        )
        detail_payload = detail_response.get_json(force=True)

        assert detail_payload["code"] == 0
        assert detail_payload["data"]["campaign"]["name"] == "Monthly bonus"
        assert detail_payload["data"]["products"][0]["product_type"] == "plan"

        update_response = client.post(
            f"/api/admin/billing/campaigns/{created_campaign_bid}",
            json={
                "name": "Monthly bonus updated",
                "note": "ops test updated",
                "product_type": "plan",
                "benefit_type": "discount",
                "products": [
                    {
                        "product_bid": "bill-product-plan-monthly",
                        "discount_type": "percent",
                        "discount_percent": "15",
                    }
                ],
                "start_at": "2026-04-10 00:00:00",
                "end_at": "2026-04-22 23:59:00",
            },
        )
        update_payload = update_response.get_json(force=True)

        assert update_payload["code"] == 0
        assert update_payload["data"]["campaign"]["name"] == "Monthly bonus updated"
        assert update_payload["data"]["campaign"]["benefit_type"] == "discount"
        assert update_payload["data"]["campaign"]["discount_type"] == "percent"
        assert update_payload["data"]["campaign"]["discount_percent"] == 15
        assert (
            update_payload["data"]["products"][0]["campaign_discount_type"] == "percent"
        )

        status_response = client.post(
            f"/api/admin/billing/campaigns/{created_campaign_bid}/status",
            json={"enabled": False},
        )
        status_payload = status_response.get_json(force=True)

        assert status_payload["code"] == 0
        assert status_payload["data"]["campaign"]["enabled"] is False
        assert status_payload["data"]["campaign"]["computed_status"] == "inactive"

    def test_admin_billing_campaign_create_returns_overlap_product_names(
        self,
        admin_billing_client,
    ) -> None:
        client = admin_billing_client["client"]

        first_response = client.post(
            "/api/admin/billing/campaigns",
            json={
                "name": "Monthly overlap 1",
                "note": "ops test",
                "product_type": "plan",
                "benefit_type": "bonus",
                "products": [
                    {
                        "product_bid": "bill-product-plan-monthly",
                        "bonus_credit_amount": "18",
                    }
                ],
                "start_at": "2026-04-10 00:00:00",
                "end_at": "2026-04-20 23:59:00",
            },
        )
        first_payload = first_response.get_json(force=True)
        assert first_payload["code"] == 0

        overlap_response = client.post(
            "/api/admin/billing/campaigns",
            json={
                "name": "Monthly overlap 2",
                "note": "ops test",
                "product_type": "plan",
                "benefit_type": "discount",
                "products": [
                    {
                        "product_bid": "bill-product-plan-monthly",
                        "discount_type": "percent",
                        "discount_percent": "15",
                    }
                ],
                "start_at": "2026-04-15 00:00:00",
                "end_at": "2026-04-25 23:59:00",
            },
        )
        overlap_payload = overlap_response.get_json(force=True)

        assert (
            overlap_payload["code"]
            == ERROR_CODE["server.billing.campaignOverlapActive"]
        )
        assert "Lite" in overlap_payload["message"]

    def test_admin_billing_campaign_create_ignores_ended_overlap(
        self,
        admin_billing_client,
    ) -> None:
        client = admin_billing_client["client"]

        ended_response = client.post(
            "/api/admin/billing/campaigns",
            json={
                "name": "Monthly ended overlap",
                "note": "ops test",
                "product_type": "plan",
                "benefit_type": "bonus",
                "products": [
                    {
                        "product_bid": "bill-product-plan-monthly",
                        "bonus_credit_amount": "18",
                    }
                ],
                "start_at": "2026-04-01 00:00:00",
                "end_at": "2026-04-05 23:59:00",
            },
        )
        ended_payload = ended_response.get_json(force=True)
        assert ended_payload["code"] == 0
        assert ended_payload["data"]["campaign"]["computed_status"] == "ended"

        active_response = client.post(
            "/api/admin/billing/campaigns",
            json={
                "name": "Monthly active after ended",
                "note": "ops test",
                "product_type": "plan",
                "benefit_type": "discount",
                "products": [
                    {
                        "product_bid": "bill-product-plan-monthly",
                        "discount_type": "fixed",
                        "campaign_price_amount": "500",
                    }
                ],
                "start_at": "2026-04-04 00:00:00",
                "end_at": "2026-04-10 23:59:00",
            },
        )
        active_payload = active_response.get_json(force=True)

        assert active_payload["code"] == 0
        assert active_payload["data"]["campaign"]["computed_status"] == "active"

    def test_admin_billing_campaign_routes_require_operator(
        self,
        admin_billing_client,
    ) -> None:
        client = admin_billing_client["client"]

        response = client.get(
            "/api/admin/billing/campaigns",
            headers={"X-Operator": "0"},
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 401
        assert payload["message"] == _translations["en-US"]["server.shifu.noPermission"]

    def test_admin_billing_campaign_rejects_zero_campaign_price(
        self,
        admin_billing_client,
    ) -> None:
        client = admin_billing_client["client"]

        response = client.post(
            "/api/admin/billing/campaigns",
            json={
                "name": "Zero price discount",
                "note": "ops test",
                "product_type": "topup",
                "benefit_type": "discount",
                "products": [
                    {
                        "product_bid": "bill-product-topup-small",
                        "discount_type": "fixed",
                        "campaign_price_amount": 0,
                    }
                ],
                "start_at": "2026-04-10 00:00:00",
                "end_at": "2026-04-20 23:59:00",
            },
        )
        payload = response.get_json(force=True)

        assert payload["code"] == ERROR_CODE["server.common.paramsError"]
        assert "campaign_price_amount" in payload["message"]

    def test_admin_billing_campaign_update_locks_product_rules_after_hit(
        self,
        admin_billing_client,
    ) -> None:
        app = admin_billing_client["app"]
        client = admin_billing_client["client"]

        create_response = client.post(
            "/api/admin/billing/campaigns",
            json={
                "name": "Hit locked discount",
                "note": "ops test",
                "product_type": "topup",
                "benefit_type": "discount",
                "products": [
                    {
                        "product_bid": "bill-product-topup-small",
                        "discount_type": "fixed",
                        "campaign_price_amount": "4000",
                    },
                    {
                        "product_bid": "bill-product-topup-medium",
                        "discount_type": "fixed",
                        "campaign_price_amount": "8000",
                    },
                ],
                "start_at": "2026-04-10 00:00:00",
                "end_at": "2026-04-20 23:59:00",
            },
        )
        create_payload = create_response.get_json(force=True)
        assert create_payload["code"] == 0
        created_campaign_bid = create_payload["data"]["campaign"]["campaign_bid"]

        with app.app_context():
            dao.db.session.add(
                BillingOrder(
                    bill_order_bid="order-campaign-hit",
                    creator_bid="creator-1",
                    order_type=BILLING_ORDER_TYPE_TOPUP,
                    product_bid="bill-product-topup-small",
                    subscription_bid="",
                    currency="CNY",
                    payable_amount=4000,
                    paid_amount=4000,
                    payment_provider="pingxx",
                    channel="alipay_qr",
                    provider_reference_id="charge_campaign_hit",
                    status=BILLING_ORDER_STATUS_PAID,
                    campaign_bid=created_campaign_bid,
                    campaign_benefit_type=BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
                    created_at=datetime(2026, 4, 11, 8, 0, 0),
                )
            )
            dao.db.session.commit()

        update_response = client.post(
            f"/api/admin/billing/campaigns/{created_campaign_bid}",
            json={
                "name": "Hit locked discount",
                "note": "rule drift attempt",
                "product_type": "topup",
                "benefit_type": "discount",
                "products": [
                    {
                        "product_bid": "bill-product-topup-small",
                        "discount_type": "fixed",
                        "campaign_price_amount": "4000",
                    },
                    {
                        "product_bid": "bill-product-topup-medium",
                        "discount_type": "fixed",
                        "campaign_price_amount": "7000",
                    },
                ],
                "start_at": "2026-04-10 00:00:00",
                "end_at": "2026-04-20 23:59:00",
            },
        )
        update_payload = update_response.get_json(force=True)

        assert update_payload["code"] == 7117
        assert (
            update_payload["message"]
            == _translations["en-US"]["server.billing.campaignLockedAfterHit"]
        )

    def test_admin_billing_routes_require_creator(self, admin_billing_client) -> None:
        client = admin_billing_client["client"]

        response = client.get(
            "/api/admin/billing/subscriptions",
            headers={"X-Creator": "0"},
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 401
        assert payload["message"] == _translations["en-US"]["server.shifu.noPermission"]

    def test_admin_billing_public_builders_return_dto_instances(
        self,
        admin_billing_client,
    ) -> None:
        app = admin_billing_client["app"]

        results = {
            "subscriptions": build_admin_bill_subscriptions_page(app),
            "domain_audits": build_admin_billing_domain_audits_page(app),
            "entitlements": build_admin_bill_entitlements_page(app),
            "orders": build_admin_bill_orders_page(app),
            "campaign_product_options": build_admin_billing_campaign_product_options(
                app
            ),
            "campaigns": build_admin_billing_campaigns_page(app),
            "usage_daily": build_admin_bill_daily_usage_metrics_page(app),
            "ledger_daily": build_admin_bill_daily_ledger_summary_page(app),
            "adjust": adjust_admin_billing_ledger(
                app,
                operator_user_bid="admin-creator",
                payload={
                    "creator_bid": "creator-1",
                    "amount": "1.5000000000",
                    "note": "contract-check",
                },
            ),
        }

        assert isinstance(results["subscriptions"], BillingSubscriptionsPageDTO)
        assert isinstance(results["domain_audits"], BillingDomainAuditsPageDTO)
        assert isinstance(results["entitlements"], BillingEntitlementsPageDTO)
        assert isinstance(results["orders"], AdminBillingOrdersPageDTO)
        assert isinstance(
            results["campaign_product_options"],
            AdminBillingCampaignProductOptionsDTO,
        )
        assert isinstance(results["campaigns"], AdminBillingCampaignsPageDTO)
        assert isinstance(
            results["usage_daily"],
            AdminBillingDailyUsageMetricsPageDTO,
        )
        assert isinstance(
            results["ledger_daily"],
            AdminBillingDailyLedgerSummaryPageDTO,
        )
        assert isinstance(results["adjust"], BillingLedgerAdjustResultDTO)

        for value in results.values():
            assert not isinstance(value, dict)
            assert not isinstance(value, list)
            assert isinstance(value.__json__(), dict)

    def test_admin_billing_campaign_detail_builder_returns_dto_instance(
        self,
        admin_billing_client,
    ) -> None:
        app = admin_billing_client["app"]

        with app.app_context():
            dao.db.session.add(
                BillingCampaign(
                    campaign_bid="campaign-builder-1",
                    name="Builder Campaign",
                    note="",
                    benefit_type=BILLING_CAMPAIGN_BENEFIT_TYPE_BONUS,
                    discount_type=0,
                    discount_amount=0,
                    discount_percent=Decimal("0"),
                    bonus_credit_amount=Decimal("12"),
                    enabled=1,
                    start_at=datetime(2026, 4, 10, 0, 0, 0),
                    end_at=datetime(2026, 4, 20, 23, 59, 0),
                    created_user_bid="admin-creator",
                    updated_user_bid="admin-creator",
                )
            )
            dao.db.session.add(
                BillingCampaignProduct(
                    campaign_bid="campaign-builder-1",
                    product_bid="bill-product-plan-monthly",
                    product_type=BILLING_PRODUCT_TYPE_PLAN,
                )
            )
            dao.db.session.commit()

        detail = build_admin_billing_campaign_detail(app, "campaign-builder-1")

        assert isinstance(detail, AdminBillingCampaignDetailDTO)
        assert detail.campaign.campaign_bid == "campaign-builder-1"
