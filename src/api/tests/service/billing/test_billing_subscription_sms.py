from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta
from types import SimpleNamespace

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.i18n import load_translations
from flaskr.service.billing.consts import (
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_ORDER_TYPE_SUBSCRIPTION_START,
    BILLING_ORDER_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
)
from flaskr.service.billing.checkout import sync_billing_order
from flaskr.service.billing.models import BillingOrder, BillingSubscription
from flaskr.service.billing.notifications import (
    TASK_NAME as SUBSCRIPTION_SMS_TASK_NAME,
    deliver_subscription_purchase_sms,
    requeue_subscription_purchase_sms,
)
from flaskr.service.billing.tasks import (
    SubscriptionPurchaseSmsRetryableError,
    send_subscription_purchase_sms_task,
)
from flaskr.service.billing.webhooks import apply_billing_stripe_notification
from flaskr.service.billing.webhooks import handle_billing_pingxx_webhook
from flaskr.service.order.payment_providers.base import PaymentNotificationResult
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.models import UserConversion
from flaskr.service.user.repository import create_user_entity, upsert_credential
from tests.common.fixtures.bill_products import build_bill_products


@pytest.fixture
def billing_subscription_sms_app(tmp_path):
    db_path = tmp_path / "billing-subscription-sms.sqlite"
    db_uri = f"sqlite:///{db_path}"

    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI=db_uri,
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": db_uri,
            "ai_shifu_admin": db_uri,
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"check_same_thread": False}},
        TZ="UTC",
        ALIBABA_CLOUD_SMS_SIGN_NAME="TestSign",
        ALIBABA_CLOUD_SMS_SUBSCRIPTION_SUCCESS_TEMPLATE_CODE="TPL-SUB-001",
    )
    dao.db.init_app(app)
    with app.app_context():
        load_translations(app)
        dao.db.create_all()
        dao.db.session.add_all(build_bill_products())
        dao.db.session.commit()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _seed_creator(
    app: Flask,
    *,
    creator_bid: str = "creator-1",
    mobile: str | None = "13800000000",
    language: str = "zh-CN",
) -> None:
    identify = mobile or creator_bid
    with app.app_context():
        create_user_entity(
            user_bid=creator_bid,
            identify=identify,
            nickname="Creator",
            language=language,
            state=USER_STATE_REGISTERED,
        )
        if mobile:
            upsert_credential(
                app,
                user_bid=creator_bid,
                provider_name="phone",
                subject_id=mobile,
                subject_format="phone",
                identifier=mobile,
                metadata={},
                verified=True,
            )
        dao.db.session.commit()


def _notification_payload(
    status: str = "pending",
) -> dict[str, dict[str, dict[str, str]]]:
    return {
        "notifications": {
            "subscription_purchase_sms": {
                "status": status,
                "requested_at": "2026-04-20T00:00:00",
            }
        }
    }


def _create_subscription(
    *,
    subscription_bid: str,
    creator_bid: str = "creator-1",
    product_bid: str = "bill-product-plan-monthly",
    current_period_start_at: datetime,
    current_period_end_at: datetime | None,
) -> BillingSubscription:
    return BillingSubscription(
        subscription_bid=subscription_bid,
        creator_bid=creator_bid,
        product_bid=product_bid,
        status=BILLING_SUBSCRIPTION_STATUS_ACTIVE,
        billing_provider="stripe",
        provider_subscription_id=f"sub_{subscription_bid}",
        provider_customer_id=f"customer-{subscription_bid}",
        current_period_start_at=current_period_start_at,
        current_period_end_at=current_period_end_at,
        cancel_at_period_end=0,
        next_product_bid="",
        metadata_json={},
        created_at=current_period_start_at - timedelta(days=1),
        updated_at=current_period_start_at - timedelta(days=1),
    )


