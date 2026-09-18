"""Security regressions for learner-triggered Stripe synchronization."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from flaskr import dao
from flaskr.service.common.models import AppError
from flaskr.service.order.consts import (
    ORDER_STATUS_REFUND,
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_TO_BE_PAID,
)
from flaskr.service.order.funs import (
    handle_stripe_webhook,
    sync_stripe_checkout_session,
)
from flaskr.service.order.models import Order, StripeOrder
from flaskr.service.order.payment_providers.base import PaymentNotificationResult
from flaskr.service.order.payment_providers.stripe import StripeProvider


def _seed_stripe_order(
    *,
    order_bid: str,
    session_id: str,
    attempt_bid: str,
    status: int = ORDER_STATUS_TO_BE_PAID,
    amount: int = 20000,
) -> None:
    dao.db.session.add_all(
        [
            Order(
                order_bid=order_bid,
                shifu_bid=f"course-{order_bid}",
                user_bid="owner-user",
                payable_price=Decimal("200.00"),
                paid_price=Decimal("200.00"),
                payment_channel="stripe",
                status=status,
                deleted=0,
            ),
            StripeOrder(
                stripe_order_bid=attempt_bid,
                biz_domain="order",
                order_bid=order_bid,
                user_bid="owner-user",
                shifu_bid=f"course-{order_bid}",
                checkout_session_id=session_id,
                payment_intent_id=f"pi_{attempt_bid}",
                amount=amount,
                currency="cny",
                status=0,
            ),
        ]
    )
    dao.db.session.commit()


def _paid_sync_result(
    *,
    order_bid: str,
    session_id: str,
    payment_intent_id: str,
    amount: int = 20000,
) -> PaymentNotificationResult:
    return PaymentNotificationResult(
        order_bid=order_bid,
        status="manual_sync",
        provider_payload={
            "checkout_session": {
                "id": session_id,
                "payment_status": "paid",
                "status": "complete",
                "amount_total": amount,
                "currency": "cny",
                "payment_intent": payment_intent_id,
                "metadata": {"order_bid": order_bid},
            },
            "payment_intent": {
                "id": payment_intent_id,
                "status": "succeeded",
                "amount": amount,
                "currency": "cny",
                "metadata": {"order_bid": order_bid},
            },
        },
        charge_id="ch_paid",
    )


def test_stripe_provider_sync_falls_back_to_payment_intent_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = StripeProvider()
    monkeypatch.setattr(
        provider,
        "retrieve_checkout_session",
        lambda **_kwargs: {
            "id": "cs_legacy",
            "metadata": {},
            "payment_intent": "pi_legacy",
        },
    )
    monkeypatch.setattr(
        provider,
        "retrieve_payment_intent",
        lambda **_kwargs: {
            "id": "pi_legacy",
            "metadata": {"order_bid": "legacy-order"},
        },
    )

    result = provider.sync_reference(
        provider_reference="cs_legacy",
        reference_type="checkout_session",
        app=object(),
    )

    assert result.order_bid == "legacy-order"


def test_stripe_sync_rejects_a_caller_supplied_foreign_session_before_provider_call(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_called = False

    class Provider:
        def sync_reference(self, **_kwargs: object) -> None:
            nonlocal provider_called
            provider_called = True

    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: Provider()
    )
    with app.app_context():
        _seed_stripe_order(
            order_bid="sync-foreign-session",
            session_id="cs_owned",
            attempt_bid="attempt-owned",
        )

    with pytest.raises(AppError, match="Order Not Found"):
        sync_stripe_checkout_session(
            app,
            "sync-foreign-session",
            session_id="cs_foreign",
            expected_user="owner-user",
        )

    assert provider_called is False


def test_stripe_sync_rejects_a_superseded_local_attempt_before_provider_call(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_called = False

    class Provider:
        def sync_reference(self, **_kwargs: object) -> None:
            nonlocal provider_called
            provider_called = True

    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: Provider()
    )
    with app.app_context():
        _seed_stripe_order(
            order_bid="sync-superseded",
            session_id="cs_old",
            attempt_bid="attempt-old",
        )
        dao.db.session.add(
            StripeOrder(
                stripe_order_bid="attempt-current",
                biz_domain="order",
                order_bid="sync-superseded",
                user_bid="owner-user",
                shifu_bid="course-sync-superseded",
                checkout_session_id="cs_current",
                payment_intent_id="pi_attempt-current",
                amount=20000,
                currency="cny",
                status=0,
            )
        )
        dao.db.session.commit()

    with pytest.raises(AppError, match="Order Not Found"):
        sync_stripe_checkout_session(
            app,
            "sync-superseded",
            session_id="cs_old",
            expected_user="owner-user",
        )

    assert provider_called is False


@pytest.mark.parametrize(
    (
        "case_id",
        "remote_order_bid",
        "remote_intent_id",
        "remote_amount",
        "order_status",
    ),
    [
        (
            "metadata",
            "another-order",
            "pi_attempt-metadata",
            20000,
            ORDER_STATUS_TO_BE_PAID,
        ),
        (
            "intent",
            "sync-provider-intent",
            "pi_foreign",
            20000,
            ORDER_STATUS_TO_BE_PAID,
        ),
        (
            "amount",
            "sync-provider-amount",
            "pi_attempt-amount",
            19900,
            ORDER_STATUS_TO_BE_PAID,
        ),
        (
            "status",
            "sync-provider-status",
            "pi_attempt-status",
            20000,
            ORDER_STATUS_REFUND,
        ),
    ],
)
def test_stripe_sync_rejects_provider_or_lifecycle_mismatches_without_mutation(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    remote_order_bid: str,
    remote_intent_id: str,
    remote_amount: int,
    order_status: int,
) -> None:
    order_bid = f"sync-provider-{case_id}"
    attempt_bid = f"attempt-{case_id}"
    result = _paid_sync_result(
        order_bid=remote_order_bid,
        session_id="cs_current",
        payment_intent_id=remote_intent_id,
        amount=remote_amount,
    )
    provider = SimpleNamespace(sync_reference=lambda **_kwargs: result)
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: provider
    )
    with app.app_context():
        _seed_stripe_order(
            order_bid=order_bid,
            session_id="cs_current",
            attempt_bid=attempt_bid,
            status=order_status,
        )

    with pytest.raises(AppError):
        sync_stripe_checkout_session(
            app,
            order_bid,
            session_id="cs_current",
            expected_user="owner-user",
        )

    with app.app_context():
        order = Order.query.filter_by(order_bid=order_bid).one()
        attempt = StripeOrder.query.filter_by(stripe_order_bid=attempt_bid).one()
        assert order.status == order_status
        assert attempt.status == 0
        assert attempt.checkout_session_id == "cs_current"
        assert attempt.payment_intent_id == f"pi_{attempt_bid}"


def test_stripe_sync_completes_the_current_matching_attempt(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _paid_sync_result(
        order_bid="sync-valid",
        session_id="cs_valid",
        payment_intent_id="pi_attempt-valid",
    )
    provider = SimpleNamespace(sync_reference=lambda **_kwargs: result)
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: provider
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.send_order_feishu", lambda *_args: None
    )
    monkeypatch.setattr("flaskr.service.order.funs.set_user_state", lambda *_args: None)
    with app.app_context():
        _seed_stripe_order(
            order_bid="sync-valid",
            session_id="cs_valid",
            attempt_bid="attempt-valid",
        )

    details = sync_stripe_checkout_session(
        app,
        "sync-valid",
        session_id="cs_valid",
        expected_user="owner-user",
    )

    assert details["status"] == 1
    with app.app_context():
        assert Order.query.filter_by(order_bid="sync-valid").one().status == (
            ORDER_STATUS_SUCCESS
        )


def test_stripe_sync_accepts_legacy_session_metadata_from_the_payment_intent(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _paid_sync_result(
        order_bid="sync-legacy-metadata",
        session_id="cs_legacy-metadata",
        payment_intent_id="pi_attempt-legacy-metadata",
    )
    result.provider_payload["checkout_session"]["metadata"] = {}
    provider = SimpleNamespace(sync_reference=lambda **_kwargs: result)
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: provider
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.send_order_feishu", lambda *_args: None
    )
    monkeypatch.setattr("flaskr.service.order.funs.set_user_state", lambda *_args: None)
    with app.app_context():
        _seed_stripe_order(
            order_bid="sync-legacy-metadata",
            session_id="cs_legacy-metadata",
            attempt_bid="attempt-legacy-metadata",
        )

    details = sync_stripe_checkout_session(
        app,
        "sync-legacy-metadata",
        session_id="cs_legacy-metadata",
        expected_user="owner-user",
    )

    assert details["status"] == 1


def test_stripe_sync_is_idempotent_for_the_completed_matching_attempt(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _paid_sync_result(
        order_bid="sync-idempotent",
        session_id="cs_idempotent",
        payment_intent_id="pi_attempt-idempotent",
    )
    provider = SimpleNamespace(sync_reference=lambda **_kwargs: result)
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: provider
    )
    with app.app_context():
        _seed_stripe_order(
            order_bid="sync-idempotent",
            session_id="cs_idempotent",
            attempt_bid="attempt-idempotent",
            status=ORDER_STATUS_SUCCESS,
        )
        StripeOrder.query.filter_by(
            stripe_order_bid="attempt-idempotent"
        ).one().status = 1
        dao.db.session.commit()

    details = sync_stripe_checkout_session(
        app,
        "sync-idempotent",
        session_id="cs_idempotent",
        expected_user="owner-user",
    )

    assert details["status"] == 1


def test_stripe_sync_does_not_fulfill_a_complete_but_unpaid_session(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _paid_sync_result(
        order_bid="sync-unpaid",
        session_id="cs_unpaid",
        payment_intent_id="pi_attempt-unpaid",
    )
    result.provider_payload["checkout_session"]["payment_status"] = "unpaid"
    result.provider_payload["payment_intent"]["status"] = "requires_payment_method"
    provider = SimpleNamespace(sync_reference=lambda **_kwargs: result)
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: provider
    )
    with app.app_context():
        _seed_stripe_order(
            order_bid="sync-unpaid",
            session_id="cs_unpaid",
            attempt_bid="attempt-unpaid",
        )

    details = sync_stripe_checkout_session(
        app,
        "sync-unpaid",
        session_id="cs_unpaid",
        expected_user="owner-user",
    )

    assert details["status"] == 0
    with app.app_context():
        order = Order.query.filter_by(order_bid="sync-unpaid").one()
        attempt = StripeOrder.query.filter_by(stripe_order_bid="attempt-unpaid").one()
        assert order.status == ORDER_STATUS_TO_BE_PAID
        assert attempt.status == 0


def test_stripe_webhook_does_not_fulfill_a_complete_but_unpaid_session(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order_bid = "webhook-unpaid"
    attempt_bid = "webhook-unpaid"
    notification = PaymentNotificationResult(
        order_bid=order_bid,
        status="checkout.session.completed",
        provider_payload={
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_webhook-unpaid",
                    "metadata": {"order_bid": order_bid},
                    "currency": "cny",
                    "payment_status": "unpaid",
                    "status": "complete",
                    "amount_total": 20000,
                    "payment_intent": "pi_webhook-unpaid",
                }
            },
        },
    )
    provider = SimpleNamespace(verify_webhook=lambda **_kwargs: notification)
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: provider
    )
    with app.app_context():
        _seed_stripe_order(
            order_bid=order_bid,
            session_id="cs_webhook-unpaid",
            attempt_bid=attempt_bid,
        )

    payload, status_code = handle_stripe_webhook(app, b"{}", "signature")

    assert status_code == 202
    assert payload["status"] == "ignored"
    with app.app_context():
        assert (
            Order.query.filter_by(order_bid=order_bid).one().status
            == ORDER_STATUS_TO_BE_PAID
        )


@pytest.mark.parametrize(
    "event_type",
    ["checkout.session.completed", "checkout.session.async_payment_succeeded"],
)
def test_stripe_checkout_webhook_persists_the_refundable_payment_intent(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    event_type: str,
) -> None:
    case_id = event_type.rsplit(".", 1)[-1]
    order_bid = f"webhook-persist-intent-{case_id}"
    attempt_bid = f"webhook-persist-intent-{case_id}"
    session_id = f"cs_webhook-persist-intent-{case_id}"
    notification = PaymentNotificationResult(
        order_bid=order_bid,
        status=event_type,
        provider_payload={
            "type": event_type,
            "data": {
                "object": {
                    "id": session_id,
                    "metadata": {
                        "order_bid": order_bid,
                        "stripe_order_bid": attempt_bid,
                    },
                    "currency": "cny",
                    "payment_status": "paid",
                    "status": "complete",
                    "amount_total": 20000,
                    "payment_intent": "pi_late-created",
                }
            },
        },
    )
    provider = SimpleNamespace(verify_webhook=lambda **_kwargs: notification)
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: provider
    )
    monkeypatch.setattr(
        "flaskr.service.order.funs.send_order_feishu", lambda *_args: None
    )
    monkeypatch.setattr("flaskr.service.order.funs.set_user_state", lambda *_args: None)
    with app.app_context():
        _seed_stripe_order(
            order_bid=order_bid,
            session_id=session_id,
            attempt_bid=attempt_bid,
        )
        StripeOrder.query.filter_by(
            stripe_order_bid=attempt_bid
        ).one().payment_intent_id = ""
        dao.db.session.commit()

    payload, status_code = handle_stripe_webhook(app, b"{}", "signature")

    assert status_code == 200
    assert payload["status"] == "paid"
    with app.app_context():
        attempt = StripeOrder.query.filter_by(stripe_order_bid=attempt_bid).one()
        assert attempt.payment_intent_id == "pi_late-created"


@pytest.mark.parametrize(
    ("session_id", "expected_status", "expected_http_status"),
    [
        ("cs_async-failed", 4, 200),
        ("cs_superseded", 0, 202),
    ],
)
def test_stripe_async_failure_only_updates_its_current_session(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    session_id: str,
    expected_status: int,
    expected_http_status: int,
) -> None:
    order_bid = f"webhook-async-failed-{session_id}"
    attempt_bid = f"attempt-async-failed-{session_id}"
    notification = PaymentNotificationResult(
        order_bid=order_bid,
        status="checkout.session.async_payment_failed",
        provider_payload={
            "type": "checkout.session.async_payment_failed",
            "data": {
                "object": {
                    "id": session_id,
                    "metadata": {
                        "order_bid": order_bid,
                        "stripe_order_bid": attempt_bid,
                    },
                    "currency": "cny",
                    "amount_total": 20000,
                    "payment_intent": f"pi_{attempt_bid}",
                }
            },
        },
    )
    provider = SimpleNamespace(verify_webhook=lambda **_kwargs: notification)
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: provider
    )
    with app.app_context():
        _seed_stripe_order(
            order_bid=order_bid,
            session_id="cs_async-failed",
            attempt_bid=attempt_bid,
        )

    payload, status_code = handle_stripe_webhook(app, b"{}", "signature")

    assert status_code == expected_http_status
    assert payload["status"] == ("failed" if expected_status == 4 else "acknowledged")
    with app.app_context():
        attempt = StripeOrder.query.filter_by(stripe_order_bid=attempt_bid).one()
        assert attempt.status == expected_status


@pytest.mark.parametrize(
    "event_type",
    ["payment_intent.payment_failed", "payment_intent.canceled"],
)
def test_stripe_webhook_ignores_delayed_events_from_a_superseded_intent(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    event_type: str,
) -> None:
    order_bid = f"webhook-stale-{event_type}"
    attempt_bid = f"attempt-stale-{event_type}"
    notification = PaymentNotificationResult(
        order_bid=order_bid,
        status=event_type,
        provider_payload={
            "type": event_type,
            "data": {
                "object": {
                    "id": "pi_superseded",
                    "metadata": {"order_bid": order_bid},
                    "last_payment_error": {
                        "code": "card_declined",
                        "message": "declined",
                    },
                }
            },
        },
    )
    provider = SimpleNamespace(verify_webhook=lambda **_kwargs: notification)
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: provider
    )
    with app.app_context():
        _seed_stripe_order(
            order_bid=order_bid,
            session_id=f"cs_{attempt_bid}",
            attempt_bid=attempt_bid,
        )

    payload, status_code = handle_stripe_webhook(app, b"{}", "signature")

    assert status_code == 202
    assert payload["status"] == "acknowledged"
    with app.app_context():
        attempt = StripeOrder.query.filter_by(stripe_order_bid=attempt_bid).one()
        assert attempt.payment_intent_id == f"pi_{attempt_bid}"
        assert attempt.status == 0
        assert attempt.failure_code in {None, ""}


@pytest.mark.parametrize(
    ("case_id", "event_type", "object_id", "amount"),
    [
        ("session", "checkout.session.completed", "cs_foreign", 20000),
        ("amount", "checkout.session.completed", "cs_webhook-amount", 19900),
        ("intent", "payment_intent.succeeded", "pi_foreign", 20000),
    ],
)
def test_stripe_webhook_rejects_mismatched_provider_objects_without_mutation(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    event_type: str,
    object_id: str,
    amount: int,
) -> None:
    order_bid = f"webhook-{case_id}"
    attempt_bid = f"webhook-{case_id}"
    expected_session_id = f"cs_{attempt_bid}"
    expected_intent_id = f"pi_{attempt_bid}"
    is_session = event_type == "checkout.session.completed"
    data_object: dict[str, object] = {
        "id": object_id,
        "metadata": {"order_bid": order_bid},
        "currency": "cny",
    }
    if is_session:
        data_object.update(
            {
                "payment_status": "paid",
                "status": "complete",
                "amount_total": amount,
                "payment_intent": expected_intent_id,
            }
        )
    else:
        data_object.update({"status": "succeeded", "amount": amount})
    notification = PaymentNotificationResult(
        order_bid=order_bid,
        status=event_type,
        provider_payload={"type": event_type, "data": {"object": data_object}},
        charge_id="ch_webhook",
    )
    provider = SimpleNamespace(verify_webhook=lambda **_kwargs: notification)
    monkeypatch.setattr(
        "flaskr.service.order.funs.get_payment_provider", lambda _name: provider
    )
    with app.app_context():
        _seed_stripe_order(
            order_bid=order_bid,
            session_id=expected_session_id,
            attempt_bid=attempt_bid,
        )

    payload, status_code = handle_stripe_webhook(app, b"{}", "signature")

    assert status_code == 202
    assert payload["status"] == "ignored"
    with app.app_context():
        assert (
            Order.query.filter_by(order_bid=order_bid).one().status
            == ORDER_STATUS_TO_BE_PAID
        )
        attempt = StripeOrder.query.filter_by(stripe_order_bid=attempt_bid).one()
        assert attempt.status == 0
        assert attempt.checkout_session_id == expected_session_id
        assert attempt.payment_intent_id == expected_intent_id
