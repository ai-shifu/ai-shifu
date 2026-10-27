"""Cover provider-owned Stripe payment, recovery, and signed event contracts."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import stripe as stripe_sdk
from flask import Flask
from flaskr.service.order.payment_providers import stripe
from flaskr.service.order.payment_providers.base import (
    PaymentRefundRequest,
    PaymentRequest,
)


def _sdk_object(payload: dict) -> Mock:
    return Mock(to_dict=Mock(return_value=payload))


@pytest.fixture
def stripe_client(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    client = SimpleNamespace(
        PaymentIntent=Mock(),
        Subscription=Mock(),
        Refund=Mock(),
        Coupon=Mock(),
        checkout=SimpleNamespace(Session=Mock()),
        Webhook=stripe_sdk.Webhook,
    )
    monkeypatch.setattr(
        stripe,
        "get_stripe_client_options",
        lambda _app: (client, {"api_key": "sk-test-scoped"}),
    )
    monkeypatch.setattr(
        stripe,
        "get_config",
        lambda key: "whsec-test" if key == "STRIPE_WEBHOOK_SECRET" else False,
    )
    return client


def _request(**overrides: object) -> PaymentRequest:
    values = {
        "order_bid": "order-test",
        "user_bid": "user-test",
        "shifu_bid": "course-test",
        "amount": 12345,
        "currency": "usd",
        "channel": "payment_intent",
        "subject": "Course",
        "body": "Course",
        "client_ip": "127.0.0.1",
    }
    return PaymentRequest(**(values | overrides))


def _checkout_options(**overrides: object) -> dict:
    return {
        "mode": "checkout_session",
        "success_url": "https://example.test/success",
        "cancel_url": "https://example.test/cancel",
        "line_items": [{"price": "price-test", "quantity": 1}],
    } | overrides


def test_payment_intent_creation_preserves_exact_amount_and_scoped_credentials(
    stripe_client: SimpleNamespace,
) -> None:
    payload = {
        "id": "pi-test",
        "client_secret": "secret-test",
        "latest_charge": "ch-test",
    }
    stripe_client.PaymentIntent.create.return_value = _sdk_object(payload)
    result = stripe.StripeProvider().create_payment(
        request=_request(
            extra={
                "metadata": _sdk_object({"business_kind": "course"}),
                "payment_intent_params": {"capture_method": "manual"},
            }
        ),
        app=Flask(__name__),
    )
    stripe_client.PaymentIntent.create.assert_called_once_with(
        amount=12345,
        currency="usd",
        capture_method="manual",
        api_key="sk-test-scoped",
        metadata={
            "business_kind": "course",
            "order_bid": "order-test",
            "user_bid": "user-test",
            "shifu_bid": "course-test",
        },
    )
    assert result.provider_reference == "pi-test"
    assert result.client_secret == "secret-test"
    assert result.extra["latest_charge_id"] == "ch-test"
    assert result.extra["payment_intent_object"] == payload
    assert stripe.StripeProvider()._ensure_client(Flask(__name__)) is stripe_client


@pytest.mark.parametrize("missing", ["success_url", "cancel_url", "line_items"])
def test_checkout_missing_required_input_never_creates_a_session(
    missing: str, stripe_client: SimpleNamespace
) -> None:
    options = _checkout_options()
    options.pop(missing)
    with pytest.raises(RuntimeError, match="requires"):
        stripe.StripeProvider().create_payment(
            request=_request(extra=options), app=Flask(__name__)
        )
    stripe_client.checkout.Session.create.assert_not_called()


def test_subscription_discount_is_once_only_and_session_tracks_payment_evidence(
    stripe_client: SimpleNamespace,
) -> None:
    stripe_client.Coupon.create.return_value = _sdk_object({"id": "coupon-test"})
    stripe_client.checkout.Session.create.return_value = _sdk_object(
        {
            "id": "cs-test",
            "payment_intent": "pi-test",
            "url": "https://checkout.example.test/session",
        }
    )
    stripe_client.PaymentIntent.retrieve.return_value = _sdk_object(
        {"id": "pi-test", "latest_charge": "ch-test"}
    )
    request = _request(
        extra=_checkout_options(
            subscription_one_time_discount_amount=345,
            customer_email="learner@example.test",
            metadata={"bill_order_bid": "billing-test"},
            session_params={
                "metadata": _sdk_object({"session_field": "retained"}),
                "subscription_data": {
                    "metadata": _sdk_object({"subscription_bid": "sub-test"})
                },
            },
        )
    )
    result = stripe.StripeProvider().create_subscription(
        request=request, app=Flask(__name__)
    )
    coupon = stripe_client.Coupon.create.call_args.kwargs
    assert coupon["amount_off"] == 345
    assert coupon["duration"] == "once"
    assert coupon["currency"] == "usd"
    assert coupon["idempotency_key"] == "order-test:subscription-first-invoice-discount"
    assert coupon["api_key"] == "sk-test-scoped"
    params = stripe_client.checkout.Session.create.call_args.kwargs
    assert params["mode"] == "subscription"
    assert params["discounts"] == [{"coupon": "coupon-test"}]
    assert params["customer_email"] == "learner@example.test"
    assert params["payment_method_types"] == ["card"]
    assert params["metadata"]["session_field"] == "retained"
    assert params["metadata"]["bill_order_bid"] == "billing-test"
    assert params["subscription_data"]["metadata"]["subscription_bid"] == "sub-test"
    assert params["subscription_data"]["metadata"]["order_bid"] == "order-test"
    assert "mode" not in request.extra["session_params"]
    assert result.extra["payment_intent_id"] == "pi-test"
    assert result.extra["latest_charge_id"] == "ch-test"
    assert result.extra["discounts"] == [{"coupon": "coupon-test"}]
    stripe_client.PaymentIntent.retrieve.assert_called_once_with(
        "pi-test", api_key="sk-test-scoped"
    )


def test_explicit_discounts_are_not_combined_with_generated_subscription_coupon(
    stripe_client: SimpleNamespace,
) -> None:
    stripe_client.checkout.Session.create.return_value = _sdk_object({"id": "cs-test"})
    result = stripe.StripeProvider().create_subscription(
        request=_request(
            extra=_checkout_options(
                discounts=[{"promotion_code": "promo-test"}],
                subscription_one_time_discount_amount=100,
            )
        ),
        app=Flask(__name__),
    )
    stripe_client.Coupon.create.assert_not_called()
    assert result.extra["discounts"] == [{"promotion_code": "promo-test"}]
    assert result.extra["payment_intent_object"] == {}


@pytest.mark.parametrize("discount", [0, 100])
def test_failed_checkout_cleans_up_only_its_generated_coupon(
    discount: int, stripe_client: SimpleNamespace
) -> None:
    stripe_client.Coupon.create.return_value = {"id": "coupon-test"}
    failure = RuntimeError("checkout unavailable")
    stripe_client.checkout.Session.create.side_effect = failure
    with pytest.raises(RuntimeError, match="checkout unavailable") as raised:
        stripe.StripeProvider().create_subscription(
            request=_request(
                extra=_checkout_options(subscription_one_time_discount_amount=discount)
            ),
            app=Flask(__name__),
        )
    assert raised.value is failure
    if discount:
        stripe_client.Coupon.delete.assert_called_once_with(
            "coupon-test", api_key="sk-test-scoped"
        )
    else:
        stripe_client.Coupon.delete.assert_not_called()


@pytest.mark.parametrize(
    ("method", "cancelled"),
    [("cancel_subscription", True), ("resume_subscription", False)],
)
@pytest.mark.parametrize("with_provider_id", [False, True])
def test_subscription_lifecycle_preserves_id_and_cancel_state(
    method: str, cancelled: bool, with_provider_id: bool, stripe_client: SimpleNamespace
) -> None:
    payload = {"status": "active", "cancel_at_period_end": cancelled}
    if with_provider_id:
        payload["id"] = "sub-provider"
    stripe_client.Subscription.modify.return_value = _sdk_object(payload)
    result = getattr(stripe.StripeProvider(), method)(
        subscription_bid="local-sub",
        provider_subscription_id="sub-requested",
        app=Flask(__name__),
    )
    stripe_client.Subscription.modify.assert_called_once_with(
        "sub-requested",
        cancel_at_period_end=cancelled,
        metadata={"subscription_bid": "local-sub"},
        api_key="sk-test-scoped",
    )
    assert result.provider_reference == (
        "sub-provider" if with_provider_id else "sub-requested"
    )
    assert result.status == "active"
    assert result.extra == {"cancel_at_period_end": cancelled}


@pytest.mark.parametrize(
    ("reference_type", "payload", "charge"),
    [
        ("session", {"payment_intent": "pi-test"}, "ch-first"),
        ("checkout_session", {"payment_intent": "pi-test"}, "ch-latest"),
        ("payment", {}, None),
        ("payment_intent", {}, "ch-latest"),
        ("subscription", {}, None),
    ],
)
def test_sync_reference_preserves_order_evidence_and_charge_fallback(
    reference_type: str,
    payload: dict,
    charge: str | None,
    stripe_client: SimpleNamespace,
) -> None:
    session = {"id": "cs-test", "metadata": {"order_bid": "order-test"}} | payload
    intent = {
        "id": "pi-test",
        "metadata": {"order_bid": "order-test"},
        "latest_charge": "ch-latest" if charge == "ch-latest" else "",
        "charges": {"data": [{"id": "ch-first"}]},
    }
    subscription = {"id": "sub-test", "metadata": {"order_bid": "order-test"}}
    stripe_client.checkout.Session.retrieve.return_value = session
    stripe_client.PaymentIntent.retrieve.return_value = intent
    stripe_client.Subscription.retrieve.return_value = subscription
    result = stripe.StripeProvider().sync_reference(
        provider_reference="reference-test",
        reference_type=f" {reference_type.upper()} ",
        app=Flask(__name__),
    )
    assert result.order_bid == "order-test"
    assert result.status == "manual_sync"
    assert result.charge_id == charge
    if reference_type == "subscription":
        assert result.provider_payload == {"subscription": subscription}
        stripe_client.Subscription.retrieve.assert_called_once_with(
            "reference-test", api_key="sk-test-scoped"
        )
    elif reference_type == "payment_intent":
        assert result.provider_payload == {"payment_intent": intent}
    else:
        assert result.provider_payload["checkout_session"] == session
        if not payload:
            stripe_client.PaymentIntent.retrieve.assert_not_called()


@pytest.mark.parametrize("operation", ["sync_reference", "cancel_payment"])
def test_unsupported_provider_reference_type_is_rejected(
    operation: str, stripe_client: SimpleNamespace
) -> None:
    with pytest.raises(RuntimeError, match="Unsupported Stripe reference type"):
        getattr(stripe.StripeProvider(), operation)(
            provider_reference="ref-test", reference_type="unknown", app=Flask(__name__)
        )
    stripe_client.PaymentIntent.cancel.assert_not_called()
    stripe_client.checkout.Session.expire.assert_not_called()


@pytest.mark.parametrize(
    ("reference_type", "status", "recovered"),
    [
        ("payment_intent", "canceled", True),
        ("payment_intent", "processing", False),
        ("checkout_session", "open", False),
    ],
)
def test_cancellation_failure_is_only_recovered_after_terminal_provider_state(
    reference_type: str, status: str, recovered: bool, stripe_client: SimpleNamespace
) -> None:
    failure = RuntimeError("cancellation unavailable")
    stripe_client.PaymentIntent.cancel.side_effect = failure
    stripe_client.checkout.Session.expire.side_effect = failure
    stripe_client.PaymentIntent.retrieve.return_value = {"status": status}
    stripe_client.checkout.Session.retrieve.return_value = {"status": status}
    if recovered:
        result = stripe.StripeProvider().cancel_payment(
            provider_reference="reference-test",
            reference_type=reference_type,
            app=Flask(__name__),
        )
        assert result.status == "cancelled"
        assert result.raw_response == {"status": status}
    else:
        with pytest.raises(RuntimeError, match="cancellation unavailable") as raised:
            stripe.StripeProvider().cancel_payment(
                provider_reference="reference-test",
                reference_type=reference_type,
                app=Flask(__name__),
            )
        assert raised.value is failure


def test_successful_intent_cancellation_accepts_sdk_objects(
    stripe_client: SimpleNamespace,
) -> None:
    stripe_client.PaymentIntent.cancel.return_value = _sdk_object(
        {"id": "pi-test", "status": "canceled"}
    )
    result = stripe.StripeProvider().cancel_payment(
        provider_reference="pi-test",
        reference_type="payment_intent",
        app=Flask(__name__),
    )
    assert result.status == "cancelled"
    stripe_client.PaymentIntent.cancel.assert_called_once_with(
        "pi-test", api_key="sk-test-scoped"
    )


@pytest.mark.parametrize("sdk_object", [False, True])
def test_expiry_accepts_mapping_and_sdk_object(
    sdk_object: bool, stripe_client: SimpleNamespace
) -> None:
    payload = {"id": "cs-test", "status": "expired"}
    stripe_client.checkout.Session.expire.return_value = (
        _sdk_object(payload) if sdk_object else payload
    )
    assert (
        stripe.StripeProvider().expire_checkout_session(
            session_id="cs-test", app=Flask(__name__)
        )
        == payload
    )
    stripe_client.checkout.Session.expire.assert_called_once_with(
        "cs-test", api_key="sk-test-scoped"
    )


def _webhook_payload(event: dict) -> tuple[str, str]:
    body = json.dumps(event)
    timestamp = int(time.time())
    signature = hmac.new(
        b"whsec-test", f"{timestamp}.{body}".encode(), hashlib.sha256
    ).hexdigest()
    return body, f"t={timestamp},v1={signature}"


@pytest.mark.parametrize(
    ("event_object", "charge"),
    [
        (
            {"metadata": {"order_bid": "order-test"}, "latest_charge": "ch-latest"},
            "ch-latest",
        ),
        (
            {
                "metadata": {"order_bid": "order-test"},
                "charges": {"data": [{"id": "ch-first"}]},
            },
            "ch-first",
        ),
        ({"metadata": {"order_bid": "order-test"}}, None),
    ],
)
@pytest.mark.parametrize("as_bytes", [False, True])
def test_signed_webhook_is_verified_by_stripe_sdk(
    event_object: dict,
    charge: str | None,
    as_bytes: bool,
    stripe_client: SimpleNamespace,
) -> None:
    del stripe_client
    event = {"type": "payment_intent.succeeded", "data": {"object": event_object}}
    body, signature = _webhook_payload(event)
    result = stripe.StripeProvider().handle_notification(
        payload={
            "raw_body": body.encode() if as_bytes else body,
            "sig_header": signature,
        },
        app=Flask(__name__),
    )
    assert result.order_bid == "order-test"
    assert result.charge_id == charge
    assert result.status == "payment_intent.succeeded"
    assert result.provider_payload == event


def test_forged_webhook_signature_is_rejected(stripe_client: SimpleNamespace) -> None:
    del stripe_client
    body, signature = _webhook_payload(
        {"type": "payment_intent.succeeded", "data": {"object": {}}}
    )
    with pytest.raises(stripe_sdk.SignatureVerificationError):
        stripe.StripeProvider().verify_webhook(
            headers={"stripe-signature": signature},
            raw_body=body + " ",
            app=Flask(__name__),
        )


@pytest.mark.parametrize("missing_secret", [False, True])
def test_webhook_missing_authentication_configuration_is_rejected(
    missing_secret: bool,
    stripe_client: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del stripe_client
    if missing_secret:
        monkeypatch.setattr(stripe, "get_config", lambda _key: "")
    with pytest.raises(
        RuntimeError,
        match="must be configured" if missing_secret else "signature header missing",
    ):
        stripe.StripeProvider().verify_webhook(
            headers={}, raw_body=b"{}", app=Flask(__name__)
        )


@pytest.mark.parametrize(
    ("metadata", "reference_key"),
    [
        ({"payment_intent_id": "pi-test", "charge_id": "ch-test"}, "payment_intent"),
        ({"charge_id": "ch-test"}, "charge"),
    ],
)
def test_refund_passes_amount_reason_and_prefers_intent_reference(
    metadata: dict, reference_key: str, stripe_client: SimpleNamespace
) -> None:
    stripe_client.Refund.create.return_value = _sdk_object(
        {"id": "refund-test", "status": "succeeded"}
    )
    result = stripe.StripeProvider().refund_payment(
        request=PaymentRefundRequest(
            order_bid="order-test",
            amount=123,
            reason="requested_by_customer",
            metadata=metadata,
        ),
        app=Flask(__name__),
    )
    params = stripe_client.Refund.create.call_args.kwargs
    assert params[reference_key] == (
        "pi-test" if reference_key == "payment_intent" else "ch-test"
    )
    assert params["amount"] == 123
    assert params["reason"] == "requested_by_customer"
    assert params["metadata"]["order_bid"] == "order-test"
    assert params["api_key"] == "sk-test-scoped"
    if reference_key == "payment_intent":
        assert "charge" not in params
    assert result.provider_reference == "refund-test"
    assert result.status == "succeeded"


def test_refund_requires_a_provider_reference(stripe_client: SimpleNamespace) -> None:
    with pytest.raises(RuntimeError, match="requires payment_intent_id or charge_id"):
        stripe.StripeProvider().refund_payment(
            request=PaymentRefundRequest(order_bid="order-test"), app=Flask(__name__)
        )
    stripe_client.Refund.create.assert_not_called()