def _create_renewal_order(
    *,
    bill_order_bid: str,
    subscription_bid: str,
    creator_bid: str = "creator-1",
    cycle_start_at: datetime,
    cycle_end_at: datetime,
) -> BillingOrder:
    return BillingOrder(
        bill_order_bid=bill_order_bid,
        creator_bid=creator_bid,
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
        product_bid="bill-product-plan-monthly",
        subscription_bid=subscription_bid,
        currency="CNY",
        payable_amount=990,
        paid_amount=0,
        payment_provider="stripe",
        channel="subscription",
        provider_reference_id=f"sub_{subscription_bid}",
        status=BILLING_ORDER_STATUS_PENDING,
        metadata_json={
            "provider_reference_type": "subscription",
            "renewal_cycle_start_at": cycle_start_at.isoformat(),
            "renewal_cycle_end_at": cycle_end_at.isoformat(),
        },
    )


def _create_paid_start_order(
    *,
    bill_order_bid: str,
    subscription_bid: str,
    creator_bid: str = "creator-1",
    paid_at: datetime,
    metadata_json: dict | None = None,
) -> BillingOrder:
    return BillingOrder(
        bill_order_bid=bill_order_bid,
        creator_bid=creator_bid,
        order_type=BILLING_ORDER_TYPE_SUBSCRIPTION_START,
        product_bid="bill-product-plan-monthly",
        subscription_bid=subscription_bid,
        currency="CNY",
        payable_amount=990,
        paid_amount=990,
        payment_provider="stripe",
        channel="checkout_session",
        provider_reference_id="cs_subscription_sms",
        status=BILLING_ORDER_STATUS_PAID,
        paid_at=paid_at,
        metadata_json=metadata_json or _notification_payload(),
    )


def _create_pending_topup_order(
    *,
    bill_order_bid: str,
    creator_bid: str = "creator-1",
    charge_id: str = "ch_billing_feishu_topup_1",
) -> BillingOrder:
    return BillingOrder(
        bill_order_bid=bill_order_bid,
        creator_bid=creator_bid,
        order_type=BILLING_ORDER_TYPE_TOPUP,
        product_bid="bill-product-topup-small",
        subscription_bid="",
        currency="CNY",
        payable_amount=5000,
        paid_amount=0,
        payment_provider="pingxx",
        channel="alipay_qr",
        provider_reference_id=charge_id,
        status=BILLING_ORDER_STATUS_PENDING,
        metadata_json={},
    )


