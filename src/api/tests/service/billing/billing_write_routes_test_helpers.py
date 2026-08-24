"""Provide billing write routes test helpers support for service billing tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING

import flaskr.common.config as common_config
import flaskr.service.billing.checkout as billing_checkout_module
import flaskr.service.billing.subscriptions as billing_subscriptions_module
from flask import Flask, jsonify, request
from flaskr import dao
from flaskr.i18n import load_translations, set_language
from flaskr.service.billing.consts import (
    ALLOCATION_INTERVAL_PER_CYCLE,
    BILLING_CAMPAIGN_BENEFIT_TYPE_BONUS,
    BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
    BILLING_INTERVAL_DAY,
    BILLING_MODE_RECURRING,
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_ORDER_STATUS_TIMEOUT,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
    BILLING_RENEWAL_EVENT_STATUS_CANCELED,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE,
    BILLING_RENEWAL_EVENT_TYPE_EXPIRE,
    BILLING_RENEWAL_EVENT_TYPE_RENEWAL,
    BILLING_RENEWAL_EVENT_TYPE_RETRY,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_TRIAL_PRODUCT_BID,
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_BUCKET_STATUS_EXPIRED,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_LEDGER_ENTRY_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_GIFT,
    CREDIT_SOURCE_TYPE_REFUND,
    CREDIT_SOURCE_TYPE_SUBSCRIPTION,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from flaskr.service.billing.models import (
    BillingCampaign,
    BillingCampaignProduct,
    BillingOrder,
    BillingProduct,
    BillingProductProviderPrice,
    BillingRenewalEvent,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from flaskr.service.billing.preorders import mark_preorder_effective_applied
from flaskr.service.billing.primitives import normalize_mysql_datetime
from flaskr.service.billing.provider_state import (
    apply_billing_subscription_provider_update,
)
from flaskr.service.billing.queries import (
    calculate_self_managed_billing_cycle_end,
    calculate_self_managed_billing_cycle_end_after_boundary,
)
from flaskr.service.billing.subscriptions import (
    grant_paid_order_credits,
    repair_topup_grant_expiries,
    sync_subscription_lifecycle_events,
)
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.order.models import PingxxOrder, StripeOrder
from flaskr.service.order.payment_providers import (
    PaymentCreationResult,
    PaymentNotificationResult,
    PaymentRefundResult,
    SubscriptionUpdateResult,
)
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.repository import create_user_entity
from flaskr.util.datetime import now_utc, to_utc_iso

from tests.common.fixtures.bill_products import build_bill_products
from tests.service.billing.route_loader import (
    load_billing_routes_module,
    load_register_billing_routes,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    "ALLOCATION_INTERVAL_PER_CYCLE",
    "BILLING_CAMPAIGN_BENEFIT_TYPE_BONUS",
    "BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT",
    "BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED",
    "BILLING_INTERVAL_DAY",
    "BILLING_MODE_RECURRING",
    "BILLING_ORDER_STATUS_CANCELED",
    "BILLING_ORDER_STATUS_PAID",
    "BILLING_ORDER_STATUS_PENDING",
    "BILLING_ORDER_STATUS_REFUNDED",
    "BILLING_ORDER_STATUS_TIMEOUT",
    "BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL",
    "BILLING_ORDER_TYPE_SUBSCRIPTION_START",
    "BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE",
    "BILLING_ORDER_TYPE_TOPUP",
    "BILLING_PRODUCT_STATUS_ACTIVE",
    "BILLING_PRODUCT_TYPE_PLAN",
    "BILLING_PROVIDER_PRICE_STATUS_ACTIVE",
    "BILLING_RENEWAL_EVENT_STATUS_CANCELED",
    "BILLING_RENEWAL_EVENT_STATUS_PENDING",
    "BILLING_RENEWAL_EVENT_TYPE_CANCEL_EFFECTIVE",
    "BILLING_RENEWAL_EVENT_TYPE_DOWNGRADE_EFFECTIVE",
    "BILLING_RENEWAL_EVENT_TYPE_EXPIRE",
    "BILLING_RENEWAL_EVENT_TYPE_RENEWAL",
    "BILLING_RENEWAL_EVENT_TYPE_RETRY",
    "BILLING_SUBSCRIPTION_STATUS_ACTIVE",
    "BILLING_SUBSCRIPTION_STATUS_DRAFT",
    "BILLING_SUBSCRIPTION_STATUS_EXPIRED",
    "BILLING_SUBSCRIPTION_STATUS_PAST_DUE",
    "BILLING_TRIAL_PRODUCT_BID",
    "CREDIT_BUCKET_CATEGORY_FREE",
    "CREDIT_BUCKET_CATEGORY_SUBSCRIPTION",
    "CREDIT_BUCKET_CATEGORY_TOPUP",
    "CREDIT_BUCKET_STATUS_ACTIVE",
    "CREDIT_BUCKET_STATUS_EXPIRED",
    "CREDIT_LEDGER_ENTRY_TYPE_GRANT",
    "CREDIT_LEDGER_ENTRY_TYPE_REFUND",
    "CREDIT_SOURCE_TYPE_GIFT",
    "CREDIT_SOURCE_TYPE_REFUND",
    "CREDIT_SOURCE_TYPE_SUBSCRIPTION",
    "CREDIT_SOURCE_TYPE_TOPUP",
    "ERROR_CODE",
    "BillingCampaign",
    "BillingCampaignProduct",
    "BillingOrder",
    "BillingProduct",
    "BillingProductProviderPrice",
    "BillingRenewalEvent",
    "BillingSubscription",
    "CreditLedgerEntry",
    "CreditWallet",
    "CreditWalletBucket",
    "Decimal",
    "PingxxOrder",
    "StripeOrder",
    "add_active_subscription",
    "add_trial_subscription_state",
    "apply_billing_subscription_provider_update",
    "billing_checkout_module",
    "billing_subscriptions_module",
    "billing_write_client",
    "billing_write_routes_module",
    "calculate_self_managed_billing_cycle_end",
    "dao",
    "datetime",
    "grant_paid_order_credits",
    "mark_preorder_effective_applied",
    "normalize_mysql_datetime",
    "now_utc",
    "repair_topup_grant_expiries",
    "seed_active_stripe_provider_price_mappings",
    "seed_creator_user",
    "self_managed_cycle_end_after_boundary",
    "sync_subscription_lifecycle_events",
    "timedelta",
    "to_utc_iso",
]

register_billing_routes = load_register_billing_routes()

billing_write_routes_module = load_billing_routes_module()


def self_managed_cycle_end_after_boundary(
    product: BillingProduct,
    boundary_at: datetime,
) -> datetime:
    cycle_end_at = calculate_self_managed_billing_cycle_end_after_boundary(
        product,
        cycle_boundary_at=boundary_at,
    )
    assert cycle_end_at is not None
    return cycle_end_at


def _reset_config_cache(*keys: str) -> None:
    for key in keys:
        common_config.__ENHANCED_CONFIG__._cache.pop(key, None)


def add_active_subscription(
    app: Flask,
    *,
    creator_bid: str = "creator-1",
    subscription_bid: str = "sub-topup-active-default",
    current_period_start_at: datetime | None = None,
    current_period_end_at: datetime | None = None,
) -> None:
    now = now_utc()
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


def seed_creator_user(app: Flask, *, creator_bid: str = "creator-1") -> None:
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


def seed_active_stripe_provider_price_mappings(app: Flask) -> None:
    """Seed active Stripe price mappings for billing checkout tests."""
    with app.app_context():
        rows = BillingProduct.query.filter(BillingProduct.deleted == 0).all()
        for row in rows:
            existing = BillingProductProviderPrice.query.filter_by(
                provider_price_bid=f"mapping-{row.product_bid}",
                deleted=0,
            ).one_or_none()
            if existing is not None:
                continue
            dao.db.session.add(
                BillingProductProviderPrice(
                    provider_price_bid=f"mapping-{row.product_bid}",
                    product_bid=row.product_bid,
                    provider="stripe",
                    provider_account_id="acct_test",
                    provider_product_id=f"prod_{row.product_bid}",
                    provider_price_id=f"price_{row.product_bid}",
                    livemode=0,
                    currency=str(row.currency or "CNY").upper(),
                    unit_amount=int(row.price_amount or 0),
                    billing_mode=int(row.billing_mode or 0),
                    billing_interval=int(row.billing_interval or 0),
                    billing_interval_count=int(row.billing_interval_count or 0),
                    status=BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
                    metadata_json={},
                )
            )
        dao.db.session.commit()


def add_trial_subscription_state(
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
    now = now_utc()
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
                reserved_credits=Decimal(0),
                lifetime_granted_credits=credit_amount,
                lifetime_consumed_credits=Decimal(0),
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
                reserved_credits=Decimal(0),
                consumed_credits=Decimal(0),
                expired_credits=Decimal(0),
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


def billing_write_client(monkeypatch: object) -> Iterator[dict[str, object]]:
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
    stripe_expire_requests: list[dict] = []
    pingxx_requests: list[dict] = []
    refund_requests: list[dict] = []

    class FakeStripeProvider:
        def create_payment(self, *, request: object, app: object) -> object:
            _ = app
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
                    "status": "open",
                    "payment_status": "unpaid",
                    "success_url": request.extra.get("success_url"),
                    "cancel_url": request.extra.get("cancel_url"),
                },
                checkout_session_id="cs_billing_test",
                extra={"url": "https://stripe.test/checkout"},
            )

        def create_subscription(self, *, request: object, app: object) -> object:
            return self.create_payment(request=request, app=app)

        def retrieve_checkout_session(
            self, *, session_id: str, app: object
        ) -> dict[str, object]:
            _ = app
            return {
                "id": session_id,
                "status": "open",
                "payment_status": "unpaid",
            }

        def expire_checkout_session(
            self, *, session_id: str, app: object
        ) -> dict[str, object]:
            _ = app
            stripe_expire_requests.append({"session_id": session_id})
            return {
                **self.retrieve_checkout_session(session_id=session_id, app=app),
                "status": "expired",
            }

        def sync_reference(
            self, *, provider_reference: str, reference_type: str, app: object
        ) -> object:
            _ = app
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
            self,
            *,
            subscription_bid: str,
            provider_subscription_id: str,
            app: object,
        ) -> object:
            _ = app
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
            self,
            *,
            subscription_bid: str,
            provider_subscription_id: str,
            app: object,
        ) -> object:
            _ = app
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

        def refund_payment(self, *, request: object, app: object) -> object:
            _ = app
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
        def create_payment(self, *, request: object, app: object) -> object:
            _ = app
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

        def sync_reference(
            self, *, provider_reference: str, reference_type: str, app: object
        ) -> object:
            _ = app
            assert reference_type == "charge"
            return PaymentNotificationResult(
                order_bid="",
                status="manual_sync",
                provider_payload={"charge": {"id": provider_reference, "paid": True}},
                charge_id=provider_reference,
            )

    def _fake_get_payment_provider(channel: str) -> object:
        if channel == "stripe":
            return FakeStripeProvider()
        if channel == "pingxx":
            return FakePingxxProvider()
        message = f"Unexpected provider: {channel}"
        raise AssertionError(message)

    monkeypatch.setitem(
        billing_write_routes_module.create_billing_order_checkout.__globals__,
        "get_payment_provider",
        _fake_get_payment_provider,
    )
    monkeypatch.setitem(
        billing_write_routes_module.cancel_billing_subscription.__globals__,
        "get_payment_provider",
        _fake_get_payment_provider,
    )
    monkeypatch.setattr(
        "flaskr.service.billing.provider_price_mappings.resolve_current_stripe_provider_price_scope",
        lambda _app: SimpleNamespace(provider_account_id="acct_test", livemode=False),
    )
    monkeypatch.setattr(
        billing_write_routes_module,
        "is_billing_enabled",
        lambda: True,
    )

    @app.errorhandler(AppError)
    def _handle_app_exception(error: AppError) -> object:
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
        seed_active_stripe_provider_price_mappings(app)

        with app.test_client() as client:
            yield {
                "client": client,
                "app": app,
                "stripe_requests": stripe_requests,
                "stripe_expire_requests": stripe_expire_requests,
                "pingxx_requests": pingxx_requests,
                "refund_requests": refund_requests,
            }

        dao.db.session.remove()
        dao.db.drop_all()
        _reset_config_cache("HOST_URL", "PATH_PREFIX")
