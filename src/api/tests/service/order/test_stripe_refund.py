from flaskr.dao import db
from flaskr.service.order.consts import ORDER_STATUS_REFUND, ORDER_STATUS_SUCCESS
from flaskr.service.order.funs import refund_order_payment, get_payment_details
from flaskr.service.order.models import Order, StripeOrder
from flaskr.service.order.payment_providers.base import PaymentRefundResult


class DummyStripeRefundProvider:
    def __init__(self, result: PaymentRefundResult):
        self._result = result

    def refund_payment(self, *, request, app):  # pylint: disable=unused-argument
        return self._result


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


def test_refund_order_payment_updates_status(app, monkeypatch):
    with app.app_context():
        order = _ensure_order(ORDER_STATUS_SUCCESS, "order-refund-1")

        stripe_order = StripeOrder(
            order_bid=order.order_bid,
            stripe_order_bid="stripe-order",
            user_bid=order.user_bid,
            shifu_bid=order.shifu_bid,
            payment_intent_id="pi_test",
            checkout_session_id="",
            latest_charge_id="ch_test",
            amount=100,
            currency="usd",
            status=1,
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

        result = PaymentRefundResult(
            provider_reference="re_test",
            raw_response={"id": "re_test", "status": "succeeded"},
            status="succeeded",
        )

        provider = DummyStripeRefundProvider(result)
        monkeypatch.setattr(
            "flaskr.service.order.funs.get_payment_provider",
            lambda channel: provider,
        )

        payload = refund_order_payment(
            app, order.order_bid, reason="requested_by_customer"
        )

    assert payload["status"] == "succeeded"
    with app.app_context():
        refreshed_order = Order.query.filter(Order.order_bid == order.order_bid).first()
        refreshed_stripe_order = StripeOrder.query.filter(
            StripeOrder.order_bid == order.order_bid
        ).first()
        assert refreshed_order.status == ORDER_STATUS_REFUND
        assert refreshed_stripe_order.status == 2
        assert "last_refund_id" in refreshed_stripe_order.metadata_json


def test_get_payment_details_returns_stripe_payload(app):
    with app.app_context():
        order_bid = "order-details-1"
        order = _ensure_order(ORDER_STATUS_SUCCESS, order_bid)
        stripe_order = StripeOrder(
            order_bid=order.order_bid,
            stripe_order_bid="stripe-order",
            user_bid=order.user_bid,
            shifu_bid=order.shifu_bid,
            payment_intent_id="pi_test",
            checkout_session_id="cs_test",
            latest_charge_id="ch_test",
            amount=100,
            currency="usd",
            status=1,
            receipt_url="",
            payment_method="pm_test",
            failure_code="",
            failure_message="",
            metadata_json="{}",
            payment_intent_object="{}",
            checkout_session_object="{}",
        )
        db.session.add(stripe_order)
        db.session.commit()

    details = get_payment_details(app, order_bid)
    assert details["payment_channel"] == "stripe"
    assert details["payment_intent_id"] == "pi_test"
    assert details["checkout_session_id"] == "cs_test"
    assert details["metadata"] == {}