def test_sync_billing_order_enqueues_subscription_purchase_sms_once(
    billing_subscription_sms_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = billing_subscription_sms_app
    cycle_start_at = datetime(2026, 5, 1, 0, 0, 0)
    cycle_end_at = datetime(2026, 6, 1, 0, 0, 0)
    enqueued: list[str] = []

    class FakeStripeProvider:
        def sync_reference(self, *, provider_reference: str, reference_type: str, app):
            assert reference_type == "subscription"
            return PaymentNotificationResult(
                order_bid="",
                status="manual_sync",
                provider_payload={
                    "subscription": {
                        "id": provider_reference,
                        "customer": "cus_sync_sms_1",
                        "status": "active",
                        "current_period_start": int(cycle_start_at.timestamp()),
                        "current_period_end": int(cycle_end_at.timestamp()),
                        "cancel_at_period_end": False,
                    }
                },
                charge_id=None,
            )

    monkeypatch.setattr(
        "flaskr.service.billing.checkout.get_payment_provider",
        lambda channel: FakeStripeProvider(),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.paid_side_effects._enqueue_subscription_purchase_sms",
        lambda app, *, bill_order_bid: (
            enqueued.append(bill_order_bid) or {"status": "enqueued"}
        ),
    )

    with app.app_context():
        subscription = _create_subscription(
            subscription_bid="sub-sync-sms-1",
            current_period_start_at=cycle_start_at - timedelta(days=30),
            current_period_end_at=cycle_start_at,
        )
        order = _create_renewal_order(
            bill_order_bid="billing-sync-sms-1",
            subscription_bid=subscription.subscription_bid,
            cycle_start_at=cycle_start_at,
            cycle_end_at=cycle_end_at,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.commit()

    first_payload = sync_billing_order(
        app,
        "creator-1",
        "billing-sync-sms-1",
        {},
    )
    second_payload = sync_billing_order(
        app,
        "creator-1",
        "billing-sync-sms-1",
        {},
    )

    assert first_payload.status == "paid"
    assert second_payload.status == "paid"
    assert enqueued == ["billing-sync-sms-1"]

    with app.app_context():
        order = BillingOrder.query.filter_by(bill_order_bid="billing-sync-sms-1").one()
        notification = order.metadata_json["notifications"]["subscription_purchase_sms"]
        assert notification["status"] == "pending"
        assert notification["requested_at"] is not None


def test_stripe_subscription_webhook_enqueues_subscription_purchase_sms_once(
    billing_subscription_sms_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = billing_subscription_sms_app
    cycle_start_at = datetime(2026, 7, 1, 0, 0, 0)
    cycle_end_at = datetime(2026, 8, 1, 0, 0, 0)
    enqueued: list[str] = []

    monkeypatch.setattr(
        "flaskr.service.billing.paid_side_effects._enqueue_subscription_purchase_sms",
        lambda app, *, bill_order_bid: (
            enqueued.append(bill_order_bid) or {"status": "enqueued"}
        ),
    )

    with app.app_context():
        subscription = _create_subscription(
            subscription_bid="sub-webhook-sms-1",
            current_period_start_at=cycle_start_at - timedelta(days=30),
            current_period_end_at=cycle_start_at,
        )
        order = _create_renewal_order(
            bill_order_bid="billing-webhook-sms-1",
            subscription_bid=subscription.subscription_bid,
            cycle_start_at=cycle_start_at,
            cycle_end_at=cycle_end_at,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.commit()

    notification = PaymentNotificationResult(
        order_bid="",
        status="customer.subscription.updated",
        provider_payload={
            "type": "customer.subscription.updated",
            "created": int(cycle_end_at.timestamp()),
            "data": {
                "object": {
                    "id": "sub_sub-webhook-sms-1",
                    "customer": "cus_webhook_sms_1",
                    "status": "active",
                    "current_period_start": int(cycle_start_at.timestamp()),
                    "current_period_end": int(cycle_end_at.timestamp()),
                    "cancel_at_period_end": False,
                    "metadata": {},
                }
            },
        },
        charge_id=None,
    )

    first_payload, first_status = apply_billing_stripe_notification(app, notification)
    second_payload, second_status = apply_billing_stripe_notification(app, notification)

    assert first_status == 200
    assert second_status == 200
    assert first_payload["status"] == "paid"
    assert second_payload["status"] == "paid"
    assert enqueued == ["billing-webhook-sms-1"]

    with app.app_context():
        order = BillingOrder.query.filter_by(
            bill_order_bid="billing-webhook-sms-1"
        ).one()
        notification_payload = order.metadata_json["notifications"][
            "subscription_purchase_sms"
        ]
        assert notification_payload["status"] == "pending"


def test_sync_billing_order_sends_subscription_paid_feishu_once(
    billing_subscription_sms_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = billing_subscription_sms_app
    _seed_creator(app)
    cycle_start_at = datetime(2026, 7, 1, 0, 0, 0)
    cycle_end_at = datetime(2026, 8, 1, 0, 0, 0)
    captured: list[dict[str, object]] = []

    class FakeStripeProvider:
        def sync_reference(self, *, provider_reference: str, reference_type: str, app):
            assert reference_type == "subscription"
            return PaymentNotificationResult(
                order_bid="",
                status="manual_sync",
                provider_payload={
                    "subscription": {
                        "id": provider_reference,
                        "customer": "cus_sync_feishu_1",
                        "status": "active",
                        "current_period_start": int(cycle_start_at.timestamp()),
                        "current_period_end": int(cycle_end_at.timestamp()),
                        "cancel_at_period_end": False,
                    }
                },
                charge_id=None,
            )

    monkeypatch.setattr(
        "flaskr.service.billing.checkout.get_payment_provider",
        lambda channel: FakeStripeProvider(),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.paid_side_effects._enqueue_subscription_purchase_sms",
        lambda app, *, bill_order_bid: {"status": "enqueued"},
    )
    monkeypatch.setattr(
        "flaskr.service.billing.notifications.send_notify",
        lambda app, title, msgs: (
            captured.append({"title": title, "msgs": list(msgs)}) or {"ok": True}
        ),
    )

    with app.app_context():
        dao.db.session.add(
            UserConversion(
                user_id="creator-1",
                conversion_id="conversion-sync-feishu-1",
                conversion_source="ads",
                conversion_status=1,
            )
        )
        subscription = _create_subscription(
            subscription_bid="sub-sync-feishu-1",
            current_period_start_at=cycle_start_at - timedelta(days=30),
            current_period_end_at=cycle_start_at,
        )
        order = _create_renewal_order(
            bill_order_bid="billing-sync-feishu-1",
            subscription_bid=subscription.subscription_bid,
            cycle_start_at=cycle_start_at,
            cycle_end_at=cycle_end_at,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.commit()

    first_payload = sync_billing_order(
        app,
        "creator-1",
        "billing-sync-feishu-1",
        {},
    )
    second_payload = sync_billing_order(
        app,
        "creator-1",
        "billing-sync-feishu-1",
        {},
    )

    assert first_payload.status == "paid"
    assert second_payload.status == "paid"
    assert len(captured) == 1
    assert captured[0]["title"] == "购买订阅套餐通知"
    assert "手机号：13800000000" in captured[0]["msgs"]
    assert "昵称：Creator" in captured[0]["msgs"]
    assert "套餐名称：轻量版" in captured[0]["msgs"]
    assert "实付金额：CNY 9.90" in captured[0]["msgs"]
    assert "订单来源：用户购买 (Stripe)" in captured[0]["msgs"]
    assert "渠道：ads" in captured[0]["msgs"]
    assert "订阅续费-轻量版-CNY 9.90" in captured[0]["msgs"]

    with app.app_context():
        order = BillingOrder.query.filter_by(
            bill_order_bid="billing-sync-feishu-1"
        ).one()
        notification = order.metadata_json["notifications"]["billing_paid_feishu"]
        assert notification["status"] == "sent"
        assert notification["sent_at"] is not None


def test_pingxx_topup_webhook_sends_billing_paid_feishu_once(
    billing_subscription_sms_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = billing_subscription_sms_app
    _seed_creator(app)
    captured: list[dict[str, object]] = []

    monkeypatch.setattr(
        "flaskr.service.billing.notifications.send_notify",
        lambda app, title, msgs: (
            captured.append({"title": title, "msgs": list(msgs)}) or {"ok": True}
        ),
    )

    with app.app_context():
        dao.db.session.add(
            UserConversion(
                user_id="creator-1",
                conversion_id="conversion-topup-feishu-1",
                conversion_source="campaign",
                conversion_status=1,
            )
        )
        dao.db.session.add(
            _create_pending_topup_order(
                bill_order_bid="billing-topup-feishu-1",
                charge_id="ch_billing_feishu_topup_1",
            )
        )
        dao.db.session.commit()

    body = {
        "type": "charge.succeeded",
        "data": {
            "object": {
                "id": "ch_billing_feishu_topup_1",
                "order_no": "billing-topup-feishu-1",
                "paid": True,
                "time_paid": 1712577600,
            }
        },
    }
    first_payload, first_status = handle_billing_pingxx_webhook(app, body)
    second_payload, second_status = handle_billing_pingxx_webhook(app, body)

    assert first_status == 200
    assert second_status == 200
    assert first_payload["status"] == "paid"
    assert second_payload["status"] == "paid"
    assert len(captured) == 1
    assert captured[0]["title"] == "购买积分包通知"
    assert "手机号：13800000000" in captured[0]["msgs"]
    assert "积分包名称：20 积分包" in captured[0]["msgs"]
    assert "实付金额：CNY 50.00" in captured[0]["msgs"]
    assert "订单来源：用户购买 (Pingxx)" in captured[0]["msgs"]
    assert "渠道：campaign" in captured[0]["msgs"]
    assert "积分包-20 积分包-CNY 50.00" in captured[0]["msgs"]

    with app.app_context():
        order = BillingOrder.query.filter_by(
            bill_order_bid="billing-topup-feishu-1"
        ).one()
        notification = order.metadata_json["notifications"]["billing_paid_feishu"]
        assert notification["status"] == "sent"


def test_sync_billing_topup_sends_billing_paid_feishu_once(
    billing_subscription_sms_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = billing_subscription_sms_app
    _seed_creator(app)
    captured: list[dict[str, object]] = []

    class FakePingxxProvider:
        def sync_reference(self, *, provider_reference: str, reference_type: str, app):
            assert provider_reference == "ch_billing_feishu_topup_sync_1"
            assert reference_type == "charge"
            return PaymentNotificationResult(
                order_bid="",
                status="manual_sync",
                provider_payload={
                    "charge": {
                        "id": provider_reference,
                        "order_no": "billing-topup-sync-feishu-1",
                        "paid": True,
                        "time_paid": 1712577600,
                        "channel": "alipay_qr",
                    }
                },
                charge_id=provider_reference,
            )

    monkeypatch.setattr(
        "flaskr.service.billing.checkout.get_payment_provider",
        lambda channel: FakePingxxProvider(),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.notifications.send_notify",
        lambda app, title, msgs: (
            captured.append({"title": title, "msgs": list(msgs)}) or {"ok": True}
        ),
    )

    with app.app_context():
        dao.db.session.add(
            UserConversion(
                user_id="creator-1",
                conversion_id="conversion-topup-sync-feishu-1",
                conversion_source="sync-campaign",
                conversion_status=1,
            )
        )
        dao.db.session.add(
            _create_pending_topup_order(
                bill_order_bid="billing-topup-sync-feishu-1",
                charge_id="ch_billing_feishu_topup_sync_1",
            )
        )
        dao.db.session.commit()

    first_payload = sync_billing_order(
        app,
        "creator-1",
        "billing-topup-sync-feishu-1",
        {},
    )
    second_payload = sync_billing_order(
        app,
        "creator-1",
        "billing-topup-sync-feishu-1",
        {},
    )

    assert first_payload.status == "paid"
    assert second_payload.status == "paid"
    assert len(captured) == 1
    assert captured[0]["title"] == "购买积分包通知"
    assert "手机号：13800000000" in captured[0]["msgs"]
    assert "积分包名称：20 积分包" in captured[0]["msgs"]
    assert "实付金额：CNY 50.00" in captured[0]["msgs"]
    assert "订单来源：用户购买 (Pingxx)" in captured[0]["msgs"]
    assert "渠道：sync-campaign" in captured[0]["msgs"]
    assert "积分包-20 积分包-CNY 50.00" in captured[0]["msgs"]

    with app.app_context():
        order = BillingOrder.query.filter_by(
            bill_order_bid="billing-topup-sync-feishu-1"
        ).one()
        notification = order.metadata_json["notifications"]["billing_paid_feishu"]
        assert notification["status"] == "sent"


def test_deliver_subscription_purchase_sms_marks_sent_and_stays_idempotent(
    billing_subscription_sms_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = billing_subscription_sms_app
    _seed_creator(app)
    cycle_start_at = datetime(2026, 4, 20, 0, 0, 0)
    cycle_end_at = datetime(2026, 5, 20, 0, 0, 0)
    captured: list[dict[str, object]] = []

    monkeypatch.setattr(
        "flaskr.service.billing.notifications.send_sms_ali",
        lambda app, mobile, *, template_code, template_params, sign_name=None: (
            captured.append(
                {
                    "mobile": mobile,
                    "template_code": template_code,
                    "template_params": dict(template_params),
                }
            )
            or SimpleNamespace(ok=True)
        ),
    )

    with app.app_context():
        subscription = _create_subscription(
            subscription_bid="sub-task-sent-1",
            current_period_start_at=cycle_start_at,
            current_period_end_at=cycle_end_at,
        )
        order = _create_paid_start_order(
            bill_order_bid="billing-task-sent-1",
            subscription_bid=subscription.subscription_bid,
            paid_at=cycle_start_at,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.commit()

    first_payload = deliver_subscription_purchase_sms(
        app,
        bill_order_bid="billing-task-sent-1",
    )
    second_payload = deliver_subscription_purchase_sms(
        app,
        bill_order_bid="billing-task-sent-1",
    )

    assert first_payload["status"] == "sent"
    assert second_payload["status"] == "noop"
    assert len(captured) == 1
    assert captured[0]["template_code"] == "TPL-SUB-001"
    assert captured[0]["mobile"] == "13800000000"
    assert captured[0]["template_params"]["product"] == "轻量版"
    assert captured[0]["template_params"]["date"] == "2026-05-20 00:00:00"

    with app.app_context():
        order = BillingOrder.query.filter_by(bill_order_bid="billing-task-sent-1").one()
        notification = order.metadata_json["notifications"]["subscription_purchase_sms"]
        assert notification["status"] == "sent"
        assert notification["sent_at"] is not None


def test_deliver_subscription_purchase_sms_skips_when_creator_has_no_mobile(
    billing_subscription_sms_app,
) -> None:
    app = billing_subscription_sms_app
    _seed_creator(app, creator_bid="creator-no-mobile", mobile=None)
    cycle_start_at = datetime(2026, 4, 20, 0, 0, 0)
    cycle_end_at = datetime(2026, 5, 20, 0, 0, 0)

    with app.app_context():
        subscription = _create_subscription(
            subscription_bid="sub-task-no-mobile-1",
            creator_bid="creator-no-mobile",
            current_period_start_at=cycle_start_at,
            current_period_end_at=cycle_end_at,
        )
        order = _create_paid_start_order(
            bill_order_bid="billing-task-no-mobile-1",
            subscription_bid=subscription.subscription_bid,
            creator_bid="creator-no-mobile",
            paid_at=cycle_start_at,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.commit()

    payload = deliver_subscription_purchase_sms(
        app,
        bill_order_bid="billing-task-no-mobile-1",
    )

    assert payload["status"] == "skipped_no_mobile"

    with app.app_context():
        order = BillingOrder.query.filter_by(
            bill_order_bid="billing-task-no-mobile-1"
        ).one()
        notification = order.metadata_json["notifications"]["subscription_purchase_sms"]
        assert notification["status"] == "skipped_no_mobile"
        assert notification["error_code"] == "missing_mobile"


def test_deliver_subscription_purchase_sms_fails_when_date_is_missing(
    billing_subscription_sms_app,
) -> None:
    app = billing_subscription_sms_app
    _seed_creator(app, creator_bid="creator-missing-date")
    cycle_start_at = datetime(2026, 4, 20, 0, 0, 0)

    with app.app_context():
        subscription = _create_subscription(
            subscription_bid="sub-task-missing-date-1",
            creator_bid="creator-missing-date",
            current_period_start_at=cycle_start_at,
            current_period_end_at=None,
        )
        order = _create_paid_start_order(
            bill_order_bid="billing-task-missing-date-1",
            subscription_bid=subscription.subscription_bid,
            creator_bid="creator-missing-date",
            paid_at=cycle_start_at,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.commit()

    payload = deliver_subscription_purchase_sms(
        app,
        bill_order_bid="billing-task-missing-date-1",
    )

    assert payload["status"] == "failed_missing_date"

    with app.app_context():
        order = BillingOrder.query.filter_by(
            bill_order_bid="billing-task-missing-date-1"
        ).one()
        notification = order.metadata_json["notifications"]["subscription_purchase_sms"]
        assert notification["status"] == "failed_missing_date"
        assert notification["error_code"] == "missing_date"


def test_send_subscription_purchase_sms_task_raises_retryable_error_on_provider_failure(
    billing_subscription_sms_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = billing_subscription_sms_app
    _seed_creator(app, creator_bid="creator-provider-failure")
    cycle_start_at = datetime(2026, 4, 20, 0, 0, 0)
    cycle_end_at = datetime(2026, 5, 20, 0, 0, 0)

    with app.app_context():
        subscription = _create_subscription(
            subscription_bid="sub-task-provider-failure-1",
            creator_bid="creator-provider-failure",
            current_period_start_at=cycle_start_at,
            current_period_end_at=cycle_end_at,
        )
        order = _create_paid_start_order(
            bill_order_bid="billing-task-provider-failure-1",
            subscription_bid=subscription.subscription_bid,
            creator_bid="creator-provider-failure",
            paid_at=cycle_start_at,
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.commit()

    monkeypatch.setitem(
        sys.modules,
        "app",
        types.SimpleNamespace(create_app=lambda: app),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.notifications.send_sms_ali",
        lambda app, mobile, *, template_code, template_params, sign_name=None: None,
    )

    with pytest.raises(SubscriptionPurchaseSmsRetryableError):
        send_subscription_purchase_sms_task(
            bill_order_bid="billing-task-provider-failure-1"
        )

    with app.app_context():
        order = BillingOrder.query.filter_by(
            bill_order_bid="billing-task-provider-failure-1"
        ).one()
        notification = order.metadata_json["notifications"]["subscription_purchase_sms"]
        assert notification["status"] == "failed_provider"
        assert notification["error_code"] == "provider_failed"


def test_requeue_subscription_purchase_sms_enqueues_failed_provider_order(
    billing_subscription_sms_app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = billing_subscription_sms_app
    cycle_start_at = datetime(2026, 4, 20, 0, 0, 0)
    cycle_end_at = datetime(2026, 5, 20, 0, 0, 0)
    captured_kwargs: list[dict[str, str]] = []

    class FakeTask:
        def apply_async(self, kwargs):
            captured_kwargs.append(dict(kwargs))

    fake_celery = SimpleNamespace(tasks={SUBSCRIPTION_SMS_TASK_NAME: FakeTask()})
    monkeypatch.setattr(
        "flaskr.common.celery_app.get_celery_app",
        lambda flask_app=None: fake_celery,
    )

    with app.app_context():
        subscription = _create_subscription(
            subscription_bid="sub-task-requeue-1",
            current_period_start_at=cycle_start_at,
            current_period_end_at=cycle_end_at,
        )
        order = _create_paid_start_order(
            bill_order_bid="billing-task-requeue-1",
            subscription_bid=subscription.subscription_bid,
            paid_at=cycle_start_at,
            metadata_json=_notification_payload(status="failed_provider"),
        )
        dao.db.session.add(subscription)
        dao.db.session.add(order)
        dao.db.session.commit()

    payload = requeue_subscription_purchase_sms(
        app,
        bill_order_bid="billing-task-requeue-1",
    )

    assert payload["status"] == "enqueued"
    assert payload["notification_status"] == "failed_provider"
    assert captured_kwargs == [{"bill_order_bid": "billing-task-requeue-1"}]
