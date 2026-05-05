from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from flask import Flask, jsonify, request
import pytest

import flaskr.common.config as common_config
import flaskr.dao as dao
from flaskr.i18n import load_translations, set_language
from flaskr.service.billing.consts import (
    ALLOCATION_INTERVAL_PER_CYCLE,
    BILLING_INTERVAL_DAY,
    BILLING_MODE_RECURRING,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    BILLING_ORDER_TYPE_TOPUP,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_GIFT,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_TRIAL_PRODUCT_BID,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingProduct,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.provider_state import (
    apply_billing_subscription_provider_update,
)
from flaskr.service.billing.queries import calculate_billing_cycle_end
from flaskr.service.billing.subscriptions import (
    grant_paid_order_credits,
    repair_topup_grant_expiries,
    sync_subscription_lifecycle_events,
)
from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.order.models import PingxxOrder, StripeOrder
from flaskr.service.order.payment_providers import (
    PaymentCreationResult,
    PaymentNotificationResult,
    PaymentRefundResult,
    SubscriptionUpdateResult,
)
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.repository import create_user_entity
from tests.common.fixtures.bill_products import build_bill_products
from tests.service.billing.route_loader import (
    load_billing_routes_module,
    load_register_billing_routes,
)

register_billing_routes = load_register_billing_routes()
billing_write_routes_module = load_billing_routes_module()


def _reset_config_cache(*keys: str) -> None:
    for key in keys:
        common_config.__ENHANCED_CONFIG__._cache.pop(key, None)  # noqa: SLF001


def _add_active_subscription(
    app: Flask,
    *,
    creator_bid: str = "creator-1",
    subscription_bid: str = "sub-topup-active-default",
    current_period_start_at: datetime | None = None,
    current_period_end_at: datetime | None = None,
) -> None:
    now = datetime.now()
    with app.app_context():
        dao.db.session.add(
            BillingSubscription(
                subscription_bid=subscription_bid,
                creator_bid=creator_bid,
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id=f"provider-{subscription_bid}",
                provider_customer_id=f"customer-{subscription_bid}",
                current_period_start_at=current_period_start_at
                or now - timedelta(days=1),
                current_period_end_at=current_period_end_at or now + timedelta(days=29),
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=current_period_start_at or now - timedelta(days=1),
                updated_at=current_period_start_at or now - timedelta(days=1),
            )
        )
        dao.db.session.commit()


def _seed_creator_user(app: Flask, *, creator_bid: str = "creator-1") -> None:
    with app.app_context():
        entity = create_user_entity(
            user_bid=creator_bid,
            identify=f"{creator_bid}@example.com",
            nickname="Creator",
            language="en-US",
            avatar="",
            state=USER_STATE_REGISTERED,
        )
        entity.is_creator = 1
        dao.db.session.commit()


def _add_trial_subscription_state(
    app: Flask,
    *,
    creator_bid: str = "creator-1",
    subscription_bid: str = "sub-trial-default",
    bill_order_bid: str = "bill-trial-default",
    wallet_bid: str = "wallet-trial-default",
    wallet_bucket_bid: str = "bucket-trial-default",
    ledger_bid: str = "ledger-trial-default",
    current_period_start_at: datetime | None = None,
    current_period_end_at: datetime | None = None,
    credit_amount: Decimal = Decimal("100.0000000000"),
) -> None:
    now = datetime.now()
    trial_start = current_period_start_at or now - timedelta(minutes=5)
    trial_end = current_period_end_at or now + timedelta(days=15)
    with app.app_context():
        dao.db.session.add(
            BillingSubscription(
                subscription_bid=subscription_bid,
                creator_bid=creator_bid,
                product_bid=BILLING_TRIAL_PRODUCT_BID,
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="manual",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=trial_start,
                current_period_end_at=trial_end,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={"trial_bootstrap": True},
                created_at=trial_start,
                updated_at=trial_start,
            )
        )
        dao.db.session.add(
            CreditWallet(
                wallet_bid=wallet_bid,
                creator_bid=creator_bid,
                available_credits=credit_amount,
                reserved_credits=Decimal("0"),
                lifetime_granted_credits=credit_amount,
                lifetime_consumed_credits=Decimal("0"),
                last_settled_usage_id=0,
                version=0,
                created_at=trial_start,
                updated_at=trial_start,
            )
        )
        dao.db.session.add(
            BillingOrder(
                bill_order_bid=bill_order_bid,
                creator_bid=creator_bid,
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                product_bid=BILLING_TRIAL_PRODUCT_BID,
                subscription_bid=subscription_bid,
                currency="CNY",
                payable_amount=0,
                paid_amount=0,
                payment_provider="manual",
                channel="manual",
                provider_reference_id="",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=trial_start,
                metadata_json={"checkout_type": "trial_bootstrap"},
                created_at=trial_start,
                updated_at=trial_start,
            )
        )
        dao.db.session.add(
            CreditWalletBucket(
                wallet_bucket_bid=wallet_bucket_bid,
                wallet_bid=wallet_bid,
                creator_bid=creator_bid,
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid=bill_order_bid,
                priority=20,
                original_credits=credit_amount,
                available_credits=credit_amount,
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("0"),
                expired_credits=Decimal("0"),
                effective_from=trial_start,
                effective_to=trial_end,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={
                    "bill_order_bid": bill_order_bid,
                    "product_bid": BILLING_TRIAL_PRODUCT_BID,
                    "subscription_bid": subscription_bid,
                    "payment_provider": "manual",
                },
                created_at=trial_start,
                updated_at=trial_start,
            )
        )
        dao.db.session.add(
            CreditLedgerEntry(
                ledger_bid=ledger_bid,
                creator_bid=creator_bid,
                wallet_bid=wallet_bid,
                wallet_bucket_bid=wallet_bucket_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid=bill_order_bid,
                idempotency_key=f"grant:{bill_order_bid}",
                amount=credit_amount,
                balance_after=credit_amount,
                expires_at=trial_end,
                consumable_from=trial_start,
                metadata_json={
                    "bill_order_bid": bill_order_bid,
                    "product_bid": BILLING_TRIAL_PRODUCT_BID,
                    "subscription_bid": subscription_bid,
                    "payment_provider": "manual",
                    "grant_reason": "subscription",
                },
                created_at=trial_start,
                updated_at=trial_start,
            )
        )
        dao.db.session.commit()


@pytest.fixture
def billing_write_client(monkeypatch):
    monkeypatch.setenv("HOST_URL", "https://billing.example.com")
    monkeypatch.setenv("PATH_PREFIX", "/api")
    _reset_config_cache("HOST_URL", "PATH_PREFIX")

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
    load_translations(app)

    dao.db.init_app(app)

    stripe_requests: list[dict] = []
    pingxx_requests: list[dict] = []
    refund_requests: list[dict] = []

    class FakeStripeProvider:
        def create_payment(self, *, request, app):
            stripe_requests.append(
                {
                    "order_bid": request.order_bid,
                    "channel": request.channel,
                    "subject": request.subject,
                    "body": request.body,
                    "extra": request.extra,
                }
            )
            return PaymentCreationResult(
                provider_reference="cs_billing_test",
                raw_response={
                    "id": "cs_billing_test",
                    "url": "https://stripe.test/checkout",
                },
                checkout_session_id="cs_billing_test",
                extra={"url": "https://stripe.test/checkout"},
            )

        def create_subscription(self, *, request, app):
            return self.create_payment(request=request, app=app)

        def sync_reference(self, *, provider_reference: str, reference_type: str, app):
            assert reference_type == "checkout_session"
            return PaymentNotificationResult(
                order_bid="",
                status="manual_sync",
                provider_payload={
                    "checkout_session": {
                        "id": provider_reference,
                        "status": "complete",
                        "payment_status": "paid",
                        "payment_intent": "pi_billing_test",
                        "subscription": "sub_provider_test",
                        "customer": "cus_provider_test",
                    },
                    "payment_intent": {
                        "id": "pi_billing_test",
                        "status": "succeeded",
                    },
                },
                charge_id=None,
            )

        def cancel_subscription(
            self, *, subscription_bid: str, provider_subscription_id: str, app
        ):
            return SubscriptionUpdateResult(
                provider_reference=provider_subscription_id,
                raw_response={
                    "id": provider_subscription_id,
                    "subscription_bid": subscription_bid,
                    "cancel_at_period_end": True,
                    "status": "active",
                },
                status="active",
                extra={"cancel_at_period_end": True},
            )

        def resume_subscription(
            self, *, subscription_bid: str, provider_subscription_id: str, app
        ):
            return SubscriptionUpdateResult(
                provider_reference=provider_subscription_id,
                raw_response={
                    "id": provider_subscription_id,
                    "subscription_bid": subscription_bid,
                    "cancel_at_period_end": False,
                    "status": "active",
                },
                status="active",
                extra={"cancel_at_period_end": False},
            )

        def refund_payment(self, *, request, app):
            refund_requests.append(
                {
                    "order_bid": request.order_bid,
                    "amount": request.amount,
                    "reason": request.reason,
                    "metadata": request.metadata,
                }
            )
            return PaymentRefundResult(
                provider_reference="re_billing_test",
                raw_response={"id": "re_billing_test", "status": "succeeded"},
                status="succeeded",
            )

    class FakePingxxProvider:
        def create_payment(self, *, request, app):
            pingxx_requests.append(
                {
                    "order_bid": request.order_bid,
                    "channel": request.channel,
                    "subject": request.subject,
                    "body": request.body,
                    "extra": request.extra,
                }
            )
            return PaymentCreationResult(
                provider_reference="ch_billing_test",
                raw_response={"id": "ch_billing_test", "paid": False},
                extra={"credential": {"alipay_qr": "https://pingxx.test/qr"}},
            )

        def sync_reference(self, *, provider_reference: str, reference_type: str, app):
            assert reference_type == "charge"
            return PaymentNotificationResult(
                order_bid="",
                status="manual_sync",
                provider_payload={"charge": {"id": provider_reference, "paid": True}},
                charge_id=provider_reference,
            )

    def _fake_get_payment_provider(channel: str):
        if channel == "stripe":
            return FakeStripeProvider()
        if channel == "pingxx":
            return FakePingxxProvider()
        raise AssertionError(f"Unexpected provider: {channel}")

    monkeypatch.setattr(
        "flaskr.service.billing.checkout.get_payment_provider",
        _fake_get_payment_provider,
    )
    monkeypatch.setattr(
        "flaskr.service.billing.subscriptions.get_payment_provider",
        _fake_get_payment_provider,
    )
    monkeypatch.setattr(
        billing_write_routes_module,
        "is_billing_enabled",
        lambda: True,
    )

    @app.errorhandler(AppException)
    def _handle_app_exception(error: AppException):
        response = jsonify({"code": error.code, "message": error.message})
        response.status_code = 200
        return response

    @app.before_request
    def _inject_request_user() -> None:
        request.user = SimpleNamespace(
            user_id=request.headers.get("X-User-Id", "creator-1"),
            language=request.headers.get("X-Language", "en-US"),
            is_creator=request.headers.get("X-Creator", "1") == "1",
        )
        set_language(request.user.language)

    register_billing_routes(app=app)

    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(build_bill_products())
        dao.db.session.commit()

        with app.test_client() as client:
            yield {
                "client": client,
                "app": app,
                "stripe_requests": stripe_requests,
                "pingxx_requests": pingxx_requests,
                "refund_requests": refund_requests,
            }

        dao.db.session.remove()
        dao.db.drop_all()
        _reset_config_cache("HOST_URL", "PATH_PREFIX")


class TestBillingWriteRoutes:
    def test_subscription_checkout_rejects_when_billing_feature_disabled(
        self, billing_write_client, monkeypatch
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
        self, billing_write_client, monkeypatch
    ) -> None:
        client = billing_write_client["client"]

        def fake_get_config(key, default=None):
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
        self, billing_write_client
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

    def test_subscription_checkout_supports_daily_stripe_recurring_interval(
        self, billing_write_client
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

    def test_subscription_checkout_rejects_lower_tier_plan_while_active(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = datetime.now()

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
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = datetime.now()

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
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = datetime.now()

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
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = datetime.now()

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

    def test_pingxx_subscription_checkout_and_sync_grant_initial_credits(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
            },
            headers={"X-Language": "zh-CN"},
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        assert checkout["code"] == 0
        assert checkout["data"]["provider"] == "pingxx"
        assert checkout["data"]["status"] == "pending"
        assert checkout["data"]["payment_mode"] == "subscription"
        assert checkout["data"]["payment_payload"]["credential"]["alipay_qr"] == (
            "https://pingxx.test/qr"
        )
        assert billing_write_client["pingxx_requests"][0]["subject"] == "月套餐·轻量版"
        assert billing_write_client["pingxx_requests"][0]["body"] == "月套餐·轻量版"

        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1"
            ).one()
            raw_order = PingxxOrder.query.filter_by(
                biz_domain="billing",
                bill_order_bid=bill_order_bid,
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PENDING
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_DRAFT
            assert subscription.billing_provider == "pingxx"
            assert subscription.provider_subscription_id == ""
            assert raw_order.status == 0
            assert raw_order.order_bid == ""
            assert raw_order.creator_bid == "creator-1"

        sync = client.post(f"/api/billing/orders/{bill_order_bid}/sync").get_json(
            force=True
        )
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1"
            ).one()
            product = BillingProduct.query.filter_by(
                product_bid=order.product_bid
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            raw_order = PingxxOrder.query.filter_by(
                biz_domain="billing",
                bill_order_bid=bill_order_bid,
            ).one()
            renewal_event = BillingRenewalEvent.query.filter_by(
                subscription_bid=subscription.subscription_bid,
                event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            ).one()
            expire_event = BillingRenewalEvent.query.filter_by(
                subscription_bid=subscription.subscription_bid,
                event_type=BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PAID
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert subscription.provider_subscription_id == ""
            assert wallet.available_credits == 5
            assert bucket.bucket_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
            assert bucket.source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION
            assert subscription.current_period_start_at == order.paid_at
            assert bucket.effective_from == order.paid_at
            assert subscription.current_period_end_at == calculate_billing_cycle_end(
                product,
                cycle_start_at=order.paid_at,
            )
            assert bucket.effective_to == subscription.current_period_end_at
            assert raw_order.status == 1
            assert raw_order.charge_id == "ch_billing_test"
            assert (
                PingxxOrder.query.filter_by(
                    biz_domain="billing",
                    bill_order_bid=bill_order_bid,
                ).count()
                == 1
            )
            assert renewal_event.scheduled_at == (
                subscription.current_period_end_at - timedelta(days=7)
            )
            assert expire_event.scheduled_at == subscription.current_period_end_at

    def test_pending_pingxx_subscription_order_can_refresh_checkout(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]

        checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
            },
            headers={"X-Language": "zh-CN"},
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        refreshed = client.post(
            f"/api/billing/orders/{bill_order_bid}/checkout",
            headers={"X-Language": "zh-CN"},
        ).get_json(force=True)

        assert refreshed["code"] == 0
        assert refreshed["data"]["provider"] == "pingxx"
        assert refreshed["data"]["payment_mode"] == "subscription"
        assert refreshed["data"]["status"] == "pending"
        assert refreshed["data"]["payment_payload"]["credential"]["alipay_qr"] == (
            "https://pingxx.test/qr"
        )
        assert len(billing_write_client["pingxx_requests"]) == 2
        assert billing_write_client["pingxx_requests"][1]["order_bid"] == bill_order_bid
        assert billing_write_client["pingxx_requests"][1]["subject"] == "月套餐·轻量版"
        assert billing_write_client["pingxx_requests"][1]["body"] == "月套餐·轻量版"

    def test_pingxx_wechat_subscription_checkout_aligns_legacy_charge_extra(
        self, billing_write_client, monkeypatch
    ) -> None:
        client = billing_write_client["client"]

        def fake_get_config(key, default=None):
            if key == "PINGXX_APP_ID":
                return "app_billing_test"
            return default

        monkeypatch.setattr(
            "flaskr.service.billing.checkout.get_config",
            fake_get_config,
        )

        checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
                "channel": "wx_pub_qr",
            },
        ).get_json(force=True)

        assert checkout["code"] == 0
        request = billing_write_client["pingxx_requests"][0]
        assert request["channel"] == "wx_pub_qr"
        assert request["extra"]["app_id"] == "app_billing_test"
        assert request["extra"]["charge_extra"] == {
            "product_id": "bill-product-plan-monthly"
        }

    def test_topup_checkout_and_sync_mark_order_paid(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        _add_active_subscription(app, subscription_bid="sub-topup-paid-1")

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
            headers={"X-Language": "zh-CN"},
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        assert checkout["data"]["status"] == "pending"
        assert checkout["data"]["payment_payload"]["credential"]["alipay_qr"] == (
            "https://pingxx.test/qr"
        )
        assert billing_write_client["pingxx_requests"][0]["subject"] == "20 积分包"
        assert billing_write_client["pingxx_requests"][0]["body"] == "20 积分包"

        sync = client.post(f"/api/billing/orders/{bill_order_bid}/sync").get_json(
            force=True
        )
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            raw_order = PingxxOrder.query.filter_by(
                biz_domain="billing",
                bill_order_bid=bill_order_bid,
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PAID
            assert order.paid_at is not None
            assert wallet.available_credits == 20
            assert wallet.reserved_credits == Decimal("0E-10")
            assert bucket.bucket_category == CREDIT_BUCKET_CATEGORY_TOPUP
            assert bucket.source_type == CREDIT_SOURCE_TYPE_TOPUP
            assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
            assert bucket.available_credits == 20
            assert ledger.amount == 20
            assert ledger.wallet_bucket_bid == bucket.wallet_bucket_bid
            assert raw_order.status == 1
            assert raw_order.charge_id == "ch_billing_test"
            assert (
                PingxxOrder.query.filter_by(
                    biz_domain="billing",
                    bill_order_bid=bill_order_bid,
                ).count()
                == 1
            )

    def test_topup_grant_expires_with_current_subscription_period(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        now = datetime.now()
        current_period_start_at = now - timedelta(days=3)
        current_period_end_at = now + timedelta(days=27)
        _add_active_subscription(
            app,
            subscription_bid="sub-topup-active-1",
            current_period_start_at=current_period_start_at,
            current_period_end_at=current_period_end_at,
        )

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        sync = client.post(f"/api/billing/orders/{bill_order_bid}/sync").get_json(
            force=True
        )
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            assert bucket.effective_to == current_period_end_at
            assert ledger.expires_at == current_period_end_at

    def test_repeated_topup_reuses_single_bucket_and_tracks_latest_source(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        current_period_end_at = datetime.now() + timedelta(days=30)
        _add_active_subscription(
            app,
            subscription_bid="sub-topup-repeat-1",
            current_period_end_at=current_period_end_at,
        )

        first_checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)
        first_order_bid = first_checkout["data"]["bill_order_bid"]
        first_sync = client.post(
            f"/api/billing/orders/{first_order_bid}/sync"
        ).get_json(force=True)

        with app.app_context():
            initial_bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=first_order_bid,
            ).one()
            initial_bucket_bid = initial_bucket.wallet_bucket_bid

        second_checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)
        second_order_bid = second_checkout["data"]["bill_order_bid"]
        second_sync = client.post(
            f"/api/billing/orders/{second_order_bid}/sync"
        ).get_json(force=True)

        assert first_sync["code"] == 0
        assert second_sync["code"] == 0

        with app.app_context():
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            topup_buckets = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            ).all()
            second_ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=second_order_bid,
            ).one()

            assert len(topup_buckets) == 1
            assert topup_buckets[0].wallet_bucket_bid == initial_bucket_bid
            assert topup_buckets[0].source_bid == second_order_bid
            assert topup_buckets[0].available_credits == 40
            assert topup_buckets[0].effective_to == current_period_end_at
            assert wallet.available_credits == 40
            assert second_ledger.wallet_bucket_bid == initial_bucket_bid
            assert second_ledger.expires_at == current_period_end_at

    def test_trial_then_paid_then_topup_prefers_paid_subscription_for_overview_and_expiry(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        _seed_creator_user(app, creator_bid="creator-1")
        _add_trial_subscription_state(
            app,
            subscription_bid="sub-trial-paid-then-topup",
            bill_order_bid="bill-trial-paid-then-topup",
            wallet_bid="wallet-trial-paid-then-topup",
            wallet_bucket_bid="bucket-trial-paid-then-topup",
            ledger_bid="ledger-trial-paid-then-topup",
        )

        paid_checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "pingxx",
            },
        ).get_json(force=True)
        paid_order_bid = paid_checkout["data"]["bill_order_bid"]
        paid_sync = client.post(f"/api/billing/orders/{paid_order_bid}/sync").get_json(
            force=True
        )
        with app.app_context():
            paid_subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
            ).one()
            paid_subscription.current_period_end_at = (
                paid_subscription.current_period_start_at + timedelta(days=1)
            )
            dao.db.session.commit()

        topup_checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)
        topup_order_bid = topup_checkout["data"]["bill_order_bid"]
        topup_sync = client.post(
            f"/api/billing/orders/{topup_order_bid}/sync"
        ).get_json(force=True)
        overview = client.get("/api/billing/overview").get_json(force=True)

        assert paid_sync["code"] == 0
        assert topup_sync["code"] == 0
        assert overview["code"] == 0

        with app.app_context():
            paid_subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
            ).one()
            subscription_buckets = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            ).all()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=topup_order_bid,
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=topup_order_bid,
            ).one()

            assert paid_subscription.current_period_end_at is not None
            assert (
                BillingSubscription.query.filter_by(creator_bid="creator-1").count()
                == 1
            )
            assert len(subscription_buckets) == 1
            assert subscription_buckets[0].source_bid == paid_order_bid
            assert subscription_buckets[0].available_credits == Decimal(
                "105.0000000000"
            )
            assert bucket.effective_to == paid_subscription.current_period_end_at
            assert ledger.expires_at == paid_subscription.current_period_end_at

        assert (
            overview["data"]["subscription"]["subscription_bid"]
            == paid_subscription.subscription_bid
        )
        assert (
            overview["data"]["subscription"]["product_bid"]
            == "bill-product-plan-monthly"
        )

    def test_trial_then_topup_then_paid_realigns_existing_topup_expiry(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        _seed_creator_user(app, creator_bid="creator-1")
        _add_trial_subscription_state(
            app,
            subscription_bid="sub-trial-topup-then-paid",
            bill_order_bid="bill-trial-topup-then-paid",
            wallet_bid="wallet-trial-topup-then-paid",
            wallet_bucket_bid="bucket-trial-topup-then-paid",
            ledger_bid="ledger-trial-topup-then-paid",
        )
        with app.app_context():
            trial_subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-trial-topup-then-paid"
            ).one()
            trial_end = trial_subscription.current_period_end_at

        topup_checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)
        topup_order_bid = topup_checkout["data"]["bill_order_bid"]
        topup_sync = client.post(
            f"/api/billing/orders/{topup_order_bid}/sync"
        ).get_json(force=True)

        assert topup_sync["code"] == 0

        with app.app_context():
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=topup_order_bid,
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=topup_order_bid,
            ).one()
            assert bucket.effective_to == trial_end
            assert ledger.expires_at == trial_end

        paid_checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)
        paid_order_bid = paid_checkout["data"]["bill_order_bid"]
        paid_sync = client.post(f"/api/billing/orders/{paid_order_bid}/sync").get_json(
            force=True
        )

        assert paid_sync["code"] == 0

        with app.app_context():
            paid_subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
            ).one()
            subscription_buckets = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            ).all()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=topup_order_bid,
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=topup_order_bid,
            ).one()

            assert paid_subscription.current_period_end_at is not None
            assert (
                BillingSubscription.query.filter_by(creator_bid="creator-1").count()
                == 1
            )
            assert len(subscription_buckets) == 1
            assert subscription_buckets[0].source_bid == paid_order_bid
            assert subscription_buckets[0].available_credits == Decimal(
                "105.0000000000"
            )
            assert bucket.effective_to == paid_subscription.current_period_end_at
            assert ledger.expires_at == paid_subscription.current_period_end_at
            assert bucket.effective_to != trial_end

    def test_topup_checkout_rejects_without_active_subscription(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)

        assert checkout["code"] != 0

    def test_repair_topup_grant_expiries_updates_only_misaligned_expiry_fields(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]
        now = datetime(2026, 4, 17, 12, 0, 0)
        trial_end = now + timedelta(days=15)
        paid_end = now + timedelta(days=1)
        topup_paid_at = now + timedelta(minutes=5)

        with app.app_context():
            wallet = CreditWallet(
                wallet_bid="wallet-repair-1",
                creator_bid="creator-1",
                available_credits=Decimal("20.0000000000"),
                reserved_credits=Decimal("0"),
                lifetime_granted_credits=Decimal("20.0000000000"),
                lifetime_consumed_credits=Decimal("0"),
                last_settled_usage_id=0,
                version=0,
                created_at=now,
                updated_at=now,
            )
            dao.db.session.add(wallet)
            dao.db.session.add_all(
                [
                    BillingSubscription(
                        subscription_bid="sub-trial-repair",
                        creator_bid="creator-1",
                        product_bid=BILLING_TRIAL_PRODUCT_BID,
                        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                        billing_provider="manual",
                        provider_subscription_id="",
                        provider_customer_id="",
                        current_period_start_at=now,
                        current_period_end_at=trial_end,
                        cancel_at_period_end=0,
                        next_product_bid="",
                        metadata_json={"trial": True},
                        created_at=now,
                        updated_at=now,
                    ),
                    BillingSubscription(
                        subscription_bid="sub-paid-repair",
                        creator_bid="creator-1",
                        product_bid="bill-product-plan-monthly",
                        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                        billing_provider="stripe",
                        provider_subscription_id="sub_provider_repair",
                        provider_customer_id="cus_provider_repair",
                        current_period_start_at=now,
                        current_period_end_at=paid_end,
                        cancel_at_period_end=0,
                        next_product_bid="",
                        metadata_json={},
                        created_at=now,
                        updated_at=now,
                    ),
                    BillingOrder(
                        bill_order_bid="bill-topup-repair-1",
                        creator_bid="creator-1",
                        order_type=BILLING_ORDER_TYPE_TOPUP,
                        product_bid="bill-product-topup-small",
                        subscription_bid="",
                        currency="CNY",
                        payable_amount=5000,
                        paid_amount=5000,
                        payment_provider="pingxx",
                        channel="alipay_qr",
                        provider_reference_id="ch_topup_repair_1",
                        status=BILLING_ORDER_STATUS_PAID,
                        paid_at=topup_paid_at,
                        metadata_json={"checkout_type": "topup"},
                        created_at=topup_paid_at,
                        updated_at=topup_paid_at,
                    ),
                    CreditWalletBucket(
                        wallet_bucket_bid="bucket-topup-repair-1",
                        wallet_bid="wallet-repair-1",
                        creator_bid="creator-1",
                        bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
                        source_type=CREDIT_SOURCE_TYPE_TOPUP,
                        source_bid="bill-topup-repair-1",
                        priority=30,
                        original_credits=Decimal("20.0000000000"),
                        available_credits=Decimal("20.0000000000"),
                        reserved_credits=Decimal("0"),
                        consumed_credits=Decimal("0"),
                        expired_credits=Decimal("0"),
                        effective_from=topup_paid_at,
                        effective_to=trial_end,
                        status=CREDIT_BUCKET_STATUS_ACTIVE,
                        metadata_json={"bill_order_bid": "bill-topup-repair-1"},
                        created_at=topup_paid_at,
                        updated_at=topup_paid_at,
                    ),
                    CreditLedgerEntry(
                        ledger_bid="ledger-topup-repair-1",
                        creator_bid="creator-1",
                        wallet_bid="wallet-repair-1",
                        wallet_bucket_bid="bucket-topup-repair-1",
                        entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                        source_type=CREDIT_SOURCE_TYPE_TOPUP,
                        source_bid="bill-topup-repair-1",
                        idempotency_key="grant:bill-topup-repair-1",
                        amount=Decimal("20.0000000000"),
                        balance_after=Decimal("20.0000000000"),
                        expires_at=trial_end,
                        consumable_from=topup_paid_at,
                        metadata_json={"bill_order_bid": "bill-topup-repair-1"},
                        created_at=topup_paid_at,
                        updated_at=topup_paid_at,
                    ),
                ]
            )
            dao.db.session.commit()

            result = repair_topup_grant_expiries(app, creator_bid="creator-1")

            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-topup-repair-1"
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                ledger_bid="ledger-topup-repair-1"
            ).one()

            assert result.status == "repaired"
            assert result.inspected_bucket_count == 1
            assert result.repaired_bucket_count == 1
            assert result.repaired_ledger_count == 1
            assert result.skipped_bucket_bids == []
            assert bucket.effective_to == paid_end
            assert ledger.expires_at == paid_end
            assert wallet.available_credits == Decimal("20.0000000000")
            assert wallet.reserved_credits == Decimal("0E-10")
            assert wallet.version == 0

    def test_topup_checkout_uses_pingxx_default_channel_when_provider_omitted(
        self, billing_write_client, monkeypatch
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        _add_active_subscription(app, subscription_bid="sub-topup-default-provider-1")

        def fake_get_config(key, default=None):
            if key == "PAYMENT_CHANNELS_ENABLED":
                return "pingxx"
            return default

        monkeypatch.setattr(
            "flaskr.service.order.payment_channel_resolution.get_config",
            fake_get_config,
        )

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
            },
        ).get_json(force=True)

        assert checkout["code"] == 0
        assert checkout["data"]["provider"] == "pingxx"
        assert checkout["data"]["status"] == "pending"
        assert checkout["data"]["payment_payload"]["credential"]["alipay_qr"] == (
            "https://pingxx.test/qr"
        )
        assert billing_write_client["pingxx_requests"][0]["channel"] == "alipay_qr"

    def test_topup_sync_rebuilds_wallet_snapshot_from_bucket_balances(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        _add_active_subscription(app, subscription_bid="sub-topup-rebuild-1")

        with app.app_context():
            dao.db.session.add(
                CreditWallet(
                    wallet_bid="wallet-creator-1",
                    creator_bid="creator-1",
                    available_credits=Decimal("999.0000000000"),
                    reserved_credits=Decimal("0"),
                    lifetime_granted_credits=Decimal("100.0000000000"),
                    lifetime_consumed_credits=Decimal("0"),
                    last_settled_usage_id=0,
                    version=0,
                    created_at=datetime(2026, 4, 1, 0, 0, 0),
                    updated_at=datetime(2026, 4, 1, 0, 0, 0),
                )
            )
            dao.db.session.add(
                CreditWalletBucket(
                    wallet_bucket_bid="bucket-existing-free",
                    wallet_bid="wallet-creator-1",
                    creator_bid="creator-1",
                    bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
                    source_type=CREDIT_SOURCE_TYPE_GIFT,
                    source_bid="gift-existing",
                    priority=10,
                    original_credits=Decimal("100.0000000000"),
                    available_credits=Decimal("100.0000000000"),
                    reserved_credits=Decimal("0"),
                    consumed_credits=Decimal("0"),
                    expired_credits=Decimal("0"),
                    effective_from=datetime(2026, 4, 1, 0, 0, 0),
                    effective_to=None,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    metadata_json={},
                    created_at=datetime(2026, 4, 1, 0, 0, 0),
                    updated_at=datetime(2026, 4, 1, 0, 0, 0),
                )
            )
            dao.db.session.commit()

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        sync = client.post(f"/api/billing/orders/{bill_order_bid}/sync").get_json(
            force=True
        )
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            new_bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            raw_order = StripeOrder.query.filter_by(
                biz_domain="billing",
                bill_order_bid=bill_order_bid,
            ).one()
            assert wallet.available_credits == Decimal("120.0000000000")
            assert wallet.reserved_credits == Decimal("0E-10")
            assert new_bucket.bucket_category == CREDIT_BUCKET_CATEGORY_TOPUP
            assert new_bucket.source_type == CREDIT_SOURCE_TYPE_TOPUP
            assert new_bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
            assert raw_order.status == 1
            assert raw_order.checkout_session_id == "cs_billing_test"
            assert raw_order.payment_intent_id == "pi_billing_test"

    def test_subscription_checkout_and_sync_grant_initial_credits(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "bill-product-plan-monthly",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        sync = client.post(f"/api/billing/orders/{bill_order_bid}/sync").get_json(
            force=True
        )
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1"
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=bill_order_bid,
            ).one()
            raw_order = StripeOrder.query.filter_by(
                biz_domain="billing",
                bill_order_bid=bill_order_bid,
            ).one()
            renewal_event = BillingRenewalEvent.query.filter_by(
                subscription_bid=subscription.subscription_bid,
                event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PAID
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert subscription.provider_subscription_id == "sub_provider_test"
            assert wallet.available_credits == 5
            assert bucket.bucket_category == CREDIT_BUCKET_CATEGORY_SUBSCRIPTION
            assert bucket.source_type == CREDIT_SOURCE_TYPE_SUBSCRIPTION
            assert bucket.status == CREDIT_BUCKET_STATUS_ACTIVE
            assert bucket.available_credits == 5
            assert ledger.amount == 5
            assert raw_order.status == 1
            assert raw_order.checkout_session_id == "cs_billing_test"
            assert raw_order.payment_intent_id == "pi_billing_test"
            assert (
                StripeOrder.query.filter_by(
                    biz_domain="billing",
                    bill_order_bid=bill_order_bid,
                ).count()
                == 1
            )
            assert renewal_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
            assert renewal_event.scheduled_at == subscription.current_period_end_at

    def test_cancel_and_resume_subscription_toggle_status(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        with app.app_context():
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-active",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-monthly",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="stripe",
                    provider_subscription_id="sub_provider_1",
                    provider_customer_id="cus_provider_1",
                    current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
                    current_period_end_at=datetime(2026, 5, 1, 0, 0, 0),
                    cancel_at_period_end=0,
                    next_product_bid="",
                    metadata_json={},
                    created_at=datetime(2026, 4, 8, 12, 0, 0),
                    updated_at=datetime(2026, 4, 8, 12, 0, 0),
                )
            )
            dao.db.session.commit()

        cancel_payload = client.post(
            "/api/billing/subscriptions/cancel",
            json={"subscription_bid": "sub-active"},
        ).get_json(force=True)
        assert cancel_payload["code"] == 0
        assert cancel_payload["data"]["status"] == "cancel_scheduled"
        assert cancel_payload["data"]["cancel_at_period_end"] is True

        with app.app_context():
            cancel_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-active",
                event_type=BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
            ).one()
            assert cancel_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING

        resume_payload = client.post(
            "/api/billing/subscriptions/resume",
            json={"subscription_bid": "sub-active"},
        ).get_json(force=True)
        assert resume_payload["code"] == 0
        assert resume_payload["data"]["status"] == "active"
        assert resume_payload["data"]["cancel_at_period_end"] is False

        with app.app_context():
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-active"
            ).one()
            cancel_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-active",
                event_type=BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
            ).one()
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert subscription.cancel_at_period_end == 0
            assert subscription.metadata_json["provider"] == "stripe"
            assert (
                subscription.metadata_json["latest_event_type"] == "resume_subscription"
            )
            assert cancel_event.status == BILLING_RENEWAL_EVENT_STATUS_CANCELED

    def test_past_due_subscription_sets_grace_and_retry_event(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-past-due",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="sub_provider_retry",
                provider_customer_id="cus_provider_retry",
                current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
                current_period_end_at=datetime(2026, 5, 1, 0, 0, 0),
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=datetime(2026, 4, 1, 0, 0, 0),
                updated_at=datetime(2026, 4, 1, 0, 0, 0),
            )
            dao.db.session.add(subscription)
            dao.db.session.flush()
            sync_subscription_lifecycle_events(app, subscription)
            dao.db.session.commit()

            applied = apply_billing_subscription_provider_update(
                app,
                subscription,
                provider="stripe",
                event_type="customer.subscription.updated",
                payload={"created": 1775000000},
                data_object={
                    "id": "sub_provider_retry",
                    "status": "past_due",
                    "current_period_start": 1772000000,
                    "current_period_end": 1775003600,
                    "cancel_at_period_end": False,
                },
            )
            dao.db.session.commit()

            retry_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-past-due",
                event_type=BILLING_RENEWAL_EVENT_TYPE_RETRY,
            ).one()
            renewal_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-past-due",
                event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            ).one()
            assert applied is True
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_PAST_DUE
            assert (
                subscription.grace_period_end_at == subscription.current_period_end_at
            )
            assert retry_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
            assert renewal_event.status == BILLING_RENEWAL_EVENT_STATUS_CANCELED

    def test_next_product_bid_schedules_downgrade_event(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-downgrade",
                creator_bid="creator-1",
                product_bid="bill-product-plan-yearly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="sub_provider_yearly",
                provider_customer_id="cus_provider_yearly",
                current_period_start_at=datetime(2026, 1, 1, 0, 0, 0),
                current_period_end_at=datetime(2027, 1, 1, 0, 0, 0),
                cancel_at_period_end=0,
                next_product_bid="bill-product-plan-monthly",
                metadata_json={},
                created_at=datetime(2026, 1, 1, 0, 0, 0),
                updated_at=datetime(2026, 1, 1, 0, 0, 0),
            )
            dao.db.session.add(subscription)
            dao.db.session.flush()
            sync_subscription_lifecycle_events(app, subscription)
            dao.db.session.commit()

            downgrade_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-downgrade",
                event_type=BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
            ).one()
            assert downgrade_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
            assert downgrade_event.scheduled_at == subscription.current_period_end_at

    def test_paid_upgrade_order_switches_subscription_product_and_reschedules(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]
        current_cycle_start = datetime(2026, 4, 1, 0, 0, 0)
        current_cycle_end = datetime(2026, 5, 1, 0, 0, 0)
        upgrade_paid_at = datetime(2026, 4, 8, 13, 0, 0)
        upgraded_cycle_end = datetime(2027, 4, 8, 13, 0, 0)

        with app.app_context():
            wallet = CreditWallet(
                wallet_bid="wallet-upgrade",
                creator_bid="creator-1",
                available_credits=Decimal("3.0000000000"),
                reserved_credits=Decimal("0"),
                lifetime_granted_credits=Decimal("5.0000000000"),
                lifetime_consumed_credits=Decimal("2.0000000000"),
                last_settled_usage_id=0,
                version=0,
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
            subscription = BillingSubscription(
                subscription_bid="sub-upgrade",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="sub_provider_upgrade",
                provider_customer_id="cus_provider_upgrade",
                current_period_start_at=current_cycle_start,
                current_period_end_at=current_cycle_end,
                cancel_at_period_end=0,
                next_product_bid="bill-product-plan-monthly",
                metadata_json={},
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
            existing_bucket = CreditWalletBucket(
                wallet_bucket_bid="bucket-upgrade-existing",
                wallet_bid=wallet.wallet_bid,
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-start-1",
                priority=20,
                original_credits=Decimal("5.0000000000"),
                available_credits=Decimal("3.0000000000"),
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("2.0000000000"),
                expired_credits=Decimal("0"),
                effective_from=current_cycle_start,
                effective_to=current_cycle_end,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={
                    "bill_order_bid": "bill-start-1",
                    "product_bid": "bill-product-plan-monthly",
                    "payment_provider": "stripe",
                },
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
            existing_ledger = CreditLedgerEntry(
                ledger_bid="ledger-upgrade-existing",
                creator_bid="creator-1",
                wallet_bid=wallet.wallet_bid,
                wallet_bucket_bid=existing_bucket.wallet_bucket_bid,
                entry_type=CREDIT_LEDGER_ENTRY_TYPE_GRANT,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-start-1",
                idempotency_key="grant:bill-start-1",
                amount=Decimal("5.0000000000"),
                balance_after=Decimal("5.0000000000"),
                expires_at=current_cycle_end,
                consumable_from=current_cycle_start,
                metadata_json={
                    "bill_order_bid": "bill-start-1",
                    "subscription_bid": "sub-upgrade",
                    "product_bid": "bill-product-plan-monthly",
                    "payment_provider": "stripe",
                    "grant_reason": "subscription",
                },
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
            order = BillingOrder(
                bill_order_bid="billing-upgrade-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
                product_bid="bill-product-plan-yearly",
                subscription_bid="sub-upgrade",
                currency="CNY",
                payable_amount=99900,
                paid_amount=99900,
                payment_provider="stripe",
                channel="checkout_session",
                provider_reference_id="cs_upgrade_1",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=upgrade_paid_at,
                metadata_json={},
            )
            dao.db.session.add(wallet)
            dao.db.session.add(subscription)
            dao.db.session.add(existing_bucket)
            dao.db.session.add(existing_ledger)
            dao.db.session.add(order)
            dao.db.session.flush()

            granted = grant_paid_order_credits(app, order)
            dao.db.session.commit()

            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            existing_bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-upgrade-existing"
            ).one()
            existing_ledger = CreditLedgerEntry.query.filter_by(
                ledger_bid="ledger-upgrade-existing"
            ).one()
            upgrade_ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid="billing-upgrade-1",
            ).one()
            subscription_buckets = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
            ).all()
            upgrade_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-upgrade",
                event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            ).one()
            assert granted is True
            assert subscription.product_bid == "bill-product-plan-yearly"
            assert subscription.next_product_bid == ""
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert subscription.cancel_at_period_end == 0
            assert subscription.current_period_start_at == upgrade_paid_at
            assert subscription.current_period_end_at == upgraded_cycle_end
            assert wallet.available_credits == 10003
            assert len(subscription_buckets) == 1
            assert existing_bucket.source_bid == "billing-upgrade-1"
            assert existing_bucket.original_credits == 10005
            assert existing_bucket.available_credits == 10003
            assert existing_bucket.effective_from == upgrade_paid_at
            assert existing_bucket.effective_to == upgraded_cycle_end
            assert existing_ledger.expires_at == upgraded_cycle_end
            assert upgrade_ledger.wallet_bucket_bid == existing_bucket.wallet_bucket_bid
            assert upgrade_ledger.amount == 10000
            assert upgrade_ledger.expires_at == upgraded_cycle_end
            assert upgrade_ledger.consumable_from == upgrade_paid_at
            assert upgrade_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING

    def test_paid_renewal_order_applies_scheduled_next_product(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-renewal",
                creator_bid="creator-1",
                product_bid="bill-product-plan-yearly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="sub_provider_renewal",
                provider_customer_id="cus_provider_renewal",
                current_period_start_at=datetime(2026, 1, 1, 0, 0, 0),
                current_period_end_at=datetime(2027, 1, 1, 0, 0, 0),
                cancel_at_period_end=0,
                next_product_bid="bill-product-plan-monthly",
                metadata_json={},
                created_at=datetime(2026, 1, 1, 0, 0, 0),
                updated_at=datetime(2026, 1, 1, 0, 0, 0),
            )
            order = BillingOrder(
                bill_order_bid="bill-renewal-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                product_bid="bill-product-plan-monthly",
                subscription_bid="sub-renewal",
                currency="CNY",
                payable_amount=9900,
                paid_amount=9900,
                payment_provider="stripe",
                channel="checkout_session",
                provider_reference_id="cs_renewal_1",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=datetime(2027, 1, 1, 0, 0, 0),
                metadata_json={},
            )
            dao.db.session.add(subscription)
            dao.db.session.add(order)
            dao.db.session.flush()

            granted = grant_paid_order_credits(app, order)
            dao.db.session.commit()

            renewal_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-renewal",
                event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            ).one()
            assert granted is True
            assert subscription.product_bid == "bill-product-plan-monthly"
            assert subscription.next_product_bid == ""
            assert renewal_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING
            assert renewal_event.scheduled_at == subscription.current_period_end_at

    def test_paid_pingxx_renewal_before_cycle_start_keeps_current_period(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]
        current_cycle_start = datetime(2026, 4, 1, 0, 0, 0)
        renewal_cycle_start = datetime(2026, 5, 1, 0, 0, 0)
        renewal_cycle_end = datetime(2026, 6, 1, 0, 0, 0)

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-pingxx-early-renewal",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="pingxx",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=current_cycle_start,
                current_period_end_at=renewal_cycle_start,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
            order = BillingOrder(
                bill_order_bid="bill-pingxx-renewal-early-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                product_bid="bill-product-plan-monthly",
                subscription_bid="sub-pingxx-early-renewal",
                currency="CNY",
                payable_amount=9900,
                paid_amount=9900,
                payment_provider="pingxx",
                channel="alipay_qr",
                provider_reference_id="ch_pingxx_renewal_early_1",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=datetime(2026, 4, 24, 9, 0, 0),
                metadata_json={
                    "provider_reference_type": "charge",
                    "renewal_cycle_start_at": renewal_cycle_start.isoformat(),
                    "renewal_cycle_end_at": renewal_cycle_end.isoformat(),
                },
            )
            wallet = CreditWallet(
                wallet_bid="wallet-pingxx-early-renewal",
                creator_bid="creator-1",
                available_credits=Decimal("3.0000000000"),
                reserved_credits=Decimal("0"),
                lifetime_granted_credits=Decimal("3.0000000000"),
                lifetime_consumed_credits=Decimal("0"),
                last_settled_usage_id=0,
                version=0,
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
            bucket = CreditWalletBucket(
                wallet_bucket_bid="bucket-pingxx-early-renewal",
                wallet_bid=wallet.wallet_bid,
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_SUBSCRIPTION,
                source_bid="bill-pingxx-start-early-1",
                priority=20,
                original_credits=Decimal("3.0000000000"),
                available_credits=Decimal("3.0000000000"),
                reserved_credits=Decimal("0"),
                consumed_credits=Decimal("0"),
                expired_credits=Decimal("0"),
                effective_from=current_cycle_start,
                effective_to=renewal_cycle_start,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                metadata_json={
                    "bill_order_bid": "bill-pingxx-start-early-1",
                    "subscription_bid": "sub-pingxx-early-renewal",
                    "product_bid": "bill-product-plan-monthly",
                    "payment_provider": "pingxx",
                },
                created_at=current_cycle_start,
                updated_at=current_cycle_start,
            )
            dao.db.session.add(subscription)
            dao.db.session.add(wallet)
            dao.db.session.add(bucket)
            dao.db.session.add(order)
            dao.db.session.flush()

            granted = grant_paid_order_credits(app, order)
            dao.db.session.commit()

            bucket = CreditWalletBucket.query.filter_by(
                wallet_bucket_bid="bucket-pingxx-early-renewal",
            ).one()
            grant_ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid="bill-pingxx-renewal-early-1",
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-pingxx-early-renewal"
            ).one()
            subscription_buckets = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
            ).all()

            assert granted is True
            assert len(subscription_buckets) == 1
            assert bucket.source_bid == "bill-pingxx-renewal-early-1"
            assert bucket.available_credits == Decimal("3.0000000000")
            assert bucket.reserved_credits == Decimal("5.0000000000")
            assert bucket.effective_from == current_cycle_start
            assert bucket.effective_to == renewal_cycle_start
            assert wallet.available_credits == Decimal("3.0000000000")
            assert wallet.reserved_credits == Decimal("5.0000000000")
            assert grant_ledger.wallet_bucket_bid == bucket.wallet_bucket_bid
            assert grant_ledger.amount == Decimal("5.0000000000")
            assert grant_ledger.expires_at == renewal_cycle_end
            assert grant_ledger.consumable_from == renewal_cycle_start
            assert grant_ledger.metadata_json["bucket_credit_state"] == "reserved"
            assert subscription.current_period_start_at == current_cycle_start
            assert subscription.current_period_end_at == renewal_cycle_start
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE

    def test_paid_pingxx_renewal_after_cycle_end_shifts_cycle_from_payment_time(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]
        renewal_cycle_start = datetime(2026, 5, 1, 0, 0, 0)
        renewal_cycle_end = datetime(2026, 6, 1, 0, 0, 0)
        paid_at = datetime(2026, 6, 5, 10, 0, 0)

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-pingxx-late-renewal",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_EXPIRED,
                billing_provider="pingxx",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
                current_period_end_at=renewal_cycle_start,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=datetime(2026, 4, 1, 0, 0, 0),
                updated_at=datetime(2026, 6, 1, 0, 0, 0),
            )
            order = BillingOrder(
                bill_order_bid="bill-pingxx-renewal-late-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                product_bid="bill-product-plan-monthly",
                subscription_bid="sub-pingxx-late-renewal",
                currency="CNY",
                payable_amount=9900,
                paid_amount=9900,
                payment_provider="pingxx",
                channel="alipay_qr",
                provider_reference_id="ch_pingxx_renewal_late_1",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=paid_at,
                metadata_json={
                    "provider_reference_type": "charge",
                    "renewal_cycle_start_at": renewal_cycle_start.isoformat(),
                    "renewal_cycle_end_at": renewal_cycle_end.isoformat(),
                },
            )
            dao.db.session.add(subscription)
            dao.db.session.add(order)
            dao.db.session.flush()

            granted = grant_paid_order_credits(app, order)
            dao.db.session.commit()

            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid="bill-pingxx-renewal-late-1",
            ).one()
            order = BillingOrder.query.filter_by(
                bill_order_bid="bill-pingxx-renewal-late-1"
            ).one()
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-pingxx-late-renewal"
            ).one()

            assert granted is True
            assert bucket.effective_from == paid_at
            assert bucket.effective_to == datetime(2026, 7, 5, 10, 0, 0)
            assert order.metadata_json["applied_cycle_start_at"] == paid_at.isoformat()
            assert (
                order.metadata_json["applied_cycle_end_at"]
                == datetime(2026, 7, 5, 10, 0, 0).isoformat()
            )
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert subscription.current_period_start_at == paid_at
            assert subscription.current_period_end_at == datetime(2026, 7, 5, 10, 0, 0)

    def test_existing_subscription_grant_realigns_future_dated_cycle_on_replay(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]
        paid_at = datetime(2026, 4, 15, 13, 10, 37)
        corrupted_start_at = datetime(2026, 4, 17, 14, 31, 53)
        corrupted_end_at = datetime(2026, 4, 18, 14, 31, 53)

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-pingxx-start-repair-1",
                creator_bid="creator-1",
                product_bid="bill-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_DRAFT,
                billing_provider="pingxx",
                provider_subscription_id="",
                provider_customer_id="",
                current_period_start_at=None,
                current_period_end_at=None,
                cancel_at_period_end=0,
                next_product_bid="",
                metadata_json={},
                created_at=paid_at,
                updated_at=paid_at,
            )
            order = BillingOrder(
                bill_order_bid="bill-pingxx-start-repair-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
                product_bid="bill-product-plan-monthly",
                subscription_bid="sub-pingxx-start-repair-1",
                currency="CNY",
                payable_amount=990,
                paid_amount=990,
                payment_provider="pingxx",
                channel="alipay_qr",
                provider_reference_id="ch_pingxx_start_repair_1",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=paid_at,
                metadata_json={},
            )
            dao.db.session.add(subscription)
            dao.db.session.add(order)
            dao.db.session.flush()

            initial_grant = grant_paid_order_credits(app, order)
            subscription.current_period_start_at = corrupted_start_at
            subscription.current_period_end_at = corrupted_end_at
            subscription.updated_at = corrupted_start_at
            dao.db.session.add(subscription)
            dao.db.session.commit()

            replay_grant = grant_paid_order_credits(app, order)
            dao.db.session.commit()

            product = BillingProduct.query.filter_by(
                product_bid="bill-product-plan-monthly"
            ).one()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid="bill-pingxx-start-repair-1",
            ).one()
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-pingxx-start-repair-1"
            ).one()

            assert initial_grant is True
            assert replay_grant is False
            assert bucket.effective_from == paid_at
            assert bucket.effective_to == calculate_billing_cycle_end(
                product,
                cycle_start_at=paid_at,
            )
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert subscription.current_period_start_at == bucket.effective_from
            assert subscription.current_period_end_at == bucket.effective_to

    def test_refund_paid_stripe_order_marks_order_refunded(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        _add_active_subscription(app, subscription_bid="sub-topup-refund-stripe-1")

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "stripe",
            },
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        sync = client.post(f"/api/billing/orders/{bill_order_bid}/sync").get_json(
            force=True
        )
        assert sync["data"]["status"] == "paid"

        refund = client.post(
            f"/api/billing/orders/{bill_order_bid}/refund",
            json={"reason": "requested_by_creator"},
        ).get_json(force=True)

        assert refund["code"] == 0
        assert refund["data"]["status"] == "refunded"
        assert refund["data"]["refund_reference_id"] == "re_billing_test"
        assert (
            billing_write_client["refund_requests"][0]["metadata"]["payment_intent_id"]
            == "pi_billing_test"
        )

        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            topup_buckets = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
            ).all()
            refund_bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid="re_billing_test",
            ).one()
            refund_ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_type=CREDIT_SOURCE_TYPE_REFUND,
                source_bid="re_billing_test",
            ).one()
            raw_order = StripeOrder.query.filter_by(
                biz_domain="billing",
                bill_order_bid=bill_order_bid,
            ).one()
            assert order.status == BILLING_ORDER_STATUS_REFUNDED
            assert order.refunded_at is not None
            assert order.metadata_json["latest_event_type"] == "refund_payment"
            assert wallet.available_credits == 40
            assert len(topup_buckets) == 1
            assert refund_bucket.bucket_category == CREDIT_BUCKET_CATEGORY_TOPUP
            assert refund_bucket.source_type == CREDIT_SOURCE_TYPE_TOPUP
            assert refund_bucket.available_credits == 40
            assert refund_bucket.metadata_json["bill_order_bid"] == bill_order_bid
            assert refund_ledger.entry_type == CREDIT_LEDGER_ENTRY_TYPE_REFUND
            assert refund_ledger.amount == 20
            assert raw_order.status == 2
            assert "last_refund_id" in raw_order.metadata_json
            assert (
                StripeOrder.query.filter_by(
                    biz_domain="billing",
                    bill_order_bid=bill_order_bid,
                ).count()
                == 1
            )

    def test_refund_pingxx_order_returns_unsupported(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]
        _add_active_subscription(app, subscription_bid="sub-topup-refund-pingxx-1")

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)
        bill_order_bid = checkout["data"]["bill_order_bid"]

        sync = client.post(f"/api/billing/orders/{bill_order_bid}/sync").get_json(
            force=True
        )
        assert sync["data"]["status"] == "paid"

        refund = client.post(
            f"/api/billing/orders/{bill_order_bid}/refund",
        ).get_json(force=True)

        assert refund["code"] == 0
        assert refund["data"]["status"] == "unsupported"
        assert billing_write_client["refund_requests"] == []

        with app.app_context():
            order = BillingOrder.query.filter_by(bill_order_bid=bill_order_bid).one()
            assert order.status == BILLING_ORDER_STATUS_PAID

    def test_write_routes_require_creator(self, billing_write_client) -> None:
        client = billing_write_client["client"]
        response = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "bill-product-topup-small",
                "payment_provider": "pingxx",
            },
            headers={"X-Creator": "0"},
        )
        payload = response.get_json(force=True)

        assert payload["code"] != 0
