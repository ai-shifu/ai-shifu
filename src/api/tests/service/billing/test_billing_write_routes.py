from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import sys
from types import SimpleNamespace
import types

from flask import Flask, jsonify, request
import pytest

import flaskr.dao as dao
from flaskr.service.billing.consts import (
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_GIFT,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_PRODUCT_SEEDS,
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
)
from flaskr.service.billing.funcs import (
    _apply_billing_subscription_provider_update,
    _grant_paid_order_credits,
    _sync_subscription_lifecycle_events,
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
from flaskr.service.common.models import AppException
from flaskr.service.order.payment_providers import (
    PaymentCreationResult,
    PaymentNotificationResult,
    PaymentRefundResult,
    SubscriptionUpdateResult,
)

_API_ROOT = Path(__file__).resolve().parents[3]
_ROUTE_DIR = _API_ROOT / "flaskr" / "route"
_BILLING_ROUTE_FILE = _API_ROOT / "flaskr" / "service" / "billing" / "routes.py"


def _load_register_billing_routes():
    package_name = "flaskr.route"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(_ROUTE_DIR)]
        sys.modules[package_name] = package

    common_name = f"{package_name}.common"
    if common_name not in sys.modules:
        common_spec = importlib.util.spec_from_file_location(
            common_name,
            _ROUTE_DIR / "common.py",
        )
        assert common_spec is not None and common_spec.loader is not None
        common_module = importlib.util.module_from_spec(common_spec)
        sys.modules[common_name] = common_module
        common_spec.loader.exec_module(common_module)

    full_name = "flaskr.service.billing.routes"
    if full_name in sys.modules:
        return sys.modules[full_name].register_billing_routes

    spec = importlib.util.spec_from_file_location(full_name, _BILLING_ROUTE_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module.register_billing_routes


register_billing_routes = _load_register_billing_routes()


def _seed_products() -> list[BillingProduct]:
    items: list[BillingProduct] = []
    for seed in BILLING_PRODUCT_SEEDS:
        payload = dict(seed)
        payload["metadata_json"] = payload.pop("metadata", None)
        items.append(BillingProduct(**payload))
    return items


@pytest.fixture
def billing_write_client(monkeypatch):
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

    stripe_requests: list[dict] = []
    pingxx_requests: list[dict] = []
    refund_requests: list[dict] = []

    class FakeStripeProvider:
        def create_payment(self, *, request, app):
            stripe_requests.append(
                {
                    "order_bid": request.order_bid,
                    "channel": request.channel,
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
        "flaskr.service.billing.funcs.get_payment_provider",
        _fake_get_payment_provider,
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
            language="en-US",
            is_creator=request.headers.get("X-Creator", "1") == "1",
        )

    register_billing_routes(app=app)

    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(_seed_products())
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


class TestBillingWriteRoutes:
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
                "product_bid": "billing-product-plan-monthly",
                "success_url": "https://example.com/payment/stripe/billing-result",
                "cancel_url": "https://example.com/payment/stripe/billing-result?canceled=1",
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
                "product_bid": "billing-product-plan-monthly",
                "payment_provider": "stripe",
                "success_url": "https://example.com/payment/stripe/billing-result",
                "cancel_url": "https://example.com/payment/stripe/billing-result?canceled=1",
            },
        )
        payload = response.get_json(force=True)

        assert payload["code"] == 0
        assert payload["data"]["provider"] == "stripe"
        assert payload["data"]["payment_mode"] == "subscription"
        assert payload["data"]["status"] == "pending"
        assert payload["data"]["redirect_url"] == "https://stripe.test/checkout"

        with app.app_context():
            order = BillingOrder.query.filter_by(creator_bid="creator-1").one()
            subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1"
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PENDING
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_DRAFT
            assert order.subscription_bid == subscription.subscription_bid

        stripe_request = billing_write_client["stripe_requests"][0]
        assert stripe_request["extra"]["session_params"]["mode"] == "subscription"
        assert (
            stripe_request["extra"]["line_items"][0]["price_data"]["recurring"][
                "interval"
            ]
            == "month"
        )

    def test_pingxx_subscription_checkout_and_sync_grant_initial_credits(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "billing-product-plan-monthly",
                "payment_provider": "pingxx",
            },
        ).get_json(force=True)
        billing_order_bid = checkout["data"]["billing_order_bid"]

        assert checkout["code"] == 0
        assert checkout["data"]["provider"] == "pingxx"
        assert checkout["data"]["status"] == "pending"
        assert checkout["data"]["payment_mode"] == "subscription"
        assert checkout["data"]["payment_payload"]["credential"]["alipay_qr"] == (
            "https://pingxx.test/qr"
        )

        with app.app_context():
            order = BillingOrder.query.filter_by(
                billing_order_bid=billing_order_bid
            ).one()
            subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1"
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PENDING
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_DRAFT
            assert subscription.billing_provider == "pingxx"
            assert subscription.provider_subscription_id == ""

        sync = client.post(f"/api/billing/orders/{billing_order_bid}/sync").get_json(
            force=True
        )
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            order = BillingOrder.query.filter_by(
                billing_order_bid=billing_order_bid
            ).one()
            subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1"
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=billing_order_bid,
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
                "product_bid": "billing-product-plan-monthly",
                "payment_provider": "pingxx",
            },
        ).get_json(force=True)
        billing_order_bid = checkout["data"]["billing_order_bid"]

        refreshed = client.post(
            f"/api/billing/orders/{billing_order_bid}/checkout",
        ).get_json(force=True)

        assert refreshed["code"] == 0
        assert refreshed["data"]["provider"] == "pingxx"
        assert refreshed["data"]["payment_mode"] == "subscription"
        assert refreshed["data"]["status"] == "pending"
        assert refreshed["data"]["payment_payload"]["credential"]["alipay_qr"] == (
            "https://pingxx.test/qr"
        )
        assert len(billing_write_client["pingxx_requests"]) == 2
        assert (
            billing_write_client["pingxx_requests"][1]["order_bid"] == billing_order_bid
        )

    def test_topup_checkout_and_sync_mark_order_paid(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "billing-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)
        billing_order_bid = checkout["data"]["billing_order_bid"]

        assert checkout["data"]["status"] == "pending"
        assert checkout["data"]["payment_payload"]["credential"]["alipay_qr"] == (
            "https://pingxx.test/qr"
        )

        sync = client.post(f"/api/billing/orders/{billing_order_bid}/sync").get_json(
            force=True
        )
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            order = BillingOrder.query.filter_by(
                billing_order_bid=billing_order_bid
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=billing_order_bid,
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=billing_order_bid,
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

    def test_topup_checkout_uses_pingxx_default_channel_when_provider_omitted(
        self, billing_write_client, monkeypatch
    ) -> None:
        client = billing_write_client["client"]

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
                "product_bid": "billing-product-topup-small",
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
                "product_bid": "billing-product-topup-small",
                "payment_provider": "stripe",
                "success_url": "https://example.com/payment/stripe/billing-result",
                "cancel_url": "https://example.com/payment/stripe/billing-result?canceled=1",
            },
        ).get_json(force=True)
        billing_order_bid = checkout["data"]["billing_order_bid"]

        sync = client.post(f"/api/billing/orders/{billing_order_bid}/sync").get_json(
            force=True
        )
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            new_bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=billing_order_bid,
            ).one()
            assert wallet.available_credits == Decimal("120.0000000000")
            assert wallet.reserved_credits == Decimal("0E-10")
            assert new_bucket.bucket_category == CREDIT_BUCKET_CATEGORY_TOPUP
            assert new_bucket.source_type == CREDIT_SOURCE_TYPE_TOPUP
            assert new_bucket.status == CREDIT_BUCKET_STATUS_ACTIVE

    def test_subscription_checkout_and_sync_grant_initial_credits(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        checkout = client.post(
            "/api/billing/subscriptions/checkout",
            json={
                "product_bid": "billing-product-plan-monthly",
                "payment_provider": "stripe",
                "success_url": "https://example.com/payment/stripe/billing-result",
                "cancel_url": "https://example.com/payment/stripe/billing-result?canceled=1",
            },
        ).get_json(force=True)
        billing_order_bid = checkout["data"]["billing_order_bid"]

        sync = client.post(f"/api/billing/orders/{billing_order_bid}/sync").get_json(
            force=True
        )
        assert sync["code"] == 0
        assert sync["data"]["status"] == "paid"

        with app.app_context():
            order = BillingOrder.query.filter_by(
                billing_order_bid=billing_order_bid
            ).one()
            subscription = BillingSubscription.query.filter_by(
                creator_bid="creator-1"
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid=billing_order_bid,
            ).one()
            ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid=billing_order_bid,
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
                    product_bid="billing-product-plan-monthly",
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
                product_bid="billing-product-plan-monthly",
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
            _sync_subscription_lifecycle_events(app, subscription)
            dao.db.session.commit()

            applied = _apply_billing_subscription_provider_update(
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
                product_bid="billing-product-plan-yearly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="sub_provider_yearly",
                provider_customer_id="cus_provider_yearly",
                current_period_start_at=datetime(2026, 1, 1, 0, 0, 0),
                current_period_end_at=datetime(2027, 1, 1, 0, 0, 0),
                cancel_at_period_end=0,
                next_product_bid="billing-product-plan-monthly",
                metadata_json={},
                created_at=datetime(2026, 1, 1, 0, 0, 0),
                updated_at=datetime(2026, 1, 1, 0, 0, 0),
            )
            dao.db.session.add(subscription)
            dao.db.session.flush()
            _sync_subscription_lifecycle_events(app, subscription)
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

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-upgrade",
                creator_bid="creator-1",
                product_bid="billing-product-plan-monthly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="sub_provider_upgrade",
                provider_customer_id="cus_provider_upgrade",
                current_period_start_at=datetime(2026, 4, 1, 0, 0, 0),
                current_period_end_at=datetime(2026, 5, 1, 0, 0, 0),
                cancel_at_period_end=0,
                next_product_bid="billing-product-plan-monthly",
                metadata_json={},
                created_at=datetime(2026, 4, 1, 0, 0, 0),
                updated_at=datetime(2026, 4, 1, 0, 0, 0),
            )
            order = BillingOrder(
                billing_order_bid="billing-upgrade-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
                product_bid="billing-product-plan-yearly",
                subscription_bid="sub-upgrade",
                currency="CNY",
                payable_amount=99900,
                paid_amount=99900,
                payment_provider="stripe",
                channel="checkout_session",
                provider_reference_id="cs_upgrade_1",
                status=BILLING_ORDER_STATUS_PAID,
                paid_at=datetime(2026, 4, 8, 13, 0, 0),
                metadata_json={},
            )
            dao.db.session.add(subscription)
            dao.db.session.add(order)
            dao.db.session.flush()

            granted = _grant_paid_order_credits(app, order)
            dao.db.session.commit()

            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            upgrade_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-upgrade",
                event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            ).one()
            assert granted is True
            assert subscription.product_bid == "billing-product-plan-yearly"
            assert subscription.next_product_bid == ""
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_ACTIVE
            assert subscription.cancel_at_period_end == 0
            assert wallet.available_credits == 10000
            assert upgrade_event.status == BILLING_RENEWAL_EVENT_STATUS_PENDING

    def test_paid_renewal_order_applies_scheduled_next_product(
        self, billing_write_client
    ) -> None:
        app = billing_write_client["app"]

        with app.app_context():
            subscription = BillingSubscription(
                subscription_bid="sub-renewal",
                creator_bid="creator-1",
                product_bid="billing-product-plan-yearly",
                status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                billing_provider="stripe",
                provider_subscription_id="sub_provider_renewal",
                provider_customer_id="cus_provider_renewal",
                current_period_start_at=datetime(2026, 1, 1, 0, 0, 0),
                current_period_end_at=datetime(2027, 1, 1, 0, 0, 0),
                cancel_at_period_end=0,
                next_product_bid="billing-product-plan-monthly",
                metadata_json={},
                created_at=datetime(2026, 1, 1, 0, 0, 0),
                updated_at=datetime(2026, 1, 1, 0, 0, 0),
            )
            order = BillingOrder(
                billing_order_bid="billing-renewal-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                product_bid="billing-product-plan-monthly",
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

            granted = _grant_paid_order_credits(app, order)
            dao.db.session.commit()

            renewal_event = BillingRenewalEvent.query.filter_by(
                subscription_bid="sub-renewal",
                event_type=BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
            ).one()
            assert granted is True
            assert subscription.product_bid == "billing-product-plan-monthly"
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
                product_bid="billing-product-plan-monthly",
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
                billing_order_bid="billing-pingxx-renewal-early-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                product_bid="billing-product-plan-monthly",
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
            dao.db.session.add(subscription)
            dao.db.session.add(order)
            dao.db.session.flush()

            granted = _grant_paid_order_credits(app, order)
            dao.db.session.commit()

            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid="billing-pingxx-renewal-early-1",
            ).one()
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-pingxx-early-renewal"
            ).one()

            assert granted is True
            assert bucket.effective_from == renewal_cycle_start
            assert bucket.effective_to == renewal_cycle_end
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
                product_bid="billing-product-plan-monthly",
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
                billing_order_bid="billing-pingxx-renewal-late-1",
                creator_bid="creator-1",
                order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
                product_bid="billing-product-plan-monthly",
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

            granted = _grant_paid_order_credits(app, order)
            dao.db.session.commit()

            bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_bid="billing-pingxx-renewal-late-1",
            ).one()
            order = BillingOrder.query.filter_by(
                billing_order_bid="billing-pingxx-renewal-late-1"
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

    def test_refund_paid_stripe_order_marks_order_refunded(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "billing-product-topup-small",
                "payment_provider": "stripe",
                "success_url": "https://example.com/payment/stripe/billing-result",
            },
        ).get_json(force=True)
        billing_order_bid = checkout["data"]["billing_order_bid"]

        sync = client.post(f"/api/billing/orders/{billing_order_bid}/sync").get_json(
            force=True
        )
        assert sync["data"]["status"] == "paid"

        refund = client.post(
            f"/api/billing/orders/{billing_order_bid}/refund",
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
            order = BillingOrder.query.filter_by(
                billing_order_bid=billing_order_bid
            ).one()
            wallet = CreditWallet.query.filter_by(creator_bid="creator-1").one()
            refund_bucket = CreditWalletBucket.query.filter_by(
                creator_bid="creator-1",
                source_type=CREDIT_SOURCE_TYPE_REFUND,
                source_bid="re_billing_test",
            ).one()
            refund_ledger = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_type=CREDIT_SOURCE_TYPE_REFUND,
                source_bid="re_billing_test",
            ).one()
            assert order.status == BILLING_ORDER_STATUS_REFUNDED
            assert order.refunded_at is not None
            assert order.metadata_json["latest_event_type"] == "refund_payment"
            assert wallet.available_credits == 40
            assert refund_bucket.bucket_category == CREDIT_BUCKET_CATEGORY_FREE
            assert refund_bucket.available_credits == 20
            assert refund_bucket.metadata_json["billing_order_bid"] == billing_order_bid
            assert refund_ledger.entry_type == CREDIT_LEDGER_ENTRY_TYPE_REFUND
            assert refund_ledger.amount == 20

    def test_refund_pingxx_order_returns_unsupported(
        self, billing_write_client
    ) -> None:
        client = billing_write_client["client"]
        app = billing_write_client["app"]

        checkout = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "billing-product-topup-small",
                "payment_provider": "pingxx",
                "channel": "alipay_qr",
            },
        ).get_json(force=True)
        billing_order_bid = checkout["data"]["billing_order_bid"]

        sync = client.post(f"/api/billing/orders/{billing_order_bid}/sync").get_json(
            force=True
        )
        assert sync["data"]["status"] == "paid"

        refund = client.post(
            f"/api/billing/orders/{billing_order_bid}/refund",
        ).get_json(force=True)

        assert refund["code"] == 0
        assert refund["data"]["status"] == "unsupported"
        assert billing_write_client["refund_requests"] == []

        with app.app_context():
            order = BillingOrder.query.filter_by(
                billing_order_bid=billing_order_bid
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PAID

    def test_write_routes_require_creator(self, billing_write_client) -> None:
        client = billing_write_client["client"]
        response = client.post(
            "/api/billing/topups/checkout",
            json={
                "product_bid": "billing-product-topup-small",
                "payment_provider": "pingxx",
            },
            headers={"X-Creator": "0"},
        )
        payload = response.get_json(force=True)

        assert payload["code"] != 0
