"""Verify native payment split tables behavior."""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao import uow
from flaskr.service.billing.checkout import (
    _persist_billing_native_raw_snapshot,
    load_billing_order_for_native_event,
)
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_TOPUP,
)
from flaskr.service.billing.models import BillingOrder
from flaskr.service.order.admin import _load_payment_detail
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS, ORDER_STATUS_TO_BE_PAID
from flaskr.service.order.funs import sync_native_payment_order
from flaskr.service.order.models import AlipayOrder, Order, WechatPayOrder
from flaskr.service.order.payment_providers.base import PaymentNotificationResult
from flaskr.service.order.raw_snapshots import (
    legacy_native_snapshot_query,
    upsert_native_snapshot,
)
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def native_payment_split_app() -> Iterator[Flask]:
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
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def test_native_snapshot_upsert_routes_each_provider_to_own_table(
    native_payment_split_app: object,
) -> None:
    with native_payment_split_app.app_context():
        alipay_snapshot = upsert_native_snapshot(
            biz_domain="order",
            payment_provider="alipay",
            native_payment_order_bid="ali-snapshot-1",
            provider_attempt_id="ali-attempt-1",
            order_bid="order-alipay-1",
            user_bid="user-1",
            shifu_bid="shifu-1",
            amount=19900,
            currency="CNY",
            raw_status="pending",
            raw_snapshot_status=0,
            channel="alipay_qr",
            raw_request={"out_trade_no": "ali-attempt-1"},
            raw_response={"qr_code": "https://alipay.test/qr"},
        )
        wechat_snapshot = upsert_native_snapshot(
            biz_domain="order",
            payment_provider="wechatpay",
            native_payment_order_bid="wx-snapshot-1",
            provider_attempt_id="wx-attempt-1",
            order_bid="order-wechat-1",
            user_bid="user-2",
            shifu_bid="shifu-2",
            amount=29900,
            currency="CNY",
            raw_status="pending",
            raw_snapshot_status=0,
            channel="wx_pub_qr",
            raw_request={"out_trade_no": "wx-attempt-1"},
            raw_response={"code_url": "weixin://wxpay/test"},
        )
        dao.db.session.add_all([alipay_snapshot, wechat_snapshot])
        dao.db.session.commit()

        assert AlipayOrder.query.count() == 1
        assert WechatPayOrder.query.count() == 1
        assert alipay_snapshot.alipay_order_bid == "ali-snapshot-1"
        assert wechat_snapshot.wechatpay_order_bid == "wx-snapshot-1"
        assert not hasattr(alipay_snapshot, "payment_provider")
        assert not hasattr(wechat_snapshot, "payment_provider")

        alipay_row = (
            legacy_native_snapshot_query("alipay")
            .filter(AlipayOrder.order_bid == "order-alipay-1")
            .one()
        )
        wechat_row = (
            legacy_native_snapshot_query("wechatpay")
            .filter(WechatPayOrder.order_bid == "order-wechat-1")
            .one()
        )
        assert isinstance(alipay_row, AlipayOrder)
        assert isinstance(wechat_row, WechatPayOrder)

        table_names = inspect(dao.db.engine).get_table_names()
        assert "order_alipay_orders" in table_names
        assert "order_wechatpay_orders" in table_names
        assert "order_native_payment_orders" not in table_names


def test_native_snapshot_upsert_preserves_zero_amount_and_requires_identifier(
    native_payment_split_app: object,
) -> None:
    with native_payment_split_app.app_context():
        snapshot = upsert_native_snapshot(
            biz_domain="order",
            payment_provider="alipay",
            native_payment_order_bid="ali-zero-1",
            provider_attempt_id="ali-zero-1",
            order_bid="order-zero-1",
            amount=19900,
            currency="CNY",
            raw_status="pending",
            raw_snapshot_status=0,
        )
        dao.db.session.add(snapshot)
        dao.db.session.commit()

        updated = upsert_native_snapshot(
            biz_domain="order",
            payment_provider="alipay",
            provider_attempt_id="ali-zero-1",
            amount=0,
            currency="CNY",
            raw_status="pending",
            raw_snapshot_status=0,
        )
        dao.db.session.add(updated)
        dao.db.session.commit()

        assert (
            AlipayOrder.query.filter_by(provider_attempt_id="ali-zero-1").one().amount
            == 0
        )

        with pytest.raises(ValueError, match="requires a stable identifier"):
            upsert_native_snapshot(
                biz_domain="order",
                payment_provider="alipay",
                provider_attempt_id="",
                amount=0,
                currency="CNY",
                raw_status="pending",
                raw_snapshot_status=0,
            )


