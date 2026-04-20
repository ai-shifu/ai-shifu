from flaskr.dao import db
from flaskr.service.order.consts import ORDER_STATUS_TO_BE_PAID, ORDER_STATUS_SUCCESS
from flaskr.service.order.funs import handle_stripe_webhook
from flaskr.service.order.models import Order, StripeOrder
from flaskr.service.order.payment_providers.base import PaymentNotificationResult


class DummyStripeProvider:
    def __init__(self, notification: PaymentNotificationResult):
        self._notification = notification

    def handle_notification(self, *, payload, app):
        return self._notification


def _ensure_order(status, order_bid):
    order = Order.query.filter(Order.order_bid == order_bid).first()
    if not order:
        order = Order(order_bid=order_bid, shifu_bid="shifu-1", user_bid="user-1")
        db.session.add(order)
        db.session.commit()
    order.status = status
    order.payment_channel = "stripe"
    db.session.commit()
    return order


def test_handle_stripe_webhook_marks_order_paid(app, monkeypatch):
    with app.app_context():
        order = _ensure_order(ORDER_STATUS_TO_BE_PAID, "order-webhook-1")

        stripe_order = StripeOrder(
            order_bid=order.order_bid,
            stripe_order_bid="stripe-order",
            user_bid=order.user_bid,
            shifu_bid=order.shifu_bid,
            payment_intent_id="pi_test",
            checkout_session_id="",
            latest_charge_id="",
            amount=100,
            currency="usd",
            status=0,
            receipt_url="",
            payment_method="",
            failure_code="",
            failure_message="",
            metadata_json="{}",
            payment_intent_object="{}",
            checkout_session_object="{}",
        )
        db.session.add(stripe_order)
        db.session.commit()

        notification = PaymentNotificationResult(
            order_bid=order.order_bid,
            status="payment_intent.succeeded",
            provider_payload={
                "type": "payment_intent.succeeded",
                "data": {
                    "object": {
                        "id": "pi_test",
                        "metadata": {"order_bid": order.order_bid},
                        "latest_charge": "ch_test",
                        "charges": {"data": [{"id": "ch_test", "receipt_url": "url"}]},
                        "payment_method": "pm_test",
                    }
                },
            },
            charge_id="ch_test",
        )

        provider = DummyStripeProvider(notification)
        monkeypatch.setattr(
            "flaskr.service.order.funs.get_payment_provider",
            lambda channel: provider,
        )
        monkeypatch.setattr(
            "flaskr.service.order.funs.send_order_feishu",
            lambda *args, **kwargs: None,
        )

        payload, status_code = handle_stripe_webhook(app, b"{}", "sig")

    assert status_code == 200
    assert payload["status"] == "paid"
    with app.app_context():
        refreshed_order = Order.query.filter(Order.order_bid == order.order_bid).first()
        refreshed_stripe_order = StripeOrder.query.filter(
            StripeOrder.order_bid == order.order_bid
        ).first()
        assert refreshed_order.status == ORDER_STATUS_SUCCESS
        assert refreshed_stripe_order.latest_charge_id == "ch_test"
        assert refreshed_stripe_order.status == 1
