"""Verify billing callbacks behavior."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from flask import Flask
from flaskr import dao
from flaskr.route.callback import register_callback_handler
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_CANCELED,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
)
from flaskr.service.billing.models import (
    BillingOrder,
    BillingSubscription,
    CreditLedgerEntry,
)
from flaskr.service.billing.provider_state import _apply_billing_order_provider_update
from flaskr.service.billing.webhooks import (
    apply_billing_native_notification,
)
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS, ORDER_STATUS_TO_BE_PAID
from flaskr.service.order.models import AlipayOrder, Order, WechatPayOrder
from flaskr.service.order.payment_providers.base import PaymentNotificationResult

from tests.common.fixtures.bill_products import build_bill_products
from tests.common.fixtures.model_factories import make_billing_order

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def billing_callback_app() -> Iterator[Flask]:
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
    register_callback_handler(app, "/api/callback")
    with app.app_context():
        dao.db.create_all()
        dao.db.session.add_all(build_bill_products())
        dao.db.session.commit()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _create_active_subscription(creator_bid: str = "creator-1") -> BillingSubscription:
    now = datetime(2024, 4, 8, 12, 0, 0)
    return BillingSubscription(
        subscription_bid=f"subscription-{creator_bid}",
        creator_bid=creator_bid,
        product_bid="bill-product-plan-monthly",
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        current_period_start_at=now - timedelta(days=1),
        current_period_end_at=now + timedelta(days=30),
    )


def _create_native_billing_order(
    bill_order_bid: str,
    provider: str,
    provider_reference_id: str,
    *,
    amount: int = 19900,
) -> BillingOrder:
    return make_billing_order(
        bill_order_bid=bill_order_bid,
        creator_bid="creator-1",
        order_type=BILLING_ORDER_TYPE_TOPUP,
        product_bid="bill-product-topup-small",
        payable_amount=amount,
        payment_provider=provider,
        channel="alipay_qr" if provider == "alipay" else "wx_pub_qr",
        provider_reference_id=provider_reference_id,
        status=BILLING_ORDER_STATUS_PENDING,
        metadata_json={},
    )


def test_replaced_package_canceled_order_cannot_be_revived_by_provider_sync() -> None:
    order = make_billing_order(
        bill_order_bid="bill-order-canceled-replaced-1",
        creator_bid="creator-1",
        order_type=BILLING_ORDER_TYPE_TOPUP,
        product_bid="bill-product-topup-small",
        payable_amount=19900,
        payment_provider="stripe",
        channel="checkout_session",
        provider_reference_id="cs_replaced_1",
        status=BILLING_ORDER_STATUS_CANCELED,
        metadata_json={"invalidated_reason": "replaced_by_new_package"},
    )

    result = _apply_billing_order_provider_update(
        order,
        provider="stripe",
        event_type="manual_sync",
        source="sync",
        payload={"checkout_session": {"id": "cs_replaced_1"}},
        provider_reference_id="cs_replaced_1",
        target_status=BILLING_ORDER_STATUS_PAID,
    )

    assert result.applied is False
    assert order.status == BILLING_ORDER_STATUS_CANCELED
    assert order.paid_at is None


def _create_billing_native_raw_snapshot(
    provider: str,
    bill_order_bid: str,
    provider_attempt_id: str,
    *,
    amount: int = 19900,
) -> AlipayOrder | WechatPayOrder:
    if provider == "alipay":
        return AlipayOrder(
            alipay_order_bid=bill_order_bid,
            biz_domain="billing",
            bill_order_bid=bill_order_bid,
            creator_bid="creator-1",
            provider_attempt_id=provider_attempt_id,
            channel="alipay_qr",
            amount=amount,
            currency="CNY",
            status=0,
            raw_status="pending",
        )
    return WechatPayOrder(
        wechatpay_order_bid=bill_order_bid,
        biz_domain="billing",
        bill_order_bid=bill_order_bid,
        creator_bid="creator-1",
        provider_attempt_id=provider_attempt_id,
        channel="wx_pub_qr",
        amount=amount,
        currency="CNY",
        status=0,
        raw_status="pending",
    )


def _alipay_notification(
    provider_attempt_id: str,
    trade_status: str,
    *,
    amount: str = "199.00",
) -> PaymentNotificationResult:
    return PaymentNotificationResult(
        order_bid=provider_attempt_id,
        status=trade_status,
        provider_payload={
            "out_trade_no": provider_attempt_id,
            "trade_no": f"trade-{provider_attempt_id}",
            "trade_status": trade_status,
            "total_amount": amount,
        },
        charge_id=f"trade-{provider_attempt_id}",
    )


def _wechatpay_notification(
    provider_attempt_id: str,
    trade_state: str,
    *,
    amount: int = 19900,
) -> PaymentNotificationResult:
    return PaymentNotificationResult(
        order_bid=provider_attempt_id,
        status=trade_state,
        provider_payload={
            "resource": {
                "out_trade_no": provider_attempt_id,
                "transaction_id": f"wx-{provider_attempt_id}",
                "trade_state": trade_state,
                "amount": {"total": amount, "payer_total": amount},
            }
        },
        charge_id=f"wx-{provider_attempt_id}",
    )


def _create_legacy_wechatpay_records(
    order_bid: str, provider_attempt_id: str
) -> tuple[Order, WechatPayOrder]:
    order = Order(
        order_bid=order_bid,
        shifu_bid="legacy-shifu-1",
        user_bid="legacy-user-1",
        payable_price=Decimal("199.00"),
        paid_price=Decimal("199.00"),
        payment_channel="wechatpay",
        status=ORDER_STATUS_TO_BE_PAID,
    )
    wechatpay_order = WechatPayOrder(
        wechatpay_order_bid=f"wechatpay-{order_bid}",
        biz_domain="order",
        user_bid=order.user_bid,
        shifu_bid=order.shifu_bid,
        order_bid=order.order_bid,
        provider_attempt_id=provider_attempt_id,
        transaction_id="",
        channel="wx_pub",
        amount=19900,
        currency="CNY",
        status=0,
        raw_status="pending",
        raw_request="{}",
        raw_response="{}",
        raw_notification="{}",
        metadata_json="{}",
    )
    return order, wechatpay_order


class TestBillingNativeCallbacks:
    """Verify billing native callbacks behavior."""

    def test_native_callback_syncs_manual_trial_subscription_provider(
        self, billing_callback_app: object
    ) -> None:
        with billing_callback_app.app_context():
            now = datetime(2026, 4, 8, 12, 0, 0)
            dao.db.session.add(
                BillingSubscription(
                    subscription_bid="sub-manual-trial-to-alipay",
                    creator_bid="creator-1",
                    product_bid="bill-product-plan-trial",
                    status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
                    billing_provider="manual",
                    current_period_start_at=now - timedelta(days=1),
                    current_period_end_at=now + timedelta(days=14),
                )
            )
            dao.db.session.add(
                make_billing_order(
                    bill_order_bid="bill-alipay-trial-upgrade-1",
                    creator_bid="creator-1",
                    order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_UPGRADE,
                    product_bid="bill-product-plan-monthly",
                    subscription_bid="sub-manual-trial-to-alipay",
                    payable_amount=9900,
                    payment_provider="alipay",
                    channel="alipay_qr",
                    provider_reference_id="bill-alipay-trial-upgrade-1",
                    status=BILLING_ORDER_STATUS_PENDING,
                    metadata_json={"checkout_type": "subscription"},
                )
            )
            dao.db.session.add(
                _create_billing_native_raw_snapshot(
                    "alipay",
                    "bill-alipay-trial-upgrade-1",
                    "bill-alipay-trial-upgrade-1",
                    amount=9900,
                )
            )
            dao.db.session.commit()

        notification = _alipay_notification(
            "bill-alipay-trial-upgrade-1", "TRADE_SUCCESS", amount="99.00"
        )
        payload, status_code = apply_billing_native_notification(
            billing_callback_app, "alipay", notification
        )

        assert status_code == 200
        assert payload["status"] == "paid"
        with billing_callback_app.app_context():
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-manual-trial-to-alipay"
            ).one()
            order = BillingOrder.query.filter_by(
                bill_order_bid="bill-alipay-trial-upgrade-1"
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PAID
            assert subscription.product_bid == "bill-product-plan-monthly"
            assert subscription.billing_provider == "alipay"
            assert subscription.metadata_json["provider"] == "alipay"
            assert subscription.metadata_json["latest_source"] == "webhook"
            subscription.cancel_at_period_end = 1
            subscription.status = BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED
            dao.db.session.commit()

        duplicate_payload, duplicate_status = apply_billing_native_notification(
            billing_callback_app, "alipay", notification
        )

        assert duplicate_status == 200
        assert duplicate_payload["status"] == "paid"
        with billing_callback_app.app_context():
            subscription = BillingSubscription.query.filter_by(
                subscription_bid="sub-manual-trial-to-alipay"
            ).one()
            assert subscription.cancel_at_period_end == 1
            assert subscription.status == BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED

    def test_alipay_billing_callback_duplicate_paid_is_idempotent(
        self, billing_callback_app: object
    ) -> None:
        with billing_callback_app.app_context():
            dao.db.session.add(
                _create_native_billing_order(
                    "bill-native-alipay-1",
                    "alipay",
                    "bill-native-alipay-1",
                )
            )
            dao.db.session.add(
                _create_billing_native_raw_snapshot(
                    "alipay",
                    "bill-native-alipay-1",
                    "bill-native-alipay-1",
                )
            )
            dao.db.session.commit()

        first_payload, first_status = apply_billing_native_notification(
            billing_callback_app,
            "alipay",
            _alipay_notification("bill-native-alipay-1", "TRADE_SUCCESS"),
        )
        second_payload, second_status = apply_billing_native_notification(
            billing_callback_app,
            "alipay",
            _alipay_notification("bill-native-alipay-1", "TRADE_SUCCESS"),
        )

        assert first_status == 200
        assert second_status == 200
        assert first_payload["status"] == "paid"
        assert second_payload["matched"] is True

        with billing_callback_app.app_context():
            order = BillingOrder.query.filter_by(
                bill_order_bid="bill-native-alipay-1"
            ).one()
            raw_order = AlipayOrder.query.filter_by(
                biz_domain="billing",
                bill_order_bid="bill-native-alipay-1",
            ).one()
            ledgers = CreditLedgerEntry.query.filter_by(
                creator_bid="creator-1",
                source_bid="bill-native-alipay-1",
            ).all()
            assert order.status == BILLING_ORDER_STATUS_PAID
            assert order.paid_at is not None
            assert raw_order.status == 1
            assert raw_order.raw_status == "TRADE_SUCCESS"
            assert len(ledgers) == 1

    def test_wechatpay_native_callbacks_allow_failed_then_paid(
        self, billing_callback_app: object
    ) -> None:
        with billing_callback_app.app_context():
            dao.db.session.add(
                _create_native_billing_order(
                    "bill-native-wechat-fail-then-paid",
                    "wechatpay",
                    "bill-native-wechat-fail-then-paid",
                )
            )
            dao.db.session.add(
                _create_billing_native_raw_snapshot(
                    "wechatpay",
                    "bill-native-wechat-fail-then-paid",
                    "bill-native-wechat-fail-then-paid",
                )
            )
            dao.db.session.commit()

        failed_payload, failed_status = apply_billing_native_notification(
            billing_callback_app,
            "wechatpay",
            _wechatpay_notification("bill-native-wechat-fail-then-paid", "PAYERROR"),
        )
        paid_payload, paid_status = apply_billing_native_notification(
            billing_callback_app,
            "wechatpay",
            _wechatpay_notification("bill-native-wechat-fail-then-paid", "SUCCESS"),
        )

        assert failed_status == 200
        assert paid_status == 200
        assert failed_payload["status"] == "acknowledged"
        assert paid_payload["status"] == "paid"

        with billing_callback_app.app_context():
            order = BillingOrder.query.filter_by(
                bill_order_bid="bill-native-wechat-fail-then-paid"
            ).one()
            raw_order = WechatPayOrder.query.filter_by(
                biz_domain="billing",
                bill_order_bid="bill-native-wechat-fail-then-paid",
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PAID
            assert raw_order.status == 1
            assert raw_order.raw_status == "SUCCESS"

    def test_wechatpay_native_callbacks_ignore_failed_after_paid(
        self, billing_callback_app: object
    ) -> None:
        with billing_callback_app.app_context():
            dao.db.session.add(
                _create_native_billing_order(
                    "bill-native-wechat-paid-then-fail",
                    "wechatpay",
                    "bill-native-wechat-paid-then-fail",
                )
            )
            dao.db.session.add(
                _create_billing_native_raw_snapshot(
                    "wechatpay",
                    "bill-native-wechat-paid-then-fail",
                    "bill-native-wechat-paid-then-fail",
                )
            )
            dao.db.session.commit()

        apply_billing_native_notification(
            billing_callback_app,
            "wechatpay",
            _wechatpay_notification("bill-native-wechat-paid-then-fail", "SUCCESS"),
        )
        apply_billing_native_notification(
            billing_callback_app,
            "wechatpay",
            _wechatpay_notification("bill-native-wechat-paid-then-fail", "PAYERROR"),
        )

        with billing_callback_app.app_context():
            order = BillingOrder.query.filter_by(
                bill_order_bid="bill-native-wechat-paid-then-fail"
            ).one()
            raw_order = WechatPayOrder.query.filter_by(
                biz_domain="billing",
                bill_order_bid="bill-native-wechat-paid-then-fail",
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PAID
            assert raw_order.status == 1
            assert raw_order.raw_status == "SUCCESS"

    def test_native_billing_callback_rejects_amount_mismatch(
        self, billing_callback_app: object
    ) -> None:
        with billing_callback_app.app_context():
            dao.db.session.add(
                _create_native_billing_order(
                    "bill-native-amount-mismatch",
                    "alipay",
                    "bill-native-amount-mismatch",
                )
            )
            dao.db.session.add(
                _create_billing_native_raw_snapshot(
                    "alipay",
                    "bill-native-amount-mismatch",
                    "bill-native-amount-mismatch",
                )
            )
            dao.db.session.commit()

        with pytest.raises(RuntimeError, match="amount mismatch"):
            apply_billing_native_notification(
                billing_callback_app,
                "alipay",
                _alipay_notification(
                    "bill-native-amount-mismatch",
                    "TRADE_SUCCESS",
                    amount="1.00",
                ),
            )

        with billing_callback_app.app_context():
            order = BillingOrder.query.filter_by(
                bill_order_bid="bill-native-amount-mismatch"
            ).one()
            assert order.status == BILLING_ORDER_STATUS_PENDING

    def test_native_callback_route_acknowledges_unmatched_alipay(
        self, billing_callback_app: object, monkeypatch: object
    ) -> None:
        class FakeAlipayProvider:
            def handle_notification(self, *, payload: object, app: object) -> object:
                _ = (payload, app)
                return _alipay_notification("missing-native-order", "TRADE_SUCCESS")

        monkeypatch.setattr(
            "flaskr.route.callback.get_payment_provider",
            lambda _provider_name: FakeAlipayProvider(),
        )
        monkeypatch.setattr(
            "flaskr.route.callback.success_buy_record_from_native",
            lambda *_args, **_kwargs: False,
        )

        with billing_callback_app.test_client() as client:
            response = client.post(
                "/api/callback/alipay-notify",
                data={"out_trade_no": "missing-native-order"},
            )

        assert response.status_code == 200
        assert response.data.decode("utf-8") == "success"

    def test_wechatpay_callback_route_updates_legacy_order_when_not_billing(
        self, billing_callback_app: object, monkeypatch: object
    ) -> None:
        class FakeWechatPayProvider:
            def verify_webhook(
                self, *, headers: object, raw_body: object, app: object
            ) -> object:
                _ = (headers, raw_body, app)
                return _wechatpay_notification("legacy-wechatpay-attempt-1", "SUCCESS")

        monkeypatch.setattr(
            "flaskr.route.callback.get_payment_provider",
            lambda _provider_name: FakeWechatPayProvider(),
        )
        monkeypatch.setattr(
            "flaskr.service.order.funs.get_shifu_creator_bid",
            lambda *_args, **_kwargs: "creator-legacy-1",
        )
        monkeypatch.setattr(
            "flaskr.service.order.funs.set_user_state",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            "flaskr.service.order.funs.send_order_feishu",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            "flaskr.service.order.funs.query_buy_record",
            lambda *_args, **_kwargs: {},
        )

        with billing_callback_app.app_context():
            legacy_order, legacy_wechatpay_order = _create_legacy_wechatpay_records(
                "legacy-wechatpay-order-1",
                "legacy-wechatpay-attempt-1",
            )
            dao.db.session.add(legacy_order)
            dao.db.session.add(legacy_wechatpay_order)
            dao.db.session.commit()

        with billing_callback_app.test_client() as client:
            response = client.post(
                "/api/callback/wechatpay-notify",
                data=b"{}",
                headers={
                    "Wechatpay-Timestamp": "1",
                    "Wechatpay-Nonce": "nonce",
                    "Wechatpay-Signature": "signature",
                },
            )

        assert response.status_code == 200
        assert response.get_json() == {"code": "SUCCESS", "message": "成功"}

        with billing_callback_app.app_context():
            legacy_order = Order.query.filter_by(
                order_bid="legacy-wechatpay-order-1"
            ).one()
            legacy_wechatpay_order = WechatPayOrder.query.filter_by(
                provider_attempt_id="legacy-wechatpay-attempt-1",
            ).one()
            assert legacy_order.status == ORDER_STATUS_SUCCESS
            assert legacy_wechatpay_order.status == 1
            assert legacy_wechatpay_order.raw_status == "SUCCESS"
            assert (
                legacy_wechatpay_order.transaction_id == "wx-legacy-wechatpay-attempt-1"
            )

    def test_wechatpay_callback_route_hides_exception_details(
        self, billing_callback_app: object, monkeypatch: object
    ) -> None:
        class FakeWechatPayProvider:
            def verify_webhook(
                self, *, headers: object, raw_body: object, app: object
            ) -> None:
                _ = (headers, raw_body, app)
                message = "secret verification detail"
                raise RuntimeError(message)

        monkeypatch.setattr(
            "flaskr.route.callback.get_payment_provider",
            lambda _provider_name: FakeWechatPayProvider(),
        )

        with billing_callback_app.test_client() as client:
            response = client.post(
                "/api/callback/wechatpay-notify",
                data=b"{}",
            )

        assert response.status_code == 400
        assert response.get_json() == {
            "code": "FAIL",
            "message": "processing error",
        }