def test_native_snapshot_status_does_not_regress_after_success(
    native_payment_split_app: object,
) -> None:
    with native_payment_split_app.app_context():
        paid_snapshot = upsert_native_snapshot(
            biz_domain="order",
            payment_provider="wechatpay",
            native_payment_order_bid="wx-monotonic-1",
            provider_attempt_id="wx-monotonic-1",
            order_bid="order-monotonic-1",
            amount=100,
            currency="CNY",
            raw_status="SUCCESS",
            raw_snapshot_status=1,
        )
        dao.db.session.add(paid_snapshot)
        dao.db.session.commit()

        pending_snapshot = upsert_native_snapshot(
            biz_domain="order",
            payment_provider="wechatpay",
            provider_attempt_id="wx-monotonic-1",
            amount=100,
            currency="CNY",
            raw_status="USERPAYING",
            raw_snapshot_status=0,
        )
        dao.db.session.add(pending_snapshot)
        dao.db.session.commit()

        snapshot = WechatPayOrder.query.filter_by(
            provider_attempt_id="wx-monotonic-1"
        ).one()
        assert snapshot.status == 1
        assert snapshot.raw_status == "SUCCESS"


def test_native_provider_bid_is_unique_per_provider_table(
    native_payment_split_app: object,
) -> None:
    with native_payment_split_app.app_context():
        dao.db.session.add_all(
            [
                AlipayOrder(
                    alipay_order_bid="ali-unique-1",
                    biz_domain="order",
                    provider_attempt_id="ali-unique-1",
                ),
                AlipayOrder(
                    alipay_order_bid="ali-unique-1",
                    biz_domain="billing",
                    provider_attempt_id="ali-unique-2",
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            dao.db.session.commit()
        dao.db.session.rollback()


def test_learner_sync_and_admin_payment_detail_read_alipay_table(
    native_payment_split_app: object,
    monkeypatch: object,
) -> None:
    class FakeAlipayProvider:
        def sync_reference(
            self,
            *,
            provider_reference: object,
            reference_type: object,
            app: object,
        ) -> object:
            _ = app
            assert reference_type == "payment"
            return PaymentNotificationResult(
                order_bid=provider_reference,
                status="WAIT_BUYER_PAY",
                provider_payload={
                    "trade": {
                        "out_trade_no": provider_reference,
                        "trade_status": "WAIT_BUYER_PAY",
                    }
                },
                charge_id=None,
            )

    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        lambda _provider_name: FakeAlipayProvider(),
    )

    with native_payment_split_app.app_context():
        order = Order(
            order_bid="order-native-sync-1",
            shifu_bid="shifu-sync-1",
            user_bid="user-sync-1",
            payable_price=Decimal("199.00"),
            paid_price=Decimal("199.00"),
            payment_channel="alipay",
            status=ORDER_STATUS_TO_BE_PAID,
        )
        snapshot = AlipayOrder(
            alipay_order_bid="ali-sync-1",
            biz_domain="order",
            bill_order_bid="",
            creator_bid="",
            user_bid="user-sync-1",
            shifu_bid="shifu-sync-1",
            order_bid="order-native-sync-1",
            provider_attempt_id="ali-sync-1",
            transaction_id="",
            channel="alipay_qr",
            amount=19900,
            currency="CNY",
            status=0,
            raw_status="pending",
            raw_request="{}",
            raw_response="{}",
            raw_notification="{}",
            metadata_json="{}",
            deleted=0,
        )
        dao.db.session.add_all([order, snapshot])
        dao.db.session.commit()

    details = sync_native_payment_order(
        native_payment_split_app,
        "order-native-sync-1",
        expected_user="user-sync-1",
    )

    assert details["payment_channel"] == "alipay"
    assert details["order_bid"] == "order-native-sync-1"
    assert details["course_id"] == "shifu-sync-1"
    assert details["status"] == 0
    assert set(details) == {"payment_channel", "order_bid", "course_id", "status"}

    with native_payment_split_app.app_context():
        refreshed = AlipayOrder.query.filter_by(order_bid="order-native-sync-1").one()
        assert refreshed.raw_status == "WAIT_BUYER_PAY"
        assert WechatPayOrder.query.count() == 0

        order = Order.query.filter_by(order_bid="order-native-sync-1").one()
        admin_payment = _load_payment_detail(order)
        assert admin_payment is not None
        assert admin_payment.payment_channel == "alipay"
        assert admin_payment.transaction_no == "ali-sync-1"


def test_learner_sync_does_not_mark_paid_when_native_amount_mismatches(
    native_payment_split_app: object,
    monkeypatch: object,
) -> None:
    class FakeAlipayProvider:
        def sync_reference(
            self,
            *,
            provider_reference: object,
            reference_type: object,
            app: object,
        ) -> object:
            _ = app
            assert reference_type == "payment"
            return PaymentNotificationResult(
                order_bid=provider_reference,
                status="TRADE_SUCCESS",
                provider_payload={
                    "trade": {
                        "out_trade_no": provider_reference,
                        "trade_status": "TRADE_SUCCESS",
                        "total_amount": "1.00",
                    }
                },
                charge_id="ali-mismatch-tx-1",
            )

    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        lambda _provider_name: FakeAlipayProvider(),
    )

    with native_payment_split_app.app_context():
        order = Order(
            order_bid="order-native-mismatch-1",
            shifu_bid="shifu-sync-1",
            user_bid="user-sync-1",
            payable_price=Decimal("199.00"),
            paid_price=Decimal("199.00"),
            payment_channel="alipay",
            status=ORDER_STATUS_TO_BE_PAID,
        )
        snapshot = AlipayOrder(
            alipay_order_bid="ali-mismatch-1",
            biz_domain="order",
            user_bid="user-sync-1",
            shifu_bid="shifu-sync-1",
            order_bid="order-native-mismatch-1",
            provider_attempt_id="ali-mismatch-1",
            amount=19900,
            currency="CNY",
            status=0,
            raw_status="pending",
        )
        dao.db.session.add_all([order, snapshot])
        dao.db.session.commit()

    sync_native_payment_order(
        native_payment_split_app,
        "order-native-mismatch-1",
        expected_user="user-sync-1",
    )

    with native_payment_split_app.app_context():
        order = Order.query.filter_by(order_bid="order-native-mismatch-1").one()
        snapshot = AlipayOrder.query.filter_by(order_bid=order.order_bid).one()
        assert order.status == ORDER_STATUS_TO_BE_PAID
        assert snapshot.status == 1
        assert snapshot.transaction_id == "ali-mismatch-tx-1"


def test_common_stripe_sync_dispatches_without_an_outer_unit_of_work(
    native_payment_split_app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with native_payment_split_app.app_context():
        dao.db.session.add(
            Order(
                order_bid="order-common-stripe-sync",
                shifu_bid="shifu-sync-1",
                user_bid="user-sync-1",
                payable_price=Decimal("199.00"),
                paid_price=Decimal("199.00"),
                payment_channel="stripe",
                status=ORDER_STATUS_TO_BE_PAID,
            )
        )
        dao.db.session.commit()

    def _sync_stripe(*_args: object, **_kwargs: object) -> dict[str, object]:
        assert uow.in_unit_of_work() is False
        return {"status": 0}

    monkeypatch.setattr(
        "flaskr.service.order.funs.sync_stripe_checkout_session",
        _sync_stripe,
    )

    details = sync_native_payment_order(
        native_payment_split_app,
        "order-common-stripe-sync",
        expected_user="user-sync-1",
    )

    assert details == {"status": 0}


def test_common_native_sync_holds_the_payment_lifecycle_lock(
    native_payment_split_app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_held = False

    @contextmanager
    def _recording_lock(order_bid: str) -> Iterator[None]:
        nonlocal lock_held
        assert order_bid == "order-common-native-lock"
        lock_held = True
        try:
            yield
        finally:
            lock_held = False

    class _AlipayProvider:
        def sync_reference(self, **_kwargs: object) -> PaymentNotificationResult:
            assert lock_held is True
            return PaymentNotificationResult(
                order_bid="ali-common-native-lock",
                status="WAIT_BUYER_PAY",
                provider_payload={
                    "trade": {
                        "out_trade_no": "ali-common-native-lock",
                        "trade_status": "WAIT_BUYER_PAY",
                    }
                },
            )

    monkeypatch.setattr(
        "flaskr.service.order.funs.payment_lifecycle_lock",
        _recording_lock,
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        lambda _provider_name: _AlipayProvider(),
    )
    with native_payment_split_app.app_context():
        dao.db.session.add_all(
            [
                Order(
                    order_bid="order-common-native-lock",
                    shifu_bid="shifu-sync-1",
                    user_bid="user-sync-1",
                    payable_price=Decimal("199.00"),
                    paid_price=Decimal("199.00"),
                    payment_channel="alipay",
                    status=ORDER_STATUS_TO_BE_PAID,
                ),
                AlipayOrder(
                    alipay_order_bid="ali-common-native-lock",
                    biz_domain="order",
                    user_bid="user-sync-1",
                    shifu_bid="shifu-sync-1",
                    order_bid="order-common-native-lock",
                    provider_attempt_id="ali-common-native-lock",
                    amount=19900,
                    currency="CNY",
                    status=0,
                    raw_status="pending",
                ),
            ]
        )
        dao.db.session.commit()

    sync_native_payment_order(
        native_payment_split_app,
        "order-common-native-lock",
        expected_user="user-sync-1",
    )

    assert lock_held is False


def test_repeated_common_native_sync_notifies_only_once(
    native_payment_split_app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _PaidAlipayProvider:
        def sync_reference(self, **_kwargs: object) -> PaymentNotificationResult:
            return PaymentNotificationResult(
                order_bid="ali-common-native-paid",
                status="TRADE_SUCCESS",
                provider_payload={
                    "trade": {
                        "out_trade_no": "ali-common-native-paid",
                        "trade_status": "TRADE_SUCCESS",
                        "total_amount": "199.00",
                    }
                },
                charge_id="ali-common-native-transaction",
            )

    notifications: list[str] = []
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider",
        lambda _provider_name: _PaidAlipayProvider(),
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_shifu_creator_bid",
        lambda *_args: "teacher-sync-1",
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.set_shifu_context",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.set_user_state",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.send_order_feishu",
        lambda _app, order_bid: notifications.append(order_bid),
    )
    with native_payment_split_app.app_context():
        dao.db.session.add_all(
            [
                Order(
                    order_bid="order-common-native-paid",
                    shifu_bid="shifu-sync-1",
                    user_bid="user-sync-1",
                    payable_price=Decimal("199.00"),
                    paid_price=Decimal("199.00"),
                    payment_channel="alipay",
                    status=ORDER_STATUS_TO_BE_PAID,
                ),
                AlipayOrder(
                    alipay_order_bid="ali-common-native-paid",
                    biz_domain="order",
                    user_bid="user-sync-1",
                    shifu_bid="shifu-sync-1",
                    order_bid="order-common-native-paid",
                    provider_attempt_id="ali-common-native-paid",
                    amount=19900,
                    currency="CNY",
                    status=0,
                    raw_status="pending",
                ),
            ]
        )
        dao.db.session.commit()

    for _ in range(2):
        sync_native_payment_order(
            native_payment_split_app,
            "order-common-native-paid",
            expected_user="user-sync-1",
        )

    assert notifications == ["order-common-native-paid"]
    with native_payment_split_app.app_context():
        order = Order.query.filter_by(order_bid="order-common-native-paid").one()
        assert order.status == ORDER_STATUS_SUCCESS


def test_billing_native_snapshot_and_transaction_lookup_use_wechat_table(
    native_payment_split_app: object,
) -> None:
    with native_payment_split_app.app_context():
        order = BillingOrder(
            bill_order_bid="bill-native-wechat-1",
            creator_bid="creator-1",
            order_type=BILLING_ORDER_TYPE_TOPUP,
            product_bid="bill-product-topup-small",
            subscription_bid="",
            currency="CNY",
            payable_amount=29900,
            paid_amount=0,
            payment_provider="wechatpay",
            channel="wx_pub_qr",
            provider_reference_id="wx-bill-attempt-1",
            status=BILLING_ORDER_STATUS_PENDING,
            failure_code="",
            failure_message="",
            metadata_json={},
        )
        dao.db.session.add(order)
        dao.db.session.commit()

        _persist_billing_native_raw_snapshot(
            order,
            create_if_missing=True,
            provider_attempt_id="wx-bill-attempt-1",
            transaction_id="wx-transaction-1",
            raw_status="SUCCESS",
            raw_request={"out_trade_no": "wx-bill-attempt-1"},
            raw_response={"code_url": "weixin://wxpay/billing"},
            metadata={"latest_source": "test"},
        )
        dao.db.session.commit()

        snapshot = WechatPayOrder.query.filter_by(
            biz_domain="billing",
            bill_order_bid="bill-native-wechat-1",
        ).one()
        assert snapshot.wechatpay_order_bid == "bill-native-wechat-1"
        assert snapshot.provider_attempt_id == "wx-bill-attempt-1"
        assert snapshot.transaction_id == "wx-transaction-1"
        assert AlipayOrder.query.count() == 0

        matched_order = load_billing_order_for_native_event(
            provider="wechatpay",
            provider_attempt_id="",
            transaction_id="wx-transaction-1",
        )
        assert matched_order is not None
        assert matched_order.bill_order_bid == "bill-native-wechat-1"
