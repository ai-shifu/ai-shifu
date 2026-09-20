"""Integrate Stripe payments with legacy orders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from flaskr.service.common.stripe_client import get_stripe_client_options
from flaskr.service.config import get_config

from . import register_payment_provider
from .base import (
    PaymentCancellationResult,
    PaymentCreationResult,
    PaymentNotificationResult,
    PaymentProvider,
    PaymentRefundRequest,
    PaymentRefundResult,
    PaymentRequest,
    SubscriptionUpdateResult,
)

if TYPE_CHECKING:
    from flask import Flask


_REFUND_STATUSES = frozenset(
    {"pending", "requires_action", "succeeded", "failed", "canceled"}
)
_ACTIVE_REFUND_STATUSES = frozenset({"pending", "requires_action", "succeeded"})


def _refund_payload(value: object) -> dict[str, Any]:
    """Read a complete SDK object without accepting malformed responses."""
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, Mapping):
        message = "Stripe refund response must be an object"
        # Provider failures use RuntimeError at the payment adapter boundary.
        raise RuntimeError(message)  # noqa: TRY004
    return dict(value)


def _refund_reference(value: object) -> str:
    """Read a Stripe reference in either expanded or identifier form."""
    if isinstance(value, Mapping):
        value = value.get("id")
    return value if isinstance(value, str) else ""


def _validate_refund_request(request: PaymentRefundRequest) -> None:
    """Require an exact financial target before querying or issuing a refund."""
    metadata = request.metadata
    currency = metadata.get("currency")
    if (
        not isinstance(request.amount, int)
        or isinstance(request.amount, bool)
        or request.amount <= 0
        or not isinstance(currency, str)
        or len(currency) != 3
        or not currency.isascii()
        or not currency.isalpha()
        or not isinstance(request.order_bid, str)
        or not request.order_bid.strip()
    ):
        message = "Stripe refund requires an exact amount, currency, and order"
        raise RuntimeError(message)
    if not any(metadata.get(key) for key in ("payment_intent_id", "charge_id")):
        message = "Stripe refund requires a payment reference"
        raise RuntimeError(message)
    for key in (
        "payment_intent_id",
        "charge_id",
        "bill_order_bid",
        "creator_bid",
        "refund_operation_bid",
        "refund_reference_id",
    ):
        value = metadata.get(key)
        if value is not None and (
            not isinstance(value, str) or (value and not value.strip())
        ):
            message = f"Stripe refund has invalid {key} metadata"
            raise RuntimeError(message)
    if metadata.get("order_bid", request.order_bid) != request.order_bid:
        message = "Stripe refund order metadata conflicts with its request"
        raise RuntimeError(message)


def _validated_refund_result(
    value: object,
    *,
    request: PaymentRefundRequest,
    match_amount: bool = True,
    match_operation: bool = True,
    reference_id: str = "",
) -> PaymentRefundResult:
    """Validate provider ownership and financial evidence before adoption."""
    payload = _refund_payload(value)
    refund_id = payload.get("id")
    amount = payload.get("amount")
    currency = payload.get("currency")
    status = payload.get("status")
    if (
        payload.get("object") != "refund"
        or not isinstance(refund_id, str)
        or not refund_id.strip()
        or (reference_id and refund_id != reference_id)
        or not isinstance(amount, int)
        or isinstance(amount, bool)
        or amount <= 0
        or (match_amount and amount != request.amount)
        or not isinstance(currency, str)
        or currency.lower() != request.metadata["currency"].lower()
        or not isinstance(status, str)
        or status not in _REFUND_STATUSES
    ):
        message = "Stripe refund has inconsistent financial evidence"
        raise RuntimeError(message)
    for expected_key, actual_key in (
        ("payment_intent_id", "payment_intent"),
        ("charge_id", "charge"),
    ):
        expected = request.metadata.get(expected_key)
        if expected and _refund_reference(payload.get(actual_key)) != expected:
            message = "Stripe refund belongs to a different payment"
            raise RuntimeError(message)
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        message = "Stripe refund ownership metadata is missing"
        # Malformed remote data is a provider failure, not a caller type error.
        raise RuntimeError(message)  # noqa: TRY004
    expected_owner = {"order_bid": request.order_bid}
    for key in ("bill_order_bid", "creator_bid"):
        if request.metadata.get(key):
            expected_owner[key] = request.metadata[key]
    if any(metadata.get(key) != expected for key, expected in expected_owner.items()):
        message = "Stripe refund belongs to a different owner"
        raise RuntimeError(message)
    operation = request.metadata.get("refund_operation_bid")
    remote_operation = metadata.get("refund_operation_bid")
    if remote_operation is not None and not isinstance(remote_operation, str):
        message = "Stripe refund operation metadata is malformed"
        raise RuntimeError(message)
    if (
        match_operation
        and operation
        and remote_operation
        and remote_operation != operation
    ):
        message = "Stripe refund belongs to a different operation"
        raise RuntimeError(message)
    return PaymentRefundResult(
        provider_reference=refund_id, raw_response=payload, status=status
    )


class StripeProvider(PaymentProvider):
    """Stripe payment provider implementation."""

    channel = "stripe"

    def _ensure_client(self, app: Flask) -> object:
        return get_stripe_client_options(app)[0]

    def _client_options(self, app: Flask) -> tuple[Any, dict[str, Any]]:
        return get_stripe_client_options(app)

    def create_payment(
        self, *, request: PaymentRequest, app: Flask
    ) -> PaymentCreationResult:
        """Create a payment through this provider."""
        stripe, request_options = self._client_options(app)
        options: dict[str, Any] = request.extra or {}
        mode = (options.get("mode") or request.channel or "payment_intent").lower()
        metadata = options.get("metadata", {}) or {}
        if hasattr(metadata, "to_dict"):
            metadata = metadata.to_dict()
        metadata.setdefault("order_bid", request.order_bid)
        metadata.setdefault("user_bid", request.user_bid)
        metadata.setdefault("shifu_bid", request.shifu_bid)

        if mode == "checkout_session":
            success_url = options.get("success_url")
            cancel_url = options.get("cancel_url")
            if not success_url or not cancel_url:
                message = "Stripe checkout session requires success and cancel URLs"
                raise RuntimeError(message)

            session_params = options.get("session_params", {})
            params: dict[str, Any] = {
                "mode": "payment",
                "success_url": success_url,
                "cancel_url": cancel_url,
                **session_params,
            }

            line_items = options.get("line_items")
            if not line_items:
                message = "Stripe checkout session requires line items"
                raise RuntimeError(message)
            params["line_items"] = line_items
            discounts = options.get("discounts")
            if discounts:
                params["discounts"] = discounts
            subscription_discount_amount = int(
                options.get("subscription_one_time_discount_amount") or 0
            )
            coupon_id = ""
            if (
                params.get("mode") == "subscription"
                and subscription_discount_amount > 0
                and not discounts
            ):
                coupon = stripe.Coupon.create(
                    amount_off=subscription_discount_amount,
                    currency=(request.currency or "cny").lower(),
                    duration="once",
                    metadata=metadata,
                    idempotency_key=(
                        f"{request.order_bid}:subscription-first-invoice-discount"
                    ),
                    **request_options,
                )
                coupon_payload = (
                    coupon.to_dict() if hasattr(coupon, "to_dict") else coupon
                )
                coupon_id = coupon_payload["id"]
                params["discounts"] = [{"coupon": coupon_id}]

            customer_email = options.get("customer_email")
            if customer_email:
                params["customer_email"] = customer_email

            if params.get("mode") == "subscription":
                subscription_data = dict(params.get("subscription_data") or {})
                subscription_metadata = subscription_data.get("metadata") or {}
                if hasattr(subscription_metadata, "to_dict"):
                    subscription_metadata = subscription_metadata.to_dict()
                subscription_data["metadata"] = {
                    **metadata,
                    **dict(subscription_metadata),
                }
                params["subscription_data"] = subscription_data
            else:
                payment_intent_data = options.get("payment_intent_data", {})
                existing_metadata = payment_intent_data.get("metadata")
                if existing_metadata:
                    if hasattr(existing_metadata, "to_dict"):
                        existing_metadata = existing_metadata.to_dict()
                    # Caller keys are kept, but the order evidence wins: it is
                    # what a later sync matches the order against.
                    metadata = {**dict(existing_metadata), **metadata}
                payment_intent_data["metadata"] = metadata
                params["payment_intent_data"] = payment_intent_data
            # The session itself has to carry the evidence as well. A
            # payment-mode session has no PaymentIntent until the buyer starts
            # paying, so a sync that runs before that can only read metadata
            # from the session.
            session_metadata = params.get("metadata")
            if hasattr(session_metadata, "to_dict"):
                session_metadata = session_metadata.to_dict()
            params["metadata"] = {**dict(session_metadata or {}), **metadata}
            is_subscription_mode = params.get("mode") == "subscription"
            params["payment_method_types"] = ["card"]
            if not is_subscription_mode and get_config("STRIPE_ALIPAY_ENABLED"):
                params["payment_method_types"].append("alipay")
            if not is_subscription_mode and get_config("STRIPE_WECHAT_PAY_ENABLED"):
                params["payment_method_types"].append("wechat_pay")
                params["payment_method_options"] = {"wechat_pay": {"client": "web"}}

            try:
                session = stripe.checkout.Session.create(**params, **request_options)
            except Exception:
                if coupon_id:
                    try:
                        stripe.Coupon.delete(coupon_id, **request_options)
                    except Exception as cleanup_error:  # pragma: no cover
                        app.logger.warning(
                            "Failed to clean up Stripe coupon %s: %s",
                            coupon_id,
                            cleanup_error,
                        )
                raise
            session_dict = session.to_dict()
            payment_intent_id = session_dict.get("payment_intent")
            latest_charge_id = ""
            payment_intent_object: dict[str, Any] = {}
            if payment_intent_id:
                payment_intent = stripe.PaymentIntent.retrieve(
                    payment_intent_id, **request_options
                )
                payment_intent_object = payment_intent.to_dict()
                latest_charge_id = payment_intent_object.get("latest_charge", "") or ""

            return PaymentCreationResult(
                provider_reference=session_dict["id"],
                raw_response=session_dict,
                client_secret=session_dict.get("client_secret"),
                checkout_session_id=session_dict["id"],
                extra={
                    "payment_intent_id": payment_intent_id or "",
                    "latest_charge_id": latest_charge_id,
                    "payment_intent_object": payment_intent_object,
                    "metadata": metadata,
                    "discounts": params.get("discounts") or [],
                    "url": session_dict.get("url", ""),
                },
            )

        # Default to payment intent flow
        intent_params = options.get("payment_intent_params", {})
        intent = stripe.PaymentIntent.create(
            amount=request.amount,
            currency=request.currency,
            metadata=metadata,
            **intent_params,
            **request_options,
        )
        intent_dict = intent.to_dict()

        return PaymentCreationResult(
            provider_reference=intent_dict["id"],
            raw_response=intent_dict,
            client_secret=intent_dict.get("client_secret"),
            extra={
                "latest_charge_id": intent_dict.get("latest_charge", "") or "",
                "payment_intent_object": intent_dict,
                "metadata": metadata,
            },
        )

    def create_subscription(
        self, *, request: PaymentRequest, app: Flask
    ) -> PaymentCreationResult:
        """Create a recurring subscription through this provider."""
        options: dict[str, Any] = dict(request.extra or {})
        session_params = dict(options.get("session_params", {}) or {})
        session_params["mode"] = "subscription"
        options["mode"] = "checkout_session"
        options["session_params"] = session_params
        subscription_request = PaymentRequest(
            order_bid=request.order_bid,
            user_bid=request.user_bid,
            shifu_bid=request.shifu_bid,
            amount=request.amount,
            channel=request.channel,
            currency=request.currency,
            subject=request.subject,
            body=request.body,
            client_ip=request.client_ip,
            extra=options,
        )
        return self.create_payment(request=subscription_request, app=app)

    def cancel_subscription(
        self,
        *,
        subscription_bid: str,
        provider_subscription_id: str,
        app: Flask,
    ) -> SubscriptionUpdateResult:
        """Schedule provider subscription cancellation at the current period end."""
        stripe, request_options = self._client_options(app)
        subscription = stripe.Subscription.modify(
            provider_subscription_id,
            cancel_at_period_end=True,
            metadata={"subscription_bid": subscription_bid},
            **request_options,
        )
        payload = subscription.to_dict()
        return SubscriptionUpdateResult(
            provider_reference=payload.get("id", provider_subscription_id),
            raw_response=payload,
            status=payload.get("status", ""),
            extra={
                "cancel_at_period_end": bool(payload.get("cancel_at_period_end")),
            },
        )

    def resume_subscription(
        self,
        *,
        subscription_bid: str,
        provider_subscription_id: str,
        app: Flask,
    ) -> SubscriptionUpdateResult:
        """Clear Stripe's scheduled cancellation for a subscription."""
        stripe, request_options = self._client_options(app)
        subscription = stripe.Subscription.modify(
            provider_subscription_id,
            cancel_at_period_end=False,
            metadata={"subscription_bid": subscription_bid},
            **request_options,
        )
        payload = subscription.to_dict()
        return SubscriptionUpdateResult(
            provider_reference=payload.get("id", provider_subscription_id),
            raw_response=payload,
            status=payload.get("status", ""),
            extra={
                "cancel_at_period_end": bool(payload.get("cancel_at_period_end")),
            },
        )

    def retrieve_checkout_session(
        self, *, session_id: str, app: Flask
    ) -> dict[str, Any]:
        """Retrieve a Stripe checkout session."""
        stripe, request_options = self._client_options(app)
        return stripe.checkout.Session.retrieve(session_id, **request_options)

    def expire_checkout_session(self, *, session_id: str, app: Flask) -> dict[str, Any]:
        """Expire an open Stripe checkout session."""
        stripe, request_options = self._client_options(app)
        session = stripe.checkout.Session.expire(session_id, **request_options)
        return session.to_dict() if hasattr(session, "to_dict") else session

    def cancel_payment(
        self,
        *,
        provider_reference: str,
        reference_type: str,
        app: Flask,
    ) -> PaymentCancellationResult:
        """Expire Checkout or cancel an uncaptured PaymentIntent."""
        stripe, request_options = self._client_options(app)
        normalized_type = str(reference_type or "").strip().lower()
        if normalized_type not in {"checkout_session", "payment_intent"}:
            message = f"Unsupported Stripe reference type: {reference_type}"
            raise RuntimeError(message)
        try:
            if normalized_type == "checkout_session":
                response = stripe.checkout.Session.expire(
                    provider_reference, **request_options
                )
            else:
                response = stripe.PaymentIntent.cancel(
                    provider_reference, **request_options
                )
        except Exception:
            if normalized_type == "checkout_session":
                response = stripe.checkout.Session.retrieve(
                    provider_reference, **request_options
                )
                recovered_status = str(response.get("status") or "").lower()
                terminal = recovered_status in {"complete", "expired"}
            elif normalized_type == "payment_intent":
                response = stripe.PaymentIntent.retrieve(
                    provider_reference, **request_options
                )
                terminal = str(response.get("status") or "").lower() == "canceled"
            if not terminal:
                raise
        payload = response.to_dict() if hasattr(response, "to_dict") else dict(response)
        cancellation_status = "cancelled"
        if (
            normalized_type == "checkout_session"
            and str(payload.get("status") or "").lower() == "complete"
        ):
            cancellation_status = "completed"
        return PaymentCancellationResult(
            provider_reference=provider_reference,
            raw_response=payload,
            status=cancellation_status,
        )

    def retrieve_payment_intent(self, *, intent_id: str, app: Flask) -> dict[str, Any]:
        """Retrieve a Stripe payment intent."""
        stripe, request_options = self._client_options(app)
        return stripe.PaymentIntent.retrieve(intent_id, **request_options)

    def retrieve_subscription(
        self, *, subscription_id: str, app: Flask
    ) -> dict[str, Any]:
        """Retrieve a Stripe subscription."""
        stripe, request_options = self._client_options(app)
        return stripe.Subscription.retrieve(subscription_id, **request_options)

    def verify_webhook(
        self, *, headers: dict[str, str], raw_body: bytes | str, app: Flask
    ) -> PaymentNotificationResult:
        """Verify and decode a provider webhook payload."""
        stripe, _request_options = self._client_options(app)
        webhook_secret = get_config("STRIPE_WEBHOOK_SECRET")
        if not webhook_secret:
            app.logger.error("STRIPE_WEBHOOK_SECRET configuration is missing")
            message = "STRIPE_WEBHOOK_SECRET must be configured for Stripe"
            raise RuntimeError(message)

        if isinstance(raw_body, bytes):
            raw_body_str = raw_body.decode("utf-8")
        else:
            raw_body_str = str(raw_body or "")
        sig_header = headers.get("Stripe-Signature") or headers.get(
            "stripe-signature", ""
        )
        if not sig_header:
            message = "Stripe signature header missing"
            raise RuntimeError(message)

        try:
            event = stripe.Webhook.construct_event(
                raw_body_str, sig_header, webhook_secret
            )
        except Exception:  # pragma: no cover - handled in caller
            app.logger.exception("Stripe webhook signature verification failed")
            raise

        return self._build_notification_from_event(event)

    def handle_notification(
        self, *, payload: dict[str, Any], app: Flask
    ) -> PaymentNotificationResult:
        """Verify and normalize a Stripe provider notification."""
        headers = dict(payload.get("headers", {}) or {})
        sig_header = payload.get("sig_header", "")
        if sig_header and "Stripe-Signature" not in headers:
            headers["Stripe-Signature"] = sig_header
        return self.verify_webhook(
            headers=headers,
            raw_body=payload.get("raw_body", ""),
            app=app,
        )

    def sync_reference(
        self, *, provider_reference: str, reference_type: str, app: Flask
    ) -> PaymentNotificationResult:
        """Retrieve and normalize Stripe state for local state application."""
        normalized_reference_type = str(reference_type or "").strip().lower()
        if normalized_reference_type in {"checkout_session", "session", "payment"}:
            session = self.retrieve_checkout_session(
                session_id=provider_reference,
                app=app,
            )
            intent = None
            intent_id = session.get("payment_intent") or ""
            if intent_id:
                intent = self.retrieve_payment_intent(intent_id=intent_id, app=app)
            payload = {
                "checkout_session": session,
                "payment_intent": intent or {},
            }
            charge_id = ""
            if intent:
                charge_id = str(intent.get("latest_charge") or "")
                if not charge_id:
                    charges = intent.get("charges", {}).get("data", [])
                    if charges:
                        charge_id = str(charges[0].get("id") or "")
            metadata = session.get("metadata", {}) or {}
            if not metadata.get("order_bid") and intent:
                metadata = intent.get("metadata", {}) or {}
            return PaymentNotificationResult(
                order_bid=str(metadata.get("order_bid") or ""),
                status="manual_sync",
                provider_payload=payload,
                charge_id=charge_id or None,
            )
        if normalized_reference_type == "payment_intent":
            intent = self.retrieve_payment_intent(intent_id=provider_reference, app=app)
            metadata = intent.get("metadata", {}) or {}
            charge_id = str(intent.get("latest_charge") or "") or None
            return PaymentNotificationResult(
                order_bid=str(metadata.get("order_bid") or ""),
                status="manual_sync",
                provider_payload={"payment_intent": intent},
                charge_id=charge_id,
            )
        if normalized_reference_type == "subscription":
            subscription = self.retrieve_subscription(
                subscription_id=provider_reference,
                app=app,
            )
            metadata = subscription.get("metadata", {}) or {}
            return PaymentNotificationResult(
                order_bid=str(metadata.get("order_bid") or ""),
                status="manual_sync",
                provider_payload={"subscription": subscription},
                charge_id=None,
            )
        message = f"Unsupported Stripe reference type: {reference_type}"
        raise RuntimeError(message)

    def refund_payment(
        self, *, request: PaymentRefundRequest, app: Flask
    ) -> PaymentRefundResult:
        """Refund a payment through this provider."""
        if request.metadata.get("refund_operation_bid"):
            _validate_refund_request(request)
            operation_key = request.metadata.get("idempotency_key")
            if not isinstance(operation_key, str) or not operation_key.strip():
                message = "Stripe refund operation requires a stable idempotency key"
                raise RuntimeError(message)
        stripe, request_options = self._client_options(app)
        params: dict[str, Any] = {}
        if request.amount is not None:
            params["amount"] = request.amount
        if request.reason:
            params["reason"] = request.reason

        metadata = dict(request.metadata or {})
        if hasattr(metadata, "to_dict"):
            metadata = metadata.to_dict()
        idempotency_key = str(metadata.pop("idempotency_key", "") or "")
        metadata.setdefault("order_bid", request.order_bid)
        params["metadata"] = metadata

        payment_intent_id = metadata.get("payment_intent_id")
        charge_id = metadata.get("charge_id")
        if payment_intent_id:
            params["payment_intent"] = payment_intent_id
        elif charge_id:
            params["charge"] = charge_id
        else:
            message = "Stripe refund requires payment_intent_id or charge_id metadata"
            raise RuntimeError(message)

        if idempotency_key:
            request_options = {
                **request_options,
                "idempotency_key": idempotency_key,
            }
        refund = stripe.Refund.create(**params, **request_options)
        if request.metadata.get("refund_operation_bid"):
            result = _validated_refund_result(refund, request=request)
            if (
                result.raw_response["metadata"].get("refund_operation_bid")
                != request.metadata["refund_operation_bid"]
            ):
                message = "Stripe refund response is missing its operation identity"
                raise RuntimeError(message)
            return result
        refund_dict = refund.to_dict()

        return PaymentRefundResult(
            provider_reference=refund_dict.get("id", ""),
            raw_response=refund_dict,
            status=refund_dict.get("status", ""),
        )

    def reconcile_refund(
        self, *, request: PaymentRefundRequest, app: Flask
    ) -> PaymentRefundResult | None:
        """Recover a uniquely attributable refund using only provider reads."""
        _validate_refund_request(request)
        stripe, request_options = self._client_options(app)
        refund_id = request.metadata.get("refund_reference_id")
        if refund_id:
            refund = stripe.Refund.retrieve(refund_id, **request_options)
            return _validated_refund_result(
                refund, request=request, reference_id=refund_id
            )

        payment_intent = request.metadata.get("payment_intent_id")
        params = (
            {"payment_intent": payment_intent}
            if payment_intent
            else {"charge": request.metadata["charge_id"]}
        )
        refunds: list[PaymentRefundResult] = []
        seen_ids: set[str] = set()
        while True:
            page = _refund_payload(
                stripe.Refund.list(**params, limit=100, **request_options)
            )
            data = page.get("data")
            has_more = page.get("has_more")
            if (
                page.get("object") != "list"
                or not isinstance(data, list)
                or not isinstance(has_more, bool)
                or (has_more and not data)
            ):
                message = "Stripe refund history is incomplete"
                raise RuntimeError(message)
            for value in data:
                result = _validated_refund_result(
                    value, request=request, match_amount=False, match_operation=False
                )
                if result.provider_reference in seen_ids:
                    message = "Stripe refund history contains repeated identifiers"
                    raise RuntimeError(message)
                seen_ids.add(result.provider_reference)
                refunds.append(result)
            if not has_more:
                break
            params["starting_after"] = refunds[-1].provider_reference

        if not refunds:
            return None
        operation = request.metadata.get("refund_operation_bid")
        matches = [
            refund
            for refund in refunds
            if operation
            and refund.raw_response["metadata"].get("refund_operation_bid") == operation
        ]
        if len(matches) == 1:
            candidate = matches[0]
            if any(
                refund is not candidate and refund.status in _ACTIVE_REFUND_STATUSES
                for refund in refunds
            ):
                message = "Stripe refund history contains another active refund"
                raise RuntimeError(message)
            return _validated_refund_result(candidate.raw_response, request=request)
        payment_amount = request.metadata.get("payment_amount")
        if (
            not matches
            and len(refunds) == 1
            and not refunds[0].raw_response["metadata"].get("refund_operation_bid")
            and isinstance(payment_amount, int)
            and not isinstance(payment_amount, bool)
            and payment_amount == request.amount
        ):
            return _validated_refund_result(refunds[0].raw_response, request=request)
        message = "Stripe refund history cannot identify this refund operation"
        raise RuntimeError(message)

    def _build_notification_from_event(
        self, event: dict[str, Any]
    ) -> PaymentNotificationResult:
        data_object = event.get("data", {}).get("object", {}) or {}
        metadata = data_object.get("metadata", {}) or {}
        order_bid = metadata.get("order_bid", "")
        charge_id = data_object.get("latest_charge") or ""
        if not charge_id:
            charges = data_object.get("charges", {}).get("data", [])
            if charges:
                charge_id = charges[0].get("id", "")

        return PaymentNotificationResult(
            order_bid=order_bid,
            status=event.get("type", ""),
            provider_payload=event,
            charge_id=charge_id or None,
        )


register_payment_provider(StripeProvider)
